"""Integration: импорт демо-кампаний на пустую (боевую) БД —
scripts/migrate_demo_campaigns.py.

Проверяет: перенос методик/кампаний/участников из закоммиченной выгрузки;
безопасные умолчания (campaign_only, закрытые кампании); идемпотентность
повторного запуска; dry-run не пишет; сверку шкал (порча выгрузки → откат);
ФИО перешифрованы и не лежат открытым текстом; ошибка при незасеянном ИТО.
"""
import copy
import importlib.util
import json
import uuid
from pathlib import Path

import pytest

from app.core.encryption import decrypt_text
from app.db.models import (CampaignResponse, ConsentRecord, Option, Question, Test,
                           TestCampaign, TestInterpretation, User)
from app.db.session import SessionLocal
from app.tests.profiles.ito_seed import ensure_ito_test, find_ito_test
from tests.integration.conftest import create_test_user

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_demo_campaigns.py"
spec = importlib.util.spec_from_file_location("migrate_demo_campaigns_it", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BUNDLE = json.loads(mod.DEFAULT_BUNDLE.read_text(encoding="utf-8"))


def _purge(bundle):
    with SessionLocal() as db:
        for c in bundle["campaigns"]:
            camp = db.query(TestCampaign).filter(TestCampaign.uuid == uuid.UUID(c["uuid"])).first()
            if camp:
                db.delete(camp)
        db.flush()
        db.query(ConsentRecord).filter(ConsentRecord.user_agent == mod.IMPORT_UA).delete()
        for t in bundle["tests"]:
            test = db.query(Test).filter(Test.uuid == uuid.UUID(t["uuid"])).first()
            if test:
                qids = [q.id for q in db.query(Question).filter(Question.test_id == test.id)]
                db.query(Option).filter(Option.question_id.in_(qids)).delete(synchronize_session=False)
                db.query(Question).filter(Question.test_id == test.id).delete()
                db.query(TestInterpretation).filter(TestInterpretation.test_id == test.id).delete()
                db.delete(test)
        db.commit()


@pytest.fixture
def env(client, test_email):
    owner = create_test_user(test_email)
    ito_before = None
    with SessionLocal() as db:
        ito_before = find_ito_test(db)
        _, created = ensure_ito_test(db)
        db.commit()
    yield owner, test_email
    _purge(BUNDLE)
    if ito_before is None:
        with SessionLocal() as db:
            t = find_ito_test(db)
            if t is not None:
                qids = [q.id for q in db.query(Question).filter(Question.test_id == t.id)]
                db.query(Option).filter(Option.question_id.in_(qids)).delete(synchronize_session=False)
                db.query(Question).filter(Question.test_id == t.id).delete()
                db.query(TestInterpretation).filter(TestInterpretation.test_id == t.id).delete()
                db.delete(t)
                db.commit()


def _count():
    with SessionLocal() as db:
        uuids = [uuid.UUID(c["uuid"]) for c in BUNDLE["campaigns"]]
        camps = db.query(TestCampaign).filter(TestCampaign.uuid.in_(uuids)).all()
        n = db.query(CampaignResponse).filter(
            CampaignResponse.campaign_id.in_([c.id for c in camps])).count() if camps else 0
        return len(camps), n


def test_import_defaults_idempotent_and_safe(env):
    _, email = env
    s1 = mod.do_import(BUNDLE, email, dry_run=False, catalog=False, keep_status=False)
    assert s1["campaigns_created"] == 5 and s1["tests_created"] == 3
    assert s1["responses"] == 136
    assert _count() == (5, 136)

    with SessionLocal() as db:
        for t in BUNDLE["tests"]:
            row = db.query(Test).filter(Test.uuid == uuid.UUID(t["uuid"])).one()
            assert row.campaign_only is True and row.status == "published"
        camps = db.query(TestCampaign).filter(
            TestCampaign.uuid.in_([uuid.UUID(c["uuid"]) for c in BUNDLE["campaigns"]])).all()
        assert {c.status for c in camps} == {"closed"}
        assert all(c.link_token_enc.startswith("enc:v1:") for c in camps)
        resp = db.query(CampaignResponse).first()
        assert resp.full_name_enc.startswith("enc:v1:")
        assert decrypt_text(resp.full_name_enc)
        rec = db.get(ConsentRecord, resp.consent_record_id)
        assert rec.ip_address is None and rec.user_agent == mod.IMPORT_UA

    s2 = mod.do_import(BUNDLE, email, dry_run=False, catalog=False, keep_status=False)
    assert s2["campaigns_created"] == 0 and s2["campaigns_skipped"] == 5
    assert s2["tests_created"] == 0 and s2["responses"] == 0
    assert _count() == (5, 136)


def test_dry_run_writes_nothing(env):
    _, email = env
    s = mod.do_import(BUNDLE, email, dry_run=True, catalog=False, keep_status=False)
    assert s["campaigns_created"] == 5
    assert _count() == (0, 0)
    with SessionLocal() as db:
        assert db.query(Test).filter(Test.uuid == uuid.UUID(BUNDLE["tests"][0]["uuid"])).count() == 0


def test_catalog_and_keep_status_flags(env):
    _, email = env
    mod.do_import(BUNDLE, email, dry_run=False, catalog=True, keep_status=True)
    with SessionLocal() as db:
        t = db.query(Test).filter(Test.uuid == uuid.UUID(BUNDLE["tests"][0]["uuid"])).one()
        assert t.campaign_only is False
        open_n = db.query(TestCampaign).filter(
            TestCampaign.uuid.in_([uuid.UUID(c["uuid"]) for c in BUNDLE["campaigns"]]),
            TestCampaign.status == "open").count()
        assert open_n == sum(1 for c in BUNDLE["campaigns"] if c["status"] == "open")


def test_corrupted_scales_roll_everything_back(env):
    _, email = env
    bad = copy.deepcopy(BUNDLE)
    victim = next(c for c in bad["campaigns"] if c["responses"] and c["title"] != BUNDLE["campaigns"][0]["title"])
    victim["responses"][-1]["scales"][0][1] += 1
    with pytest.raises(mod.BundleError):
        mod.do_import(bad, email, dry_run=False, catalog=False, keep_status=False)
    assert _count() == (0, 0)
    with SessionLocal() as db:
        assert db.query(Test).filter(Test.uuid == uuid.UUID(BUNDLE["tests"][0]["uuid"])).count() == 0


def test_unknown_owner_and_non_synthetic_bundle_rejected(env):
    with pytest.raises(mod.BundleError):
        mod.do_import(BUNDLE, "integ_nobody@donnu.ru", dry_run=True, catalog=False, keep_status=False)
    with pytest.raises(mod.BundleError):
        mod.do_import({**BUNDLE, "synthetic": False}, env[1], dry_run=True, catalog=False, keep_status=False)

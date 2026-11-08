#!/usr/bin/env python3
"""
Перенос демо-методик и демо-кампаний с синтетическими участниками
из dev-БД в боевую (подкоманды export / import).

Что переносится
  • кампании, чьё название начинается с «Демо:» (ИТО на 100 студентов,
    «Самочувствие», «Напряжение и усталость», «Мотивация с кодовым словом», …);
  • методики этих кампаний — вопросы, варианты, ключ, правила обработки
    (`scoring_rules`, в т.ч. нормы и уровни) и пороги `test_interpretations`;
    ИТО Собчик в файл НЕ кладётся — на проде его создаёт seed_ito_sobchik,
    ответы сопоставляются с ним по (номер вопроса, номер варианта);
  • участники (ФИО, факультет, специальность, возраст, пол), их ответы и баллы шкал.

Чего НЕ переносится
  • ответы реальных людей: экспорт берёт только участников, чей согласия-User-Agent
    входит в список синтетических (--synthetic-ua), остальных отбрасывает и
    печатает их число; ФИО в вывод не печатается;
  • токены ссылок (на проде выдаются новые), IP участников, файлы медиа
    (методика с медиа/рубриками/тегами в выгрузку не попадает — экспорт
    прерывается), SMOKE-тесты и чужие кампании.

Безопасные умолчания импорта (меняются флагами, итог печатается):
  • демо-методики `campaign_only=true` — в каталоге студентов их нет
    (`--catalog` — показать в каталоге);
  • кампании создаются закрытыми (`--keep-status` — как на dev).

Файл выгрузки содержит СИНТЕТИЧЕСКИЕ ФИО открытым текстом (перешифровываются
ключом прода при импорте) — реальные данные в него класть нельзя; флаг
`"synthetic": true` проверяется при импорте.

Порядок на проде (из mindcare_api/):
    alembic upgrade head
    python scripts/seed_ito_sobchik.py
    python scripts/migrate_demo_campaigns.py import --owner-email <e-mail супервизора> --dry-run
    python scripts/migrate_demo_campaigns.py import --owner-email <e-mail супервизора>

Повторный запуск безопасен: уже существующие по uuid кампании и методики
пропускаются, ничего не дублируется. Весь импорт — одна транзакция; перед
фиксацией шкалы каждого участника пересчитываются по ключу методики на проде и
сверяются с выгруженными, при расхождении — откат.
"""
import argparse
import json
import sys
import uuid as uuid_mod
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FORMAT_VERSION = 1
DEFAULT_BUNDLE = Path(__file__).resolve().parent / "data" / "demo_campaigns_bundle.json"
DEFAULT_PREFIX = "Демо:"
# User-Agent'ы синтетических участников: генератор ИТО и скрипт демо-кампаний.
DEFAULT_SYNTHETIC_UA = ("mindcare-demo-generator", "Python-urllib/3.13")
IMPORT_UA = "mindcare-demo-import"   # User-Agent согласий, созданных импортом


class BundleError(Exception):
    """Выгрузка или состояние БД не позволяют продолжить (выход с кодом 1)."""


# ── чистые функции (покрыты tests/test_migrate_demo_campaigns.py) ─────────────

def split_synthetic(rows: list[dict], allowed_ua: tuple) -> tuple[list, int]:
    """(синтетические, число отброшенных). Критерий — User-Agent согласия."""
    keep = [r for r in rows if r.get("user_agent") in allowed_ua]
    return keep, len(rows) - len(keep)


def answers_to_ids(answers: list, qmap: dict, omap: dict) -> list[dict]:
    """[(№ вопроса, № варианта)] → [{question_id, option_id}] по картам прода.

    qmap: {question_order: question_id}; omap: {(question_order, option_order): option_id}.
    Неизвестная пара — BundleError (структура методики на проде расходится).
    """
    out = []
    for qo, oo in answers:
        if qo not in qmap or (qo, oo) not in omap:
            raise BundleError(f"ответ ({qo}, {oo}) не найден в методике на проде")
        out.append({"question_id": qmap[qo], "option_id": omap[(qo, oo)]})
    return out


def scales_match(expected: list, computed: list[dict]) -> bool:
    """Выгруженные [[имя, балл, максимум]] совпадают с пересчитанными."""
    a = sorted((n, int(s), int(m)) for n, s, m in expected)
    b = sorted((c["scale_name"], int(c["score"]), int(c["max_score"])) for c in computed)
    return a == b


def validate_bundle(bundle: dict) -> None:
    if not isinstance(bundle, dict) or bundle.get("format_version") != FORMAT_VERSION:
        raise BundleError("неизвестный format_version выгрузки")
    if bundle.get("synthetic") is not True:
        raise BundleError("выгрузка не помечена synthetic=true — импорт запрещён")


def _iso(dt):
    return dt.isoformat() if dt else None


def _dt(s):
    return datetime.fromisoformat(s) if s else None


# ── экспорт ───────────────────────────────────────────────────────────────────

def _export_test(db, test) -> dict:
    from app.db.models import (Option, Question, TestInterpretation)
    from sqlalchemy import text

    for table in ("test_categories", "test_tags"):
        n = db.execute(text(f"SELECT count(*) FROM {table} WHERE test_id = :t"),
                       {"t": test.id}).scalar()
        if n:
            raise BundleError(f"у методики «{test.title}» есть связи в {table} — не переносится")
    n = db.execute(text(
        "SELECT (SELECT count(*) FROM question_media qm JOIN questions q ON q.id = qm.question_id"
        " WHERE q.test_id = :t) + (SELECT count(*) FROM option_media om"
        " JOIN options o ON o.id = om.option_id JOIN questions q ON q.id = o.question_id"
        " WHERE q.test_id = :t)"), {"t": test.id}).scalar()
    if n:
        raise BundleError(f"у методики «{test.title}» есть медиа — файлы не переносятся")

    questions = []
    for q in (db.query(Question).filter(Question.test_id == test.id)
              .order_by(Question.question_order, Question.id).all()):
        opts = (db.query(Option).filter(Option.question_id == q.id)
                .order_by(Option.option_order, Option.id).all())
        questions.append({
            "order": q.question_order, "text": q.question_text,
            "type": q.question_type, "is_required": q.is_required,
            "config": q.config or {},
            "options": [{"order": o.option_order, "text": o.option_text,
                         "value_score": o.value_score} for o in opts],
        })
    interps = (db.query(TestInterpretation).filter(TestInterpretation.test_id == test.id)
               .order_by(TestInterpretation.scale_name, TestInterpretation.min_score,
                         TestInterpretation.id).all())
    return {
        "uuid": str(test.uuid), "lineage_uuid": str(test.lineage_uuid),
        "title": test.title, "description": test.description, "version": test.version,
        "scoring": test.scoring, "max_score": test.max_score,
        "time_limit_min": test.time_limit_min,
        "shuffle_questions": test.shuffle_questions, "shuffle_options": test.shuffle_options,
        "scoring_rules": test.scoring_rules,
        "questions": questions,
        "interpretations": [{"scale_name": i.scale_name, "min_score": i.min_score,
                             "max_score": i.max_score, "label": i.label,
                             "recommendation": i.recommendation} for i in interps],
    }


def do_export(out: Path, prefix: str, allowed_ua: tuple) -> dict:
    from sqlalchemy import text
    from app.core.encryption import decrypt_text
    from app.db.models import (CampaignResponse, CampaignResponseAnswer,
                               CampaignResponseScale, ConsentRecord, Option, Question,
                               Test, TestCampaign)
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        campaigns = (db.query(TestCampaign).filter(TestCampaign.title.like(prefix + "%"))
                     .order_by(TestCampaign.created_at, TestCampaign.id).all())
        if not campaigns:
            raise BundleError(f"кампаний с названием «{prefix}…» нет")
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()

        tests, profiles, out_campaigns, report = {}, {}, [], []
        for c in campaigns:
            test = db.get(Test, c.test_id)
            if test.scoring_profile:
                profiles[str(test.uuid)] = {"scoring_profile": test.scoring_profile,
                                            "version": test.version}
            elif str(test.uuid) not in tests:
                tests[str(test.uuid)] = _export_test(db, test)

            qorder = {q.id: q.question_order for q in
                      db.query(Question).filter(Question.test_id == test.id)}
            oorder = {(o.id): (qorder[o.question_id], o.option_order) for o in
                      db.query(Option).join(Question, Question.id == Option.question_id)
                      .filter(Question.test_id == test.id)}

            raw = []
            for r, ua in (db.query(CampaignResponse, ConsentRecord.user_agent)
                          .join(ConsentRecord, ConsentRecord.id == CampaignResponse.consent_record_id)
                          .filter(CampaignResponse.campaign_id == c.id)
                          .order_by(CampaignResponse.submitted_at, CampaignResponse.id).all()):
                raw.append({"r": r, "user_agent": ua})
            keep, dropped = split_synthetic(raw, allowed_ua)

            responses = []
            for item in keep:
                r = item["r"]
                answers = (db.query(CampaignResponseAnswer)
                           .filter(CampaignResponseAnswer.response_id == r.id).all())
                scales = (db.query(CampaignResponseScale)
                          .filter(CampaignResponseScale.response_id == r.id)
                          .order_by(CampaignResponseScale.scale_name).all())
                responses.append({
                    "uuid": str(r.uuid), "submission_key": str(r.submission_key),
                    "test_version": r.test_version,
                    "full_name": decrypt_text(r.full_name_enc),
                    "faculty_code": r.faculty_code, "specialty": r.specialty,
                    "age": r.age, "gender": r.gender, "submitted_at": _iso(r.submitted_at),
                    "answers": sorted([list(oorder[a.option_id]) for a in answers]),
                    "scales": [[s.scale_name, s.score, s.max_score] for s in scales],
                })
            out_campaigns.append({
                "uuid": str(c.uuid), "title": c.title, "test_uuid": str(test.uuid),
                "status": c.status, "created_at": _iso(c.created_at),
                "closed_at": _iso(c.closed_at), "opens_at": _iso(c.opens_at),
                "closes_at": _iso(c.closes_at), "access_code_hash": c.access_code_hash,
                "responses": responses,
            })
            report.append((c.title, len(keep), dropped))

    bundle = {
        "format_version": FORMAT_VERSION,
        "synthetic": True,
        "note": "СИНТЕТИЧЕСКИЕ данные демо-кампаний MindCare. Реальных участников здесь нет.",
        "source_revision": revision,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tests": list(tests.values()),
        "profile_tests": profiles,
        "campaigns": out_campaigns,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Выгрузка: {out}")
    print(f"  методик: {len(tests)} (+ по профилю: {len(profiles)}), кампаний: {len(out_campaigns)}")
    for title, kept, dropped in report:
        print(f"  {title}: участников {kept}, отброшено не синтетических {dropped}")
    return bundle


# ── импорт ────────────────────────────────────────────────────────────────────

def _check_head(db) -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    heads = set(ScriptDirectory.from_config(Config(str(ini))).get_heads())
    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if current not in heads:
        raise BundleError(f"БД не на head ({current} ≠ {sorted(heads)}): сначала alembic upgrade head")


def _structure_maps(db, test_id: int) -> tuple[dict, dict]:
    from app.db.models import Option, Question

    qmap, omap = {}, {}
    for q in db.query(Question).filter(Question.test_id == test_id):
        qmap[q.question_order] = q.id
        for o in db.query(Option).filter(Option.question_id == q.id):
            omap[(q.question_order, o.option_order)] = o.id
    return qmap, omap


def _create_test(db, spec: dict, owner_id: int, catalog: bool):
    from app.db.models import Option, Question, Test, TestInterpretation

    test = Test(
        uuid=uuid_mod.UUID(spec["uuid"]), lineage_uuid=uuid_mod.UUID(spec["lineage_uuid"]),
        title=spec["title"], description=spec["description"], version=spec["version"],
        scoring=spec["scoring"], max_score=spec["max_score"],
        time_limit_min=spec["time_limit_min"],
        shuffle_questions=spec["shuffle_questions"], shuffle_options=spec["shuffle_options"],
        scoring_rules=spec["scoring_rules"], status="published", is_active=True,
        campaign_only=not catalog, created_by=owner_id,
    )
    db.add(test)
    db.flush()
    for q in spec["questions"]:
        question = Question(test_id=test.id, question_text=q["text"], question_order=q["order"],
                            question_type=q["type"], is_required=q["is_required"],
                            config=q["config"])
        db.add(question)
        db.flush()
        db.add_all(Option(question_id=question.id, option_text=o["text"],
                          option_order=o["order"], value_score=o["value_score"])
                   for o in q["options"])
    db.add_all(TestInterpretation(test_id=test.id, **i) for i in spec["interpretations"])
    db.flush()
    return test


def do_import(bundle: dict, owner_email: str, *, dry_run: bool, catalog: bool,
              keep_status: bool) -> dict:
    from app.campaigns import tokens
    from app.campaigns.answers import compute
    from app.campaigns.storage import _latest_consent, _test_structure
    from app.core.encryption import encrypt_text
    from app.core.normalization import normalize_email
    from app.db.models import (CampaignResponse, CampaignResponseAnswer,
                               CampaignResponseScale, ConsentRecord, Test, TestCampaign, User)
    from app.db.session import SessionLocal
    from app.tests.profiles.ito_seed import find_ito_test

    validate_bundle(bundle)
    stats = {"tests_created": 0, "tests_skipped": 0, "campaigns_created": 0,
             "campaigns_skipped": 0, "responses": 0}
    with SessionLocal() as db:
        try:
            _check_head(db)
            owner = (db.query(User).filter(User.email == normalize_email(owner_email),
                                           User.deleted_at.is_(None)).first())
            if owner is None or owner.is_active is False:
                raise BundleError("пользователь --owner-email не найден или отключён")
            consent = _latest_consent(db)   # RuntimeError, если campaign_consent не засеян

            by_uuid: dict[str, Test] = {}
            for spec in bundle["tests"]:
                existing = db.query(Test).filter(Test.uuid == uuid_mod.UUID(spec["uuid"])).first()
                if existing:
                    stats["tests_skipped"] += 1
                    by_uuid[spec["uuid"]] = existing
                else:
                    by_uuid[spec["uuid"]] = _create_test(db, spec, owner.id, catalog)
                    stats["tests_created"] += 1
            for src_uuid, prof in bundle["profile_tests"].items():
                if prof["scoring_profile"] != "ito_sobchik":
                    raise BundleError(f"неизвестный профиль {prof['scoring_profile']}")
                ito = find_ito_test(db)
                if ito is None:
                    raise BundleError("методика ИТО не найдена: сначала scripts/seed_ito_sobchik.py")
                by_uuid[src_uuid] = ito

            for spec in bundle["campaigns"]:
                if db.query(TestCampaign).filter(
                        TestCampaign.uuid == uuid_mod.UUID(spec["uuid"])).first():
                    stats["campaigns_skipped"] += 1
                    continue
                test = by_uuid[spec["test_uuid"]]
                token = tokens.generate_token(spec["title"])
                closed = (not keep_status) or spec["status"] == "closed"
                campaign = TestCampaign(
                    uuid=uuid_mod.UUID(spec["uuid"]), test_id=test.id, title=spec["title"],
                    status="closed" if closed else "open",
                    link_token_hash=tokens.hash_token(token), link_token_enc=encrypt_text(token),
                    created_by=owner.id,
                    closed_at=(_dt(spec["closed_at"]) or datetime.now(timezone.utc)) if closed else None,
                    opens_at=_dt(spec["opens_at"]), closes_at=_dt(spec["closes_at"]),
                    access_code_hash=spec["access_code_hash"],
                )
                if closed and campaign.closes_at and campaign.opens_at \
                        and campaign.opens_at >= campaign.closes_at:
                    raise BundleError(f"кампания «{spec['title']}»: opens_at ≥ closes_at")
                db.add(campaign)
                db.flush()

                structure = _test_structure(db, test)
                qmap, omap = _structure_maps(db, test.id)
                for r in spec["responses"]:
                    ids = answers_to_ids(r["answers"], qmap, omap)
                    if len(ids) != len(qmap):
                        raise BundleError(f"«{spec['title']}»: неполный набор ответов")
                    if not scales_match(r["scales"], compute(structure, ids)):
                        raise BundleError(
                            f"«{spec['title']}»: пересчёт шкал не совпал с выгрузкой "
                            f"(участник {r['uuid']})")
                    record = ConsentRecord(user_id=None, consent_id=consent.id, accepted=True,
                                           ip_address=None, user_agent=IMPORT_UA,
                                           accepted_at=_dt(r["submitted_at"]))
                    db.add(record)
                    db.flush()
                    resp = CampaignResponse(
                        uuid=uuid_mod.UUID(r["uuid"]), campaign_id=campaign.id,
                        submission_key=uuid_mod.UUID(r["submission_key"]),
                        test_version=r["test_version"], full_name_enc=encrypt_text(r["full_name"]),
                        faculty_code=r["faculty_code"], specialty=r["specialty"], age=r["age"],
                        gender=r["gender"], consent_record_id=record.id,
                        submitted_at=_dt(r["submitted_at"]),
                    )
                    db.add(resp)
                    db.flush()
                    db.add_all(CampaignResponseScale(response_id=resp.id, scale_name=n,
                                                     score=s, max_score=m)
                               for n, s, m in r["scales"])
                    db.add_all(CampaignResponseAnswer(response_id=resp.id, **a) for a in ids)
                    stats["responses"] += 1
                stats["campaigns_created"] += 1
        except BaseException:
            db.rollback()
            raise
        if dry_run:
            db.rollback()
        else:
            db.commit()
    mode = "DRY-RUN (откат)" if dry_run else "ЗАФИКСИРОВАНО"
    print(f"{mode}: методик создано {stats['tests_created']}, пропущено {stats['tests_skipped']}; "
          f"кампаний создано {stats['campaigns_created']}, пропущено {stats['campaigns_skipped']}; "
          f"участников {stats['responses']}")
    print(f"  методики в каталоге студентов: {'да' if catalog else 'нет (campaign_only)'}; "
          f"кампании: {'как на dev' if keep_status else 'закрыты'}")
    return stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="dev-БД → файл выгрузки")
    e.add_argument("--out", type=Path, default=DEFAULT_BUNDLE)
    e.add_argument("--prefix", default=DEFAULT_PREFIX)
    e.add_argument("--synthetic-ua", nargs="+", default=list(DEFAULT_SYNTHETIC_UA))
    i = sub.add_parser("import", help="файл выгрузки → боевая БД")
    i.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    i.add_argument("--owner-email", required=True,
                   help="владелец методик и кампаний (супервизор/админ на проде)")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--catalog", action="store_true",
                   help="показать демо-методики в каталоге студентов (по умолчанию campaign_only)")
    i.add_argument("--keep-status", action="store_true",
                   help="оставить кампании открытыми, как на dev (по умолчанию закрываются)")
    args = p.parse_args(argv)
    try:
        if args.cmd == "export":
            do_export(args.out, args.prefix, tuple(args.synthetic_ua))
        else:
            do_import(json.loads(args.bundle.read_text(encoding="utf-8")), args.owner_email,
                      dry_run=args.dry_run, catalog=args.catalog, keep_status=args.keep_status)
    except (BundleError, RuntimeError, FileNotFoundError) as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Unit: чистые функции scripts/migrate_demo_campaigns.py и сама выгрузка.

Без БД: фильтр синтетики, сопоставление ответов по (№ вопроса, № варианта),
сверка шкал, проверка метки выгрузки; закоммиченный файл выгрузки не содержит
не синтетических участников и согласован внутри.
"""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_demo_campaigns.py"
spec = importlib.util.spec_from_file_location("migrate_demo_campaigns", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BUNDLE = SCRIPT.parent / "data" / "demo_campaigns_bundle.json"


def test_split_synthetic_drops_foreign_user_agents():
    rows = [{"user_agent": "mindcare-demo-generator"}, {"user_agent": "Mozilla/5.0 Chrome"},
            {"user_agent": None}, {"user_agent": "Python-urllib/3.13"}]
    keep, dropped = mod.split_synthetic(rows, mod.DEFAULT_SYNTHETIC_UA)
    assert [r["user_agent"] for r in keep] == ["mindcare-demo-generator", "Python-urllib/3.13"]
    assert dropped == 2


def test_answers_to_ids_maps_by_orders():
    qmap = {1: 10, 2: 20}
    omap = {(1, 1): 101, (1, 2): 102, (2, 1): 201}
    assert mod.answers_to_ids([[1, 2], [2, 1]], qmap, omap) == [
        {"question_id": 10, "option_id": 102}, {"question_id": 20, "option_id": 201}]


def test_answers_to_ids_rejects_unknown_pair():
    with pytest.raises(mod.BundleError):
        mod.answers_to_ids([[1, 9]], {1: 10}, {(1, 1): 101})
    with pytest.raises(mod.BundleError):
        mod.answers_to_ids([[3, 1]], {1: 10}, {(1, 1): 101})


def test_scales_match_ignores_order_and_detects_diff():
    computed = [{"scale_name": "B", "score": 3, "max_score": 9},
                {"scale_name": "A", "score": 1, "max_score": 5}]
    assert mod.scales_match([["A", 1, 5], ["B", 3, 9]], computed)
    assert not mod.scales_match([["A", 2, 5], ["B", 3, 9]], computed)
    assert not mod.scales_match([["A", 1, 5]], computed)


def test_validate_bundle_requires_synthetic_flag_and_format():
    mod.validate_bundle({"format_version": 1, "synthetic": True})
    with pytest.raises(mod.BundleError):
        mod.validate_bundle({"format_version": 1, "synthetic": False})
    with pytest.raises(mod.BundleError):
        mod.validate_bundle({"format_version": 2, "synthetic": True})
    with pytest.raises(mod.BundleError):
        mod.validate_bundle({"format_version": 1})


@pytest.mark.skipif(not BUNDLE.exists(), reason="выгрузка не создана")
def test_committed_bundle_is_consistent_synthetic():
    b = json.loads(BUNDLE.read_text(encoding="utf-8"))
    mod.validate_bundle(b)
    counts = {c["title"]: len(c["responses"]) for c in b["campaigns"]}
    assert counts["Демо: ИТО, 100 студентов (синтетические данные)"] == 100
    assert all(c["title"].startswith("Демо:") for c in b["campaigns"])
    known = {t["uuid"] for t in b["tests"]} | set(b["profile_tests"])
    assert all(c["test_uuid"] in known for c in b["campaigns"])
    keys = [r["submission_key"] for c in b["campaigns"] for r in c["responses"]]
    assert len(keys) == len(set(keys))
    for c in b["campaigns"]:
        for r in c["responses"]:
            assert r["answers"] and r["scales"]

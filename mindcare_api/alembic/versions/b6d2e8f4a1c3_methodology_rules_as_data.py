"""methodology_rules_as_data

ADR-037: правила обработки методики как данные.

tests:
  - scoring_rules JSONB NULL — правила ScoringRulesV1 (шкалы, уровни,
    достоверность, типы, инструкция); схему проверяет приложение;
  - lineage_uuid UUID NOT NULL — общий для версий одной методики
    (backfill = tests.uuid) + индекс ix_tests_lineage_uuid;
  - superseded_at TIMESTAMPTZ NULL — опубликована более новая версия;
  - CHECK ck_tests_scoring_profile удаляется: профиль больше не выбирает
    код обработки; колонка scoring_profile остаётся (код её не читает).
test_results:
  - rule_summary JSONB NULL — снимок {is_valid, types} на момент отправки.

Data: тестам с scoring_profile = 'ito_sobchik' записываются правила ИТО.
Значения зафиксированы здесь (не импортом модуля приложения), чтобы миграция
не менялась вместе с кодом.

downgrade — fail-closed, если есть правила у теста без профиля, несколько
версий одной методики или заполненные снимки rule_summary. STRICT.

Revision ID: b6d2e8f4a1c3
Revises: a3e7c1f9d5b2
Create Date: 2026-11-06
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b6d2e8f4a1c3"
down_revision: Union[str, None] = "a3e7c1f9d5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ITO_RULES = json.loads(r"""
{
    "version": 1,
    "instruction": "Прочитайте каждое утверждение и выберите «Да», если согласны с ним, или «Нет», если не согласны. Отвечайте искренне: правильных и неправильных ответов нет.",
    "scales": [
        {
            "code": "L",
            "label": "L Ложь",
            "main": false
        },
        {
            "code": "F",
            "label": "F Аггравация",
            "main": false
        },
        {
            "code": "IV",
            "label": "IV Ригидность",
            "main": true
        },
        {
            "code": "II",
            "label": "II Спонтанность",
            "main": true
        },
        {
            "code": "VI",
            "label": "VI Сензитивность",
            "main": true
        },
        {
            "code": "VII",
            "label": "VII Тревожность",
            "main": true
        },
        {
            "code": "VIII",
            "label": "VIII Лабильность",
            "main": true
        },
        {
            "code": "I",
            "label": "I Экстраверсия",
            "main": true
        },
        {
            "code": "III",
            "label": "III Агрессивность",
            "main": true
        },
        {
            "code": "V",
            "label": "V Интроверсия",
            "main": true
        }
    ],
    "levels": [
        {
            "code": "low",
            "label": "Гипоэмотивность, плохое самопонимание или неоткровенность",
            "min": 0,
            "max": 2
        },
        {
            "code": "norm",
            "label": "Норма",
            "min": 3,
            "max": 4
        },
        {
            "code": "accent",
            "label": "Акцентуированные черты",
            "min": 5,
            "max": 7
        },
        {
            "code": "maladaptive",
            "label": "Дезадаптирующие свойства",
            "min": 8,
            "max": 9
        }
    ],
    "validity": {
        "scales": [
            {
                "code": "L",
                "max_valid": 5
            },
            {
                "code": "F",
                "max_valid": 5
            }
        ],
        "invalid_mark": "недостоверно"
    },
    "types": {
        "threshold": 8,
        "items": [
            {
                "name": "Дезадаптивно-интровертированный, суицидальный риск",
                "scales": [
                    "VII",
                    "V",
                    "F"
                ]
            },
            {
                "name": "Социально активный, ранимый",
                "scales": [
                    "I",
                    "VI"
                ]
            },
            {
                "name": "Тревожно-агрессивный, тенденция нападения, в том числе с антисоциальной тенденцией",
                "scales": [
                    "VII",
                    "I",
                    "III",
                    "II"
                ]
            },
            {
                "name": "Тревожно-чувствительный, виктимный, суицидальный риск",
                "scales": [
                    "VII",
                    "VI",
                    "VIII"
                ]
            },
            {
                "name": "Защитно-агрессивный, конфликтный",
                "scales": [
                    "II",
                    "III",
                    "IV",
                    "V"
                ]
            },
            {
                "name": "Неуравновешенный",
                "scales": [
                    "VIII",
                    "III"
                ]
            }
        ]
    }
}
""")


def upgrade() -> None:
    op.add_column("tests", sa.Column(
        "scoring_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("tests", sa.Column(
        "lineage_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tests", sa.Column(
        "superseded_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE tests SET lineage_uuid = uuid")
    op.alter_column("tests", "lineage_uuid", nullable=False)
    op.create_index("ix_tests_lineage_uuid", "tests", ["lineage_uuid"])
    op.drop_constraint("ck_tests_scoring_profile", "tests", type_="check")

    op.add_column("test_results", sa.Column(
        "rule_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    conn = op.get_context().connection
    conn.execute(
        sa.text("UPDATE tests SET scoring_rules = CAST(:rules AS jsonb)"
                " WHERE scoring_profile = 'ito_sobchik'"),
        {"rules": json.dumps(ITO_RULES, ensure_ascii=False)},
    )


def downgrade() -> None:
    conn = op.get_context().connection
    # Fail-closed ДО изменений. Только количества — без id и содержимого.
    custom = conn.execute(sa.text(
        "SELECT COUNT(*) FROM tests"
        " WHERE scoring_rules IS NOT NULL AND scoring_profile IS NULL"
    )).scalar()
    if custom:
        raise RuntimeError(
            "Cannot downgrade b6d2e8f4a1c3: "
            f"{custom} test(s) have scoring rules without a legacy profile; "
            "dropping scoring_rules would silently erase their processing rules."
        )
    versions = conn.execute(sa.text(
        "SELECT COUNT(*) - COUNT(DISTINCT lineage_uuid) FROM tests"
    )).scalar()
    if versions:
        raise RuntimeError(
            "Cannot downgrade b6d2e8f4a1c3: "
            f"{versions} extra methodology version(s) exist; version links "
            "would be lost."
        )
    snapshots = conn.execute(sa.text(
        "SELECT COUNT(*) FROM test_results WHERE rule_summary IS NOT NULL"
    )).scalar()
    if snapshots:
        raise RuntimeError(
            "Cannot downgrade b6d2e8f4a1c3: "
            f"{snapshots} test result(s) have rule_summary snapshots."
        )
    bad_profile = conn.execute(sa.text(
        "SELECT COUNT(*) FROM tests WHERE scoring_profile IS NOT NULL"
        " AND scoring_profile NOT IN ('ito_sobchik')"
    )).scalar()
    if bad_profile:
        raise RuntimeError(
            "Cannot downgrade b6d2e8f4a1c3: "
            f"{bad_profile} test(s) have an unknown scoring_profile."
        )

    op.drop_column("test_results", "rule_summary")
    op.create_check_constraint(
        "ck_tests_scoring_profile", "tests",
        "scoring_profile IS NULL OR scoring_profile IN ('ito_sobchik')",
    )
    op.drop_index("ix_tests_lineage_uuid", table_name="tests")
    op.drop_column("tests", "superseded_at")
    op.drop_column("tests", "lineage_uuid")
    op.drop_column("tests", "scoring_rules")

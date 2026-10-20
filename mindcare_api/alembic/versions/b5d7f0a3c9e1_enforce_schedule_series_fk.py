"""enforce_schedule_series_fk

Stage 5C-0C — enforcement-шаг expand/contract: добавляет и валидирует FK
`schedule_rules.series_id` / `schedule_breaks.series_id` → `schedule_series.series_uuid`.

Порядок деплоя (обязателен, см. план 5C §14.2):
  1. 5C-0A (a1c4e8b2f7d3) — CREATE TABLE schedule_series + backfill, БЕЗ FK;
  2. деплой совместимого приложения (5C-0B) — все три генератора series_id
     (create_schedule_rules_bulk / create_schedule_series /
     create_schedule_breaks_bulk) вставляют identity ДО rules/breaks;
  3. ЭТА ревизия — повторный backfill + preflight + FK.

Повторный backfill здесь ОБЯЗАТЕЛЕН: между шагами 1 и 2 старая версия приложения
могла создать серии без identity-строк. Без этого VALIDATE CONSTRAINT упал бы на
«сиротах». Backfill идемпотентен (ON CONFLICT DO NOTHING) и использует тот же
fail-closed preflight по единственности владельца серии, что и 5C-0A.

ADD CONSTRAINT ... NOT VALID + отдельный VALIDATE CONSTRAINT — чтобы не держать
сильную блокировку на проверке существующих строк (NOT VALID берёт короткий
SHARE ROW EXCLUSIVE, VALIDATE — более слабый SHARE UPDATE EXCLUSIVE).

Nullable legacy `series_id` остаётся допустимым: FK не срабатывает на NULL.
Новые колонки НЕ добавляются — FK строится на существующих UUID-колонках.

downgrade — FAIL-CLOSED: снятие FK запрещено, если schedule_series уже
использовалась как audit target (есть строки audit_log с
entity_type='schedule_series'). Иначе последующий DROP TABLE в 5C-0A.downgrade
пересоздал бы identity с другими SERIAL id и исторический append-only аудит стал
бы ссылаться на неверные серии. Проверка стоит ДО DROP CONSTRAINT, поэтому при
отказе оба FK остаются валидными (транзакционный DDL PostgreSQL).

Revision ID: b5d7f0a3c9e1
Revises: a1c4e8b2f7d3
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5d7f0a3c9e1"
down_revision: Union[str, Sequence[str], None] = "a1c4e8b2f7d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_RULES = "fk_schedule_rules_series"
FK_BREAKS = "fk_schedule_breaks_series"

# Фиксированные диагностики: без UUID / id / ПДн / SQL / значений.
_ERR_OWNERSHIP = (
    "schedule series backfill aborted: inconsistent psychologist ownership "
    "for at least one series"
)
_ERR_AUDIT_REFS = (
    "schedule_series fk downgrade aborted: audit_log already references "
    "schedule_series as an entity target"
)
_ERR_IDENTITY_OWNER = (
    "schedule series fk enforcement aborted: existing identity owner does not "
    "match the owner of its schedule rows"
)

_SERIES_SOURCE = """
    SELECT series_id, psychologist_id, created_at
      FROM schedule_rules  WHERE series_id IS NOT NULL
    UNION ALL
    SELECT series_id, psychologist_id, created_at
      FROM schedule_breaks WHERE series_id IS NOT NULL
"""


def _assert_consistent_ownership(conn) -> None:
    conflict = conn.execute(sa.text(f"""
        SELECT 1
          FROM ({_SERIES_SOURCE}) s
         GROUP BY series_id
        HAVING COUNT(DISTINCT psychologist_id) > 1
         LIMIT 1
    """)).first()
    if conflict is not None:
        raise RuntimeError(_ERR_OWNERSHIP)


def _backfill(conn) -> None:
    """Идемпотентно добирает серии, созданные в окне совместимости (между 5C-0A
    и деплоем 5C-0B). MIN(psychologist_id) детерминирован, т.к. preflight уже
    доказал единственность значения в пределах серии.

    created_at источников NULLABLE → COALESCE(..., CURRENT_TIMESTAMP): это
    техническое время создания identity, не юридическое время бизнес-события и не
    audit timestamp.
    """
    conn.execute(sa.text(f"""
        INSERT INTO schedule_series (series_uuid, psychologist_id, created_at)
        SELECT series_id, MIN(psychologist_id),
               COALESCE(MIN(created_at), CURRENT_TIMESTAMP)
          FROM ({_SERIES_SOURCE}) s
         GROUP BY series_id
        ON CONFLICT (series_uuid) DO NOTHING
    """))


def _assert_identity_matches_children(conn) -> None:
    """Fail-closed: владелец СУЩЕСТВУЮЩЕЙ identity-строки обязан совпадать с
    владельцем её дочерних rules/breaks.

    `ON CONFLICT DO NOTHING` в backfill'е молча пропускает уже существующие
    строки, поэтому расхождение (в т.ч. неожиданный NULL-владелец при наличии
    дочерних строк) не было бы замечено и «зацементировалось» бы навсегда FK.
    `IS DISTINCT FROM` корректно ловит NULL-случай.
    """
    mismatch = conn.execute(sa.text(f"""
        SELECT 1
          FROM (
            SELECT series_id, MIN(psychologist_id) AS expected_owner
              FROM ({_SERIES_SOURCE}) s
             GROUP BY series_id
          ) agg
          JOIN schedule_series ss ON ss.series_uuid = agg.series_id
         WHERE ss.psychologist_id IS DISTINCT FROM agg.expected_owner
         LIMIT 1
    """)).first()
    if mismatch is not None:
        raise RuntimeError(_ERR_IDENTITY_OWNER)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Догнать окно совместимости: preflight → идемпотентный backfill.
    _assert_consistent_ownership(conn)
    _backfill(conn)

    # 2. Проверить, что уже существовавшие identity-строки согласованы со своими
    #    дочерними rules/breaks (ON CONFLICT DO NOTHING их не обновляет).
    #    Строго ДО ADD CONSTRAINT: иначе FK «зацементирует» расхождение.
    _assert_identity_matches_children(conn)

    # 3. FK без немедленной проверки существующих строк (короткая блокировка).
    op.execute(
        f"ALTER TABLE schedule_rules ADD CONSTRAINT {FK_RULES} "
        "FOREIGN KEY (series_id) REFERENCES schedule_series(series_uuid) "
        "NOT VALID"
    )
    op.execute(
        f"ALTER TABLE schedule_breaks ADD CONSTRAINT {FK_BREAKS} "
        "FOREIGN KEY (series_id) REFERENCES schedule_series(series_uuid) "
        "NOT VALID"
    )

    # 4. Валидация отдельным шагом (более слабая блокировка).
    op.execute(f"ALTER TABLE schedule_rules VALIDATE CONSTRAINT {FK_RULES}")
    op.execute(f"ALTER TABLE schedule_breaks VALIDATE CONSTRAINT {FK_BREAKS}")


def downgrade() -> None:
    conn = op.get_bind()
    # FAIL-CLOSED ДО DROP CONSTRAINT: при отказе оба FK остаются валидными.
    refs = conn.execute(sa.text(
        "SELECT 1 FROM audit_log WHERE entity_type = 'schedule_series' LIMIT 1"
    )).first()
    if refs is not None:
        raise RuntimeError(_ERR_AUDIT_REFS)

    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.execute(f"ALTER TABLE schedule_breaks DROP CONSTRAINT {FK_BREAKS}")
    op.execute(f"ALTER TABLE schedule_rules DROP CONSTRAINT {FK_RULES}")

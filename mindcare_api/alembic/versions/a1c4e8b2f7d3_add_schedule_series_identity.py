"""add_schedule_series_identity

Stage 5C-0A — identity-таблица `schedule_series` + fail-closed идемпотентный
backfill. **FK НЕ добавляются** (это делает 5C-0C после деплоя совместимого
application writer'а — см. expand/contract в 5C-0C).

Зачем: у расписания-серии нет целочисленной идентичности — `series_id` это
nullable UUID-группировка в `schedule_rules`/`schedule_breaks`, а
`audit_log.entity_id` имеет тип INTEGER. `schedule_series.id` даёт стабильный
integer target для audit-событий Stage 5C-1.

Дизайн:
  - состояние серии НЕ дублируется: is_active / effective_from / effective_until /
    auto_extend остаются в schedule_rules/schedule_breaks (единственный источник
    истины). Таблица несёт только идентичность и владение;
  - `created_by` НЕ хранится: ScheduleBreak такой колонки не имеет, поэтому для
    break-only серий значение недоступно; уведомления автопродления продолжают
    использовать ScheduleRule.created_by;
  - psychologist_id NULLABLE + ON DELETE SET NULL (НЕ CASCADE): удаление
    пользователя не должно уничтожать identity-строку, на которую ссылается
    append-only audit_log. Политика проекта — soft-delete, физического удаления
    User нет; SET NULL снимает латентный риск;
  - business delete у schedule_series отсутствует — строки не удаляются
    приложением.

Backfill (fail-closed, идемпотентный):
  - источники: schedule_rules ∪ schedule_breaks, где series_id IS NOT NULL.
    break-only серии реальны: create_schedule_breaks_bulk генерирует собственный
    series_id и не создаёт rules;
  - preflight: один series_id обязан соответствовать РОВНО одному psychologist_id.
    При расхождении миграция падает с фиксированной диагностикой без UUID/ПДн/
    значений. Разрешение конфликта произвольным MIN/MAX запрещено;
  - series_id IS NULL игнорируется (серию не образует);
  - created_at = MIN(created_at) по строкам серии (детерминированный агрегат);
  - ON CONFLICT (series_uuid) DO NOTHING — повторный прогон безопасен (нужно для
    5C-0C, который добирает серии, созданные в окне совместимости).

downgrade — FAIL-CLOSED: DROP TABLE запрещён, если schedule_series уже
использовалась как audit target (есть строки audit_log с
entity_type='schedule_series'). Пересоздание таблицы выдало бы другие SERIAL id, и
исторический append-only аудит стал бы ссылаться на неверные серии. Миграция
технически обратима ДО начала audit-writes и намеренно необратима после.

Revision ID: a1c4e8b2f7d3
Revises: f2a9c4e7b1d8
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e8b2f7d3"
down_revision: Union[str, Sequence[str], None] = "f2a9c4e7b1d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Фиксированные диагностики: без UUID / id / ПДн / SQL / значений.
_ERR_OWNERSHIP = (
    "schedule series backfill aborted: inconsistent psychologist ownership "
    "for at least one series"
)
_ERR_AUDIT_REFS = (
    "schedule_series downgrade aborted: audit_log already references "
    "schedule_series as an entity target"
)

# Объединение источников серий. UNION ALL — для агрегатов backfill'а;
# psychologist_id в обеих таблицах NOT NULL, поэтому MIN(...) не даёт NULL.
_SERIES_SOURCE = """
    SELECT series_id, psychologist_id, created_at
      FROM schedule_rules  WHERE series_id IS NOT NULL
    UNION ALL
    SELECT series_id, psychologist_id, created_at
      FROM schedule_breaks WHERE series_id IS NOT NULL
"""


def _assert_consistent_ownership(conn) -> None:
    """Fail-closed preflight: один series_id → ровно один psychologist_id."""
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
    """Идемпотентный backfill. MIN(psychologist_id) детерминирован ТОЛЬКО потому,
    что preflight уже доказал единственность значения в пределах серии.

    created_at в schedule_rules/schedule_breaks NULLABLE, поэтому MIN(created_at)
    может быть NULL и нарушил бы NOT NULL identity-строки → COALESCE(...,
    CURRENT_TIMESTAMP). Это техническое время создания identity, НЕ юридическое
    время бизнес-события: в audit metadata оно не попадает и как audit timestamp
    не используется.
    """
    conn.execute(sa.text(f"""
        INSERT INTO schedule_series (series_uuid, psychologist_id, created_at)
        SELECT series_id, MIN(psychologist_id),
               COALESCE(MIN(created_at), CURRENT_TIMESTAMP)
          FROM ({_SERIES_SOURCE}) s
         GROUP BY series_id
        ON CONFLICT (series_uuid) DO NOTHING
    """))


def upgrade() -> None:
    op.create_table(
        "schedule_series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "series_uuid", sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "psychologist_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("series_uuid", name="uq_schedule_series_uuid"),
    )

    conn = op.get_bind()
    _assert_consistent_ownership(conn)   # fail-closed ДО вставки
    _backfill(conn)


def downgrade() -> None:
    conn = op.get_bind()
    # FAIL-CLOSED: append-only audit не переписывается и id не перенумеровываются.
    refs = conn.execute(sa.text(
        "SELECT 1 FROM audit_log WHERE entity_type = 'schedule_series' LIMIT 1"
    )).first()
    if refs is not None:
        raise RuntimeError(_ERR_AUDIT_REFS)

    # STRICT: без IF EXISTS — рассинхрон схемы должен упасть, а не замаскироваться.
    op.drop_table("schedule_series")

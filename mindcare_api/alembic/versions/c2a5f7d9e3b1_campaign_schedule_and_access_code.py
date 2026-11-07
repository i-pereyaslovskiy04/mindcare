"""campaign_schedule_and_access_code

ТЗ редактора методик, этап 2, §6: сроки и кодовое слово ссылки кампании.

test_campaigns:
  - opens_at  TIMESTAMPTZ NULL — до этого времени анкета не открывается;
  - closes_at TIMESTAMPTZ NULL — после него ссылка ведёт себя как закрытая
    кампания (status в БД сам не меняется);
  - CHECK ck_test_campaigns_schedule_order: opens_at < closes_at, если заданы оба;
  - access_code_hash TEXT NULL — bcrypt кодового слова (открытый текст нигде
    не хранится) + CHECK формата bcrypt ($2a$/$2b$/$2y$).

Backfill нет: у существующих кампаний сроков и кода нет — поведение прежнее.

downgrade — fail-closed, если у какой-либо кампании заданы сроки или кодовое
слово: молчаливое удаление открыло бы ссылку без ограничений. STRICT.

Revision ID: c2a5f7d9e3b1
Revises: b6d2e8f4a1c3
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2a5f7d9e3b1"
down_revision: Union[str, None] = "b6d2e8f4a1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_campaigns",
                  sa.Column("opens_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("test_campaigns",
                  sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("test_campaigns",
                  sa.Column("access_code_hash", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_test_campaigns_schedule_order", "test_campaigns",
        "opens_at IS NULL OR closes_at IS NULL OR opens_at < closes_at",
    )
    op.create_check_constraint(
        "ck_test_campaigns_access_code_hash_format", "test_campaigns",
        "access_code_hash IS NULL OR access_code_hash ~ '^\\$2[aby]\\$[0-9]{2}\\$.{53}$'",
    )


def downgrade() -> None:
    conn = op.get_context().connection
    restricted = conn.execute(sa.text(
        "SELECT COUNT(*) FROM test_campaigns WHERE opens_at IS NOT NULL"
        " OR closes_at IS NOT NULL OR access_code_hash IS NOT NULL"
    )).scalar()
    if restricted:
        raise RuntimeError(
            "Cannot downgrade c2a5f7d9e3b1: "
            f"{restricted} campaign(s) have a schedule or an access code; "
            "dropping them would open the links without restrictions."
        )
    op.drop_constraint("ck_test_campaigns_access_code_hash_format", "test_campaigns",
                       type_="check")
    op.drop_constraint("ck_test_campaigns_schedule_order", "test_campaigns", type_="check")
    op.drop_column("test_campaigns", "access_code_hash")
    op.drop_column("test_campaigns", "closes_at")
    op.drop_column("test_campaigns", "opens_at")

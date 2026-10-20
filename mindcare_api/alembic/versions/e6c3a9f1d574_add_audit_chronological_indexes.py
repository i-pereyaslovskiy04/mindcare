"""add_audit_chronological_indexes

Stage 8 (read-only admin viewer журналов): хронологические индексы трёх
audit-таблиц.

Проблема. PRIMARY KEY партиционированных журналов — составной `(id, created_at)`
(требование PostgreSQL: ключ партиционирования обязан входить в PK). Такой
индекс упорядочен по `id`, поэтому лента «последние события за период»
(`WHERE created_at >= :a AND created_at < :b ORDER BY created_at DESC, id DESC`)
им не обслуживается: планировщику остаются seq scan партиций и внешняя
сортировка. Существующие индексы ведут по другому первому столбцу
(`user_id` / `event_type` / `outcome` / `ip_address` / `actor_id` / `table_name`
/ `operation`) и для чистого хронологического окна тоже бесполезны.

Решение — по одному индексу `(created_at, id)` на каждый журнал. Порядок
столбцов повторяет ORDER BY эндпоинтов, поэтому индекс даёт и отсечение по
периоду, и готовую сортировку с детерминированным tie-break по `id`. Отдельные
DESC-варианты не нужны: B-tree сканируется в обе стороны.

Все три таблицы — RANGE-partitioned по `created_at`. `CREATE INDEX` на parent
создаёт partitioned index, который PostgreSQL автоматически материализует на
всех существующих партициях и на каждой будущей (`PARTITION OF` наследует
индексы). Поэтому `scripts/ensure_audit_partitions.py` править не нужно, а
`DROP INDEX` на parent каскадно снимает и дочерние индексы.

`CONCURRENTLY` для partitioned table PostgreSQL не поддерживает: миграция берёт
короткую, но блокирующую запись в журналы паузу и строит индексы по всем
партициям. На заполненной базе окно планировать заранее (см. handoff Stage 8).

downgrade — STRICT (без `IF EXISTS`), как и остальные audit-миграции проекта:
schema drift должен ронять миграцию, а не маскироваться. Он снимает ТОЛЬКО три
индекса этой ревизии; `idx_audit_outcome`, `idx_auth_ip`, `idx_dcl_table` и
прочие остаются нетронутыми. Данные миграция не меняет ни в одну сторону.

Revision ID: e6c3a9f1d574
Revises: c8e2b5f7a3d1
Create Date: 2026-08-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e6c3a9f1d574"
down_revision: Union[str, Sequence[str], None] = "c8e2b5f7a3d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX idx_audit_created ON audit_log (created_at, id)")
    op.execute("CREATE INDEX idx_auth_created ON auth_log (created_at, id)")
    op.execute("CREATE INDEX idx_dcl_created ON data_change_log (created_at, id)")


def downgrade() -> None:
    # STRICT и в обратном порядке: без IF EXISTS, без CASCADE.
    op.execute("DROP INDEX idx_dcl_created")
    op.execute("DROP INDEX idx_auth_created")
    op.execute("DROP INDEX idx_audit_created")

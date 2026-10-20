"""
Unit-тесты ORM-metadata для audit_log.outcome / failure_reason_code (Stage 2).

Без подключения к PostgreSQL: проверяются типы/nullable, client+server default,
CheckConstraint, Index, совместимость конструктора AuditLog(...) без outcome, и
strict-семантика downgrade миграции (отсутствие IF EXISTS).
"""
from pathlib import Path

from sqlalchemy import CheckConstraint, String

from app.db.models.audit import AuditLog

_TABLE = AuditLog.__table__


def test_outcome_column_type_and_nullable():
    col = _TABLE.c.outcome
    assert isinstance(col.type, String)
    assert col.type.length == 10
    assert col.nullable is False


def test_outcome_client_and_server_default_success():
    col = _TABLE.c.outcome
    # client default (применяется ORM на INSERT)
    assert col.default is not None
    assert col.default.arg == "success"
    # server default (DDL DEFAULT 'success')
    assert col.server_default is not None
    assert "success" in str(col.server_default.arg)


def test_failure_reason_code_column():
    col = _TABLE.c.failure_reason_code
    assert isinstance(col.type, String)
    assert col.type.length == 100
    assert col.nullable is True


def test_check_constraint_present():
    checks = [
        c for c in _TABLE.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_audit_outcome"
    ]
    assert len(checks) == 1
    assert "outcome" in str(checks[0].sqltext).lower()


def test_outcome_index_present():
    idx = {ix.name: ix for ix in _TABLE.indexes}
    assert "idx_audit_outcome" in idx
    cols = [c.name for c in idx["idx_audit_outcome"].columns]
    assert cols == ["outcome", "created_at"]


def test_existing_writer_without_outcome_is_compatible():
    # Старый writer не передаёт outcome — конструктор его не требует.
    row = AuditLog(event_type="x")
    assert row.event_type == "x"
    # client default применяется на INSERT, не в конструкторе → допустим None.
    assert getattr(row, "outcome", None) in (None, "success")


def test_migration_downgrade_is_strict_no_if_exists():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = list(versions.glob("*add_audit_outcome*.py"))
    assert len(matches) == 1, matches
    src = matches[0].read_text(encoding="utf-8")
    assert 'down_revision: Union[str, Sequence[str], None] = "3b46b9d94c08"' in src
    downgrade_block = src.split("def downgrade")[1]
    # Проверяем только SQL (op.execute), а не комментарии.
    exec_lines = [ln for ln in downgrade_block.splitlines() if "op.execute" in ln]
    assert exec_lines, "downgrade должен содержать op.execute"
    assert not any("IF EXISTS" in ln.upper() for ln in exec_lines)

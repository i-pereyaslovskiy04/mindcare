"""
ADR-016 (дополнение 2026-11-02) — помощник integration-тестов модерации тестов
(не тест-модуль): тело решения publish/return с ожидаемым состоянием теста,
каким его видит проверяющий (статус + updated_at из БД).
"""
import uuid

from app.db.models import Test as TestModel
from app.db.session import SessionLocal


def decision(test_uuid, **extra) -> dict:
    """{expected_status, expected_updated_at} текущего состояния теста + extra."""
    with SessionLocal() as db:
        row = db.query(TestModel.status, TestModel.updated_at).filter(
            TestModel.uuid == uuid.UUID(str(test_uuid))).one()
    return {"expected_status": row.status,
            "expected_updated_at": row.updated_at.isoformat(), **extra}

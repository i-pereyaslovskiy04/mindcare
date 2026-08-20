"""
Concurrency-тесты allowlist почтовых доменов (реальные потоки + отдельные
DB-соединения). Требуют dev PostgreSQL на head.

Проверяется:
  1. два одновременных disable не оставляют 0 активных доменов (advisory lock
     сериализует; ровно один получает 409);
  2. create, удерживающий домен (FOR SHARE), блокирует конкурентный disable
     (FOR UPDATE) до своего commit — TOCTOU закрыт.
"""

import threading
import time
import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AllowedEmailDomain
from app.email_domains import storage
from app.email_domains.errors import DomainError


@pytest.fixture
def admin_actor(client) -> int:      # client → lifespan/seed (нужна роль admin)
    """Реальный admin: writer allowlist'а fail-closed требует actor context.

    Раньше тесты звали storage с actor_id=None и после введения обязательного
    актора падали на RuntimeError ещё до конкурентной части.

    Функциональная область — autouse cleanup_test_records удаляет integ_*-записи
    ПОСЛЕ КАЖДОГО теста, поэтому переиспользованный module-scoped пользователь
    во втором тесте ронял бы audit-вставку по FK audit_log.user_id.
    """
    user = auth_storage.save_user({
        "name": "Integ CC DomainAdmin",
        "email": f"integ_cc_domadmin_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(
            b"SecurePass42!", bcrypt.gensalt()).decode(),
        "role": "admin",
    })
    return int(user["id"])


def _add(domain: str, is_active: bool = True) -> int:
    with SessionLocal() as db:
        row = AllowedEmailDomain(domain=domain, is_active=is_active)
        db.add(row)
        db.commit()
        return row.id


def _active_count() -> int:
    with SessionLocal() as db:
        return (
            db.query(AllowedEmailDomain)
            .filter(AllowedEmailDomain.is_active.is_(True))
            .count()
        )


def _disable(domain_id: int, actor_id: int):
    return storage.set_domain_state(
        domain_id=domain_id, new_is_active=False,
        comment_provided=False, new_comment=None,
        actor_id=actor_id, actor_role="admin", ip=None, user_agent=None,
    )


def test_two_concurrent_disable_keep_one_active(
    reset_email_domains, admin_actor
):
    # Оставляем ровно два активных домена (два temp), остальные — off.
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).update(
            {"is_active": False}, synchronize_session=False,
        )
        db.commit()
    id_a = _add(f"integ-cc-a-{_uuid.uuid4().hex[:8]}.ru")
    id_b = _add(f"integ-cc-b-{_uuid.uuid4().hex[:8]}.ru")
    assert _active_count() == 2

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def worker(dom_id: int, key: str):
        barrier.wait()
        try:
            _disable(dom_id, admin_actor)
            results[key] = "ok"
        except DomainError as e:
            results[key] = e.status_code

    t1 = threading.Thread(target=worker, args=(id_a, "a"))
    t2 = threading.Thread(target=worker, args=(id_b, "b"))
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    # Ровно один успех, один 409 (advisory lock сериализует, последний активный
    # отключить нельзя).
    vals = list(results.values())
    assert vals.count("ok") == 1, results
    assert vals.count(409) == 1, results
    # Система не осталась без активных доменов.
    assert _active_count() == 1


def test_create_holds_domain_blocks_concurrent_disable(
    reset_email_domains, admin_actor
):
    domain = f"integ-cc-hold-{_uuid.uuid4().hex[:8]}.ru"
    dom_id = _add(domain)  # активен; помимо него активны 11 seed → не last-active

    a_locked = threading.Event()
    a_may_commit = threading.Event()

    def holder():
        # Открывает транзакцию, берёт FOR SHARE на строке домена и держит её,
        # пока не разрешат commit.
        with SessionLocal() as db:
            storage.assert_email_domain_allowed_in_tx(db, f"user@{domain}")
            a_locked.set()
            a_may_commit.wait(timeout=10)
            db.commit()

    disabler: dict[str, object] = {}

    def disable_worker():
        try:
            _disable(dom_id, admin_actor)
            disabler["status"] = "ok"
        except DomainError as e:
            disabler["status"] = e.status_code

    th = threading.Thread(target=holder)
    th.start()
    assert a_locked.wait(timeout=10), "holder не взял FOR SHARE"

    td = threading.Thread(target=disable_worker)
    td.start()
    # Пока holder держит FOR SHARE, disable (FOR UPDATE) обязан блокироваться.
    time.sleep(0.8)
    assert "status" not in disabler, (
        "disable не должен завершиться, пока create держит FOR SHARE (TOCTOU)"
    )

    # Разрешаем holder закоммитить (домен остаётся активным) → disable разблокируется.
    a_may_commit.set()
    th.join(timeout=10)
    td.join(timeout=10)
    assert disabler.get("status") == "ok", disabler

    # Итог: домен отключён уже ПОСЛЕ commit создателя — не в обход его проверки.
    with SessionLocal() as db:
        row = db.query(AllowedEmailDomain).filter(
            AllowedEmailDomain.id == dom_id,
        ).first()
        assert row.is_active is False

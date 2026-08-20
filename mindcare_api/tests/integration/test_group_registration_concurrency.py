"""
Concurrency-тесты регистрации/отмены групповых занятий на ЖИВОЙ PostgreSQL
(реальные потоки + независимые DB-сессии).

Запуск ТОЛЬКО через Stage 1 isolated runner (scripts/isolated_test_db.py) при
безопасном TEST_DATABASE_URL.

Проверяемый инвариант (corrective Stage 5C): успех И audit-строка возникают
ровно для ОДНОГО физического перехода. Проверка в сервисе читается до
блокировки занятия и под конкуренцией устаревает, поэтому переход выполняется
условным `UPDATE … RETURNING id`:
  - две одновременные регистрации → ровно один 201 и ровно один
    `group_session_registered`; проигравший получает 409;
  - две одновременные отмены → ровно один 204 и ровно один
    `group_session_registration_cancelled`; проигравший получает 404;
  - через сервис две регистрации сериализуются блокировкой занятия, поэтому
    гонка на ВСТАВКЕ достигается отдельным тестом, вызывающим storage напрямую:
    он доходит до реального partial unique `ux_gsr_active` (факт блокировки
    подтверждается `pg_blocking_pids`), а не до сериализующего lock;
  - IntegrityError, не относящийся к `ux_gsr_active` (например FK), доменным
    конфликтом НЕ подменяется.

Проверяемый инвариант (corrective: устаревшее pre-lock состояние, второй
раунд). `student_register_group` брал `status`/`booking_enabled`/lead time/тип
встречи ОДИН РАЗ до `SELECT ... FOR UPDATE` (`storage.lock_group_session_by_uuid`)
и не перепроверял их после. Под конкуренцией supervisor мог закрыть booking,
отменить занятие, сдвинуть `starts_at` внутрь lead time или урезать `capacity`,
пока студент ждал блокировку строки, — регистрация проходила по устаревшему
состоянию и писала ложный success. Ниже — тесты, доказывающие обратное на
живой PostgreSQL: держащая транзакция реально мутирует занятие, держа лок, а
студенческий поток реально блокируется на ТОЙ ЖЕ строке (доказательство —
`pg_locks` с `NOT granted`, не таймер), и только после commit держащей
транзакции получает отказ по СВЕЖЕМУ состоянию:
  - booking_enabled → False во время ожидания лока → 422, регистрации нет,
    новой `group_session_registered` строки нет;
  - status scheduled → cancelled во время ожидания лока → 422, то же;
  - starts_at сдвигается внутрь lead time во время ожидания лока → 422, то же;
  - capacity урезается ниже фактической заполненности во время ожидания лока →
    409 «Нет свободных мест» — overbooking невозможен даже под гонкой.

Append-only журналы не очищаются — считаются строки по конкретному entity_id
(либо дельта общего count события в пределах одного теста — тесты выполняются
последовательно, без pytest-xdist, поэтому дельта детерминирована).
"""
import threading
import time
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError

from app.appointments import service as appt_service
from app.appointments import storage as appt_storage
from app.audit import Actor
from app.audit.request_context import build_request_context
from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, GroupSession, GroupSessionRegistration, MeetingType,
)

PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_user(role: str) -> int:
    suffix = _uuid.uuid4().hex[:10]
    user = auth_storage.save_user({
        "name": f"CcTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_cc_{role}_{suffix}@example.com",
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    return int(user["id"])


def _group_session() -> tuple[str, int]:
    """Групповое занятие в будущем; возвращает (uuid, id)."""
    psych = _make_user("psychologist")
    starts = (datetime.now(MOSCOW_TZ) + timedelta(hours=72)).replace(
        minute=0, second=0, microsecond=0)
    with SessionLocal() as db:
        mt = MeetingType(
            name=f"integ_cc_type_{_uuid.uuid4().hex[:6]}", duration_minutes=60,
            buffer_minutes=0, allow_in_person=False, allow_online=True,
            is_group=True, is_active=True, is_bookable=True, display_order=0,
        )
        db.add(mt)
        db.flush()
        gs = GroupSession(
            uuid=_uuid.uuid4(), meeting_type_id=mt.id, psychologist_id=psych,
            title=f"cc_{_uuid.uuid4().hex[:8]}", starts_at=starts,
            format="online", capacity=10, booking_enabled=True,
            status="scheduled",
        )
        db.add(gs)
        db.commit()
        return str(gs.uuid), gs.id


def _registration_id(gs_id: int, student_id: int):
    with SessionLocal() as db:
        return db.query(GroupSessionRegistration.id).filter(
            GroupSessionRegistration.group_session_id == gs_id,
            GroupSessionRegistration.student_id == student_id).scalar()


def _audit_count(event_type: str, entity_id: int) -> int:
    with SessionLocal() as db:
        return db.query(AuditLog).filter(
            AuditLog.event_type == event_type,
            AuditLog.entity_id == entity_id).count()


def _reg_status(reg_id: int) -> str:
    with SessionLocal() as db:
        return db.query(GroupSessionRegistration.status).filter(
            GroupSessionRegistration.id == reg_id).scalar()


def _run_concurrently(fn, n: int = 2) -> list:
    """Запустить fn в n потоках, синхронизировав старт барьером.

    Каждый поток работает в СВОЕЙ сессии: service открывает собственный
    SessionLocal(), поэтому транзакции действительно независимы.
    """
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def _worker(idx: int):
        barrier.wait()
        try:
            results[idx] = ("ok", fn())
        except Exception as exc:            # noqa: BLE001 — фиксируем исход
            results[idx] = ("err", type(exc).__name__, getattr(
                exc, "status_code", None))

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


# ─── Конкурентная регистрация ─────────────────────────────────────────────────

def test_concurrent_new_registration_one_success_one_conflict(client):
    """Две одновременные регистрации через сервис → один 201, один 409.

    Здесь транзакции сериализует `lock_group_session_by_uuid`, поэтому
    проигравшая доходит до ветки `existing`. Гонку непосредственно на индексе
    проверяет test_insert_race_reaches_partial_unique_index.
    """
    gs_uuid, gs_id = _group_session()
    student = _make_user("student")
    user = {"id": student, "is_active": True}

    results = _run_concurrently(
        lambda: appt_service.student_register_group(
            gs_uuid, user, actor_role="student")
    )

    ok = [r for r in results if r[0] == "ok"]
    err = [r for r in results if r[0] == "err"]
    assert len(ok) == 1, results          # ровно один успех
    assert len(err) == 1, results
    assert err[0][2] == 409, results      # проигравший — доменный 409

    reg_id = _registration_id(gs_id, student)
    assert reg_id is not None
    assert _reg_status(reg_id) == "registered"
    # ровно ОДНА audit-строка на один физический переход
    assert _audit_count("group_session_registered", reg_id) == 1


def test_concurrent_reactivation_one_success_one_conflict(client):
    """Гонка на РЕАКТИВАЦИИ существующей cancelled-строки."""
    gs_uuid, gs_id = _group_session()
    student = _make_user("student")
    user = {"id": student, "is_active": True}

    appt_service.student_register_group(gs_uuid, user, actor_role="student")
    reg_id = _registration_id(gs_id, student)
    appt_service.student_cancel_group(gs_uuid, user, actor_role="student")
    assert _reg_status(reg_id) == "cancelled"
    before = _audit_count("group_session_registered", reg_id)

    results = _run_concurrently(
        lambda: appt_service.student_register_group(
            gs_uuid, user, actor_role="student")
    )

    ok = [r for r in results if r[0] == "ok"]
    err = [r for r in results if r[0] == "err"]
    assert len(ok) == 1, results
    assert len(err) == 1 and err[0][2] == 409, results

    assert _reg_status(reg_id) == "registered"
    # ровно +1 строка: реактивация — один физический переход
    assert _audit_count("group_session_registered", reg_id) == before + 1


# ─── Конкурентная отмена ──────────────────────────────────────────────────────

def test_concurrent_cancellation_one_success_one_not_found(client):
    gs_uuid, gs_id = _group_session()
    student = _make_user("student")
    user = {"id": student, "is_active": True}

    appt_service.student_register_group(gs_uuid, user, actor_role="student")
    reg_id = _registration_id(gs_id, student)

    results = _run_concurrently(
        lambda: appt_service.student_cancel_group(
            gs_uuid, user, actor_role="student")
    )

    ok = [r for r in results if r[0] == "ok"]
    err = [r for r in results if r[0] == "err"]
    assert len(ok) == 1, results          # ровно одна успешная отмена
    assert len(err) == 1, results
    assert err[0][2] == 404, results      # проигравший — «регистрация не найдена»

    assert _reg_status(reg_id) == "cancelled"
    assert _audit_count(
        "group_session_registration_cancelled", reg_id) == 1


# ─── Гонка: устаревшее pre-lock состояние (corrective) ───────────────────────

def _audit_total(event_type: str) -> int:
    with SessionLocal() as db:
        return db.query(AuditLog).filter(
            AuditLog.event_type == event_type).count()


def _wait_for_lock_waiter(holder_pid: int, timeout: float = 30.0) -> bool:
    """Ждать, пока ДРУГОЙ backend (не holder_pid) реально заблокируется на
    row-level локе.

    Postgres реализует ожидание строкового лока через ожидание чужого
    `transactionid` (не через `NOT granted`-строку в `pg_locks` с
    `locktype='tuple'` — такая строка, как ни странно, показывается
    `granted=true`, потому что backend уже получил лок на СВОЙ tuple-запрос,
    а реально ждёт через отдельный запрос лока на XID держателя). Поэтому
    здесь используется `pg_stat_activity.wait_event_type='Lock'`, что и есть
    официальный сигнал ожидания лока (см. документацию PostgreSQL на
    `pg_stat_activity.wait_event`). Это доказательство, что вторая
    транзакция реально стоит на блокировке (а не разошлась с держащей
    раньше по другой ветке) — без него тест мог бы случайно проходить без
    настоящей гонки.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with SessionLocal() as probe:
            rows = probe.execute(
                sa_text(
                    "SELECT pid FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND pid <> :holder"
                ),
                {"holder": holder_pid},
            ).fetchall()
        if rows:
            return True
        time.sleep(0.05)
    return False


def _hold_lock_and_mutate(gs_id, mutate, holder_pid: dict,
                           release_event: threading.Event):
    """Держит `FOR UPDATE` на строке gs_id, применяет `mutate(gs)` (flush без
    commit), публикует свой pid и ждёт `release_event` перед commit — именно
    в этом окне студенческая транзакция должна реально ждать на блокировке.
    """
    with SessionLocal() as db:
        holder_pid["pid"] = db.execute(
            sa_text("SELECT pg_backend_pid()")).scalar()
        gs = (
            db.query(GroupSession)
            .filter(GroupSession.id == gs_id)
            .with_for_update()
            .first()
        )
        mutate(gs)
        db.flush()
        release_event.wait(30)
        db.commit()


def _run_student_register(gs_uuid, student_id, outcome: dict, key: str):
    user = {"id": student_id, "is_active": True}
    try:
        result = appt_service.student_register_group(
            gs_uuid, user, actor_role="student")
        outcome[key] = ("ok", result)
    except appt_service.AppointmentError as exc:
        outcome[key] = ("err", exc.status_code)


def _race_mutation_vs_registration(gs_uuid, gs_id, student_id, mutate) -> dict:
    """Общий сценарий гонки: держатель берёт `FOR UPDATE` и мутирует занятие
    (не коммитя), студент параллельно пытается зарегистрироваться и реально
    блокируется на ТОЙ ЖЕ строке; только после commit держателя студенческая
    транзакция получает управление и обязана увидеть СВЕЖЕЕ состояние.

    Возвращает `outcome` с ключом "student" → ("ok", dict) либо
    ("err", status_code).
    """
    holder_pid: dict = {}
    release_event = threading.Event()
    outcome: dict = {}

    th_holder = threading.Thread(
        target=_hold_lock_and_mutate,
        args=(gs_id, mutate, holder_pid, release_event),
    )
    th_holder.start()
    for _ in range(600):
        if holder_pid.get("pid"):
            break
        time.sleep(0.05)
    assert holder_pid.get("pid"), "holder-поток не взял блокировку"

    th_student = threading.Thread(
        target=_run_student_register,
        args=(gs_uuid, student_id, outcome, "student"),
    )
    th_student.start()

    assert _wait_for_lock_waiter(holder_pid["pid"]), (
        "студент не заблокировался на FOR UPDATE — гонка не достигнута"
    )

    release_event.set()
    th_holder.join(30)
    th_student.join(30)
    return outcome


def _assert_no_registration_and_no_new_audit(
    gs_id, student_id, before_audit_total
):
    with SessionLocal() as db:
        rows = db.query(GroupSessionRegistration).filter(
            GroupSessionRegistration.group_session_id == gs_id,
            GroupSessionRegistration.student_id == student_id).all()
    assert rows == []                                  # мутации не было
    assert _audit_total("group_session_registered") == before_audit_total


def test_concurrent_booking_close_rejects_pending_registration(client):
    """Supervisor закрывает booking, пока студент ждёт FOR UPDATE.

    Пре-лок проверка status/booking_enabled читалась бы «открыто» и раньше
    давала бы success по устаревшему состоянию.
    """
    gs_uuid, gs_id = _group_session()
    student = _make_user("student")

    before_audit = _audit_total("group_session_registered")
    outcome = _race_mutation_vs_registration(
        gs_uuid, gs_id, student,
        mutate=lambda gs: setattr(gs, "booking_enabled", False),
    )

    assert outcome.get("student") == ("err", 422), outcome
    _assert_no_registration_and_no_new_audit(gs_id, student, before_audit)


def test_concurrent_cancellation_rejects_pending_registration(client):
    """Занятие переводится scheduled→cancelled, пока студент ждёт FOR UPDATE."""
    gs_uuid, gs_id = _group_session()
    student = _make_user("student")

    before_audit = _audit_total("group_session_registered")
    outcome = _race_mutation_vs_registration(
        gs_uuid, gs_id, student,
        mutate=lambda gs: setattr(gs, "status", "cancelled"),
    )

    assert outcome.get("student") == ("err", 422), outcome
    _assert_no_registration_and_no_new_audit(gs_id, student, before_audit)


def test_concurrent_starts_at_move_inside_lead_time_rejects_registration(client):
    """starts_at переносится внутрь lead time, пока студент ждёт FOR UPDATE."""
    gs_uuid, gs_id = _group_session()
    student = _make_user("student")

    def _move_inside_lead_time(gs):
        gs.starts_at = datetime.now(MOSCOW_TZ) + timedelta(minutes=30)

    before_audit = _audit_total("group_session_registered")
    outcome = _race_mutation_vs_registration(
        gs_uuid, gs_id, student, mutate=_move_inside_lead_time,
    )

    assert outcome.get("student") == ("err", 422), outcome
    _assert_no_registration_and_no_new_audit(gs_id, student, before_audit)


def test_concurrent_capacity_exhaustion_rejects_registration(client):
    """capacity урезается ниже фактической заполненности, пока студент ждёт
    FOR UPDATE — overbooking невозможен даже под гонкой.
    """
    gs_uuid, gs_id = _group_session()
    other_student = _make_user("student")
    student = _make_user("student")

    # Одно место занято заранее ОБЫЧНОЙ (не гоночной) регистрацией.
    appt_service.student_register_group(
        gs_uuid, {"id": other_student, "is_active": True},
        actor_role="student",
    )
    with SessionLocal() as db:
        db.query(GroupSession).filter(GroupSession.id == gs_id).update(
            {"capacity": 2}, synchronize_session=False)
        db.commit()

    before_audit = _audit_total("group_session_registered")
    outcome = _race_mutation_vs_registration(
        gs_uuid, gs_id, student,
        mutate=lambda gs: setattr(gs, "capacity", 1),   # 1 занято → 0 свободно
    )

    assert outcome.get("student") == ("err", 409), outcome
    _assert_no_registration_and_no_new_audit(gs_id, student, before_audit)


# ─── Гонка ИМЕННО на partial unique index ────────────────────────────────────

_CTX = build_request_context(ip=None, user_agent=None)


def _wait_until_blocked(pid: int, timeout: float = 30.0) -> bool:
    """Дождаться, пока backend `pid` реально встанет на блокировку.

    Это и есть доказательство, что вторая транзакция дошла до INSERT и упёрлась
    в уникальный индекс, а не разошлась с первой раньше по другой ветке.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with SessionLocal() as probe:
            blockers = probe.execute(
                sa_text("SELECT pg_blocking_pids(:p)"), {"p": pid}).scalar()
        if blockers:
            return True
        time.sleep(0.05)
    return False


def test_insert_race_reaches_partial_unique_index(client):
    """Доходит до РЕАЛЬНОГО нарушения ux_gsr_active, а не до lock занятия.

    `student_register_group` берёт `lock_group_session_by_uuid` ДО вставки,
    поэтому через сервис две транзакции сериализуются и проигравшая уходит в
    ветку `existing` — INSERT-гонка там недостижима. Здесь storage вызывается
    напрямую из двух независимых сессий: обе видят `existing = None` (первая ещё
    не закоммичена), обе идут на INSERT, и вторая блокируется на индексе.
    """
    _gs_uuid, gs_id = _group_session()
    student = _make_user("student")
    actor = Actor.user(student, "student")

    t1_flushed = threading.Event()
    t1_release = threading.Event()
    t2_pid: dict = {}
    outcome: dict = {}

    def _t1():
        with SessionLocal() as db:
            gs = db.get(GroupSession, gs_id)
            appt_storage.register_student_group_session(
                gs, student, db, actor=actor, context=_CTX)
            t1_flushed.set()            # строка вставлена, но НЕ закоммичена
            t1_release.wait(30)
            db.commit()
            outcome["t1"] = "ok"

    def _t2():
        with SessionLocal() as db:
            t2_pid["pid"] = db.execute(
                sa_text("SELECT pg_backend_pid()")).scalar()
            gs = db.get(GroupSession, gs_id)
            try:
                appt_storage.register_student_group_session(
                    gs, student, db, actor=actor, context=_CTX)
                db.commit()
                outcome["t2"] = "ok"
            except Exception as exc:    # noqa: BLE001 — фиксируем класс исхода
                db.rollback()
                outcome["t2"] = type(exc).__name__

    th1 = threading.Thread(target=_t1)
    th1.start()
    assert t1_flushed.wait(30), "первая транзакция не дошла до flush"

    th2 = threading.Thread(target=_t2)
    th2.start()
    # ждём появления pid и фактической блокировки на индексе
    for _ in range(600):
        if t2_pid.get("pid"):
            break
        time.sleep(0.05)
    assert t2_pid.get("pid"), "вторая транзакция не стартовала"
    blocked = _wait_until_blocked(t2_pid["pid"])

    t1_release.set()
    th1.join(30)
    th2.join(30)

    assert blocked, "вторая вставка не заблокировалась — гонка не достигнута"
    assert outcome.get("t1") == "ok", outcome
    # конфликт пришёл из ux_gsr_active, а не из ветки `existing`
    assert outcome.get("t2") == "GroupRegistrationConflict", outcome

    with SessionLocal() as db:
        rows = db.query(GroupSessionRegistration).filter(
            GroupSessionRegistration.group_session_id == gs_id,
            GroupSessionRegistration.student_id == student).all()
    assert len(rows) == 1                       # индекс пропустил ровно одну
    assert rows[0].status == "registered"
    assert _audit_count("group_session_registered", rows[0].id) == 1


def test_foreign_key_violation_is_not_reported_as_conflict(client):
    """Не-ux_gsr_active IntegrityError НЕ маскируется доменным конфликтом.

    Регистрация на несуществующее занятие нарушает FK. Прежняя широкая ветка
    выдавала бы студенту «вы уже записаны» и прятала дефект.
    """
    student = _make_user("student")
    actor = Actor.user(student, "student")
    ghost = GroupSession(id=2_000_000_000)      # transient, в сессию не кладём

    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            appt_storage.register_student_group_session(
                ghost, student, db, actor=actor, context=_CTX)
        db.rollback()


def test_register_cancel_cycle_keeps_one_event_per_transition(client):
    """Полный цикл: каждая фактическая смена статуса даёт ровно одну строку."""
    gs_uuid, gs_id = _group_session()
    student = _make_user("student")
    user = {"id": student, "is_active": True}

    appt_service.student_register_group(gs_uuid, user, actor_role="student")
    reg_id = _registration_id(gs_id, student)
    appt_service.student_cancel_group(gs_uuid, user, actor_role="student")
    appt_service.student_register_group(gs_uuid, user, actor_role="student")

    assert _audit_count("group_session_registered", reg_id) == 2
    assert _audit_count("group_session_registration_cancelled", reg_id) == 1
    assert _reg_status(reg_id) == "registered"

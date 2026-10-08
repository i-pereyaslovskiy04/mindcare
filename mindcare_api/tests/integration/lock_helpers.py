"""
ADR-028 — примитивы ДЕТЕРМИНИРОВАННЫХ concurrency-тестов на реальном
PostgreSQL (не тест-модуль).

  * Gate — пауза потока в выбранной точке кода (обычно ПОСЛЕ взятия
    блокировки строки users): первый вызов обёрнутой функции сигналит
    `reached` и ждёт `release`; последующие вызовы проходят без паузы;
  * wait_for_lock_waiter — опрос pg_stat_activity, пока второй участник
    действительно не встанет в ожидание row lock (без «sleep и надежды»);
  * deadlock_count — счётчик pg_stat_database.deadlocks текущей БД;
  * run_in_thread — поток с захватом результата/исключения.

Потоки вызывают service/storage напрямую (TestClient не потокобезопасен);
у каждого вызова своя SessionLocal-транзакция.
"""
import threading
import time

from sqlalchemy import text

from app.db.session import SessionLocal

TIMEOUT = 20.0


class Gate:
    def __init__(self):
        self.reached = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self._used = False

    def wrap(self, fn):
        def _wrapper(*args, **kwargs):
            with self._lock:
                first = not self._used
                self._used = True
            if first:
                self.reached.set()
                if not self.release.wait(TIMEOUT):
                    raise AssertionError("gate was never released")
            return fn(*args, **kwargs)
        return _wrapper

    def wait_reached(self):
        assert self.reached.wait(TIMEOUT), "gated thread never reached the gate"


def lock_waiters() -> int:
    with SessionLocal() as db:
        return db.execute(text(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() "
            "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
        )).scalar()


def wait_for_lock_waiter(min_count: int = 1) -> None:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if lock_waiters() >= min_count:
            return
        time.sleep(0.02)
    raise AssertionError("no backend is waiting on a row lock")


def deadlock_count() -> int:
    with SessionLocal() as db:
        db.execute(text("SELECT pg_stat_clear_snapshot()"))
        return db.execute(text(
            "SELECT deadlocks FROM pg_stat_database "
            "WHERE datname = current_database()"
        )).scalar() or 0


class _Thread:
    def __init__(self, fn):
        self.result = None
        self._thread = threading.Thread(target=self._run, args=(fn,), daemon=True)
        self._thread.start()

    def _run(self, fn):
        try:
            self.result = ("ok", fn())
        except BaseException as exc:   # noqa: BLE001 — исход потока
            self.result = ("error", exc)

    def join(self):
        self._thread.join(TIMEOUT)
        assert not self._thread.is_alive(), "thread did not finish (deadlock?)"
        return self.result


def run_in_thread(fn) -> _Thread:
    return _Thread(fn)


def assert_no_deadlock_error(*results) -> None:
    for kind, value in results:
        if kind == "error":
            name = type(value).__name__ + " " + type(getattr(value, "orig", None)).__name__
            assert "Deadlock" not in name, value

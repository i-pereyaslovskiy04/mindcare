"""
Stage 5C-0A — round-trip migration test для identity-таблицы `schedule_series`.

ГЕЙТИНГ (как в test_audit_outcome_migration.py):
  - по умолчанию SKIPPED; запускается только при MINDCARE_MIGRATION_ROUNDTRIP=1;
  - при открытом gate нарушение безопасности — ОШИБКА, не skip:
      ENV=test, DATABASE_URL присутствует, current_database() ~ mindcare_test_<random>;
  - собственный engine/connection для проверок; DDL — через Alembic;
  - ТОЧНЫЕ revision ID (не downgrade -1);
  - после проверок БД остаётся на head;
  - _cleanup_probes() выполняется И до, И после каждого теста (идемпотентно):
    синтетическая audit_log-строка с entity_type='schedule_series' (тесты B/C)
    не должна пережить тест и заблокировать downgrade в последующих тестах
    fail-closed guard'ом; порядок запуска тестов не должен влиять на результат.

Покрывает план 5C §17:
  A. без audit-ссылок: upgrade → downgrade → upgrade проходит;
  B. после synthetic audit row с entity_type='schedule_series' downgrade
     завершается ошибкой, таблица остаётся, audit row сохраняется, диагностика не
     содержит entity_id/UUID/SQL;
  C. после отклонённого downgrade соответствие audit_log.entity_id →
     schedule_series.id не изменилось;
  + backfill: rule-only / break-only / mixed серии, series_id IS NULL игнорируется,
    fail-closed при конфликте psychologist_id, идемпотентность повторного прогона,
    SET NULL владельца не удаляет identity-строку.

Проверка `convalidated=true` для FK относится к 5C-0C (здесь FK ещё не создаются).

Отдельный запуск:
  ENV=test MINDCARE_MIGRATION_ROUNDTRIP=1 TEST_DATABASE_URL=... \
      python scripts/isolated_test_db.py -k schedule_series_migration -v
"""
import os
import re
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

REV_5C0A = "a1c4e8b2f7d3"
REV_5C0C = "b5d7f0a3c9e1"
PREV_REVISION = "f2a9c4e7b1d8"
FK_RULES = "fk_schedule_rules_series"
FK_BREAKS = "fk_schedule_breaks_series"
_TEST_DB_RE = re.compile(r"^mindcare_test_[a-z0-9]+$")
API_DIR = Path(__file__).resolve().parents[2]

# Фиксированная дата внутри гарантированной baseline-партиции audit_log.
PROBE_CREATED_AT = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
_PROBE_EVENT = "roundtrip_probe_5c0a"     # синтетический event, без ПДн

pytestmark = pytest.mark.skipif(
    os.environ.get("MINDCARE_MIGRATION_ROUNDTRIP") != "1",
    reason="round-trip migration disabled (set MINDCARE_MIGRATION_ROUNDTRIP=1)",
)


def _engine():
    return create_engine(
        os.environ["DATABASE_URL"], connect_args={"client_encoding": "utf8"}
    )


def _scalar(sql, **params):
    eng = _engine()
    try:
        with eng.connect() as c:
            return c.execute(text(sql), params).scalar()
    finally:
        eng.dispose()


def _exec(sql, **params):
    eng = _engine()
    try:
        with eng.begin() as c:
            c.execute(text(sql), params)
    finally:
        eng.dispose()


def _fetch_series(series_uuid):
    """Строка schedule_series как dict, либо None."""
    eng = _engine()
    try:
        with eng.connect() as c:
            row = c.execute(text(
                "SELECT id, series_uuid, psychologist_id, created_at "
                "FROM schedule_series WHERE series_uuid = :s"
            ), {"s": series_uuid}).mappings().first()
    finally:
        eng.dispose()
    return dict(row) if row is not None else None


def _table_exists(table: str) -> int:
    return _scalar(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = :t",
        t=table,
    )


def _alembic(action: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    if action == "upgrade":
        command.upgrade(cfg, revision)
    else:
        command.downgrade(cfg, revision)


def _real_series_audit_rows() -> int:
    """Настоящие (не probe) audit-ссылки на schedule_series в этой БД."""
    return _scalar(
        "SELECT count(*) FROM audit_log "
        "WHERE entity_type = 'schedule_series' AND event_type <> :probe",
        probe=_PROBE_EVENT,
    )


@pytest.fixture()
def safe_test_db():
    if os.environ.get("ENV") != "test":
        raise RuntimeError("roundtrip: ENV must be 'test'.")
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("roundtrip: DATABASE_URL must be present.")
    current = _scalar("SELECT current_database()")
    if not (current and _TEST_DB_RE.match(current)):
        raise RuntimeError(
            "roundtrip: current_database() must be mindcare_test_<random>."
        )
    # Round-trip требует БД БЕЗ исторических ссылок на schedule_series: обе
    # ревизии намеренно fail-closed и отказываются откатываться, если аудит уже
    # ссылается на серии. В общем прогоне такие строки создают gated-тесты
    # Stage 5C — тогда это не регрессия миграции, а несовместимый режим запуска.
    # Пропускаем ЯВНО, вместо непрозрачного падения downgrade.
    if _real_series_audit_rows():
        pytest.skip(
            "round-trip requires a pristine DB: audit_log already references "
            "schedule_series (run separately with -k schedule_series_migration)"
        )
    # Убрать остатки прерванного предыдущего synthetic-теста ДО старта — иначе
    # его audit_log-строка (entity_type='schedule_series') заблокирует downgrade
    # уже в ЭТОМ тесте, до того как мы успеем что-либо проверить. Идемпотентно.
    _cleanup_probes()
    try:
        yield
    finally:
        # Best-effort teardown: попытка вернуть БД на head выполняется, даже
        # если сам cleanup неожиданно упадёт (вложенный finally). Мы не
        # перехватываем исключение теста — pytest сообщает о нём отдельно от
        # ошибки teardown, поэтому исходный failure здесь не маскируется.
        try:
            _cleanup_probes()
        finally:
            _alembic("upgrade", REV_5C0C)


# ── synthetic fixtures (без ПДн: имена/почта синтетические и уникальные) ──────

def _make_user() -> int:
    suffix = _uuid.uuid4().hex[:10]
    eng = _engine()
    try:
        with eng.begin() as c:
            return c.execute(text(
                "INSERT INTO users (uuid, full_name, email, password_hash) "
                "VALUES (:u, :n, :e, 'x') RETURNING id"
            ), {"u": str(_uuid.uuid4()), "n": f"mig5c0a_{suffix}",
                "e": f"mig5c0a_{suffix}@example.com"}).scalar()
    finally:
        eng.dispose()


def _add_rule(psych_id: int, series_id, created_at="2026-01-02") -> None:
    _exec(
        "INSERT INTO schedule_rules "
        "(psychologist_id, day_of_week, start_time, end_time, series_id, "
        " effective_from, is_active, auto_extend, created_at) "
        "VALUES (:p, 1, '09:00', '10:00', :s, '2026-01-01', true, false, :ts)",
        p=psych_id, s=series_id, ts=created_at,
    )


def _add_break(psych_id: int, series_id, created_at="2026-01-03") -> None:
    _exec(
        "INSERT INTO schedule_breaks "
        "(psychologist_id, day_of_week, start_time, end_time, series_id, "
        " effective_from, is_active, created_at) "
        "VALUES (:p, 1, '13:00', '14:00', :s, '2026-01-01', true, :ts)",
        p=psych_id, s=series_id, ts=created_at,
    )


def _cleanup_probes() -> None:
    """Убрать синтетические данные ЭТОГО migration-test файла из одноразовой
    mindcare_test_<random> БД.

    Рабочие/dev/prod audit-журналы НИКОГДА не очищаются — append-only политика
    проекта здесь не ослабляется: это не общий DELETE FROM audit_log, а удаление
    ТОЛЬКО точных синтетических строк с event_type = _PROBE_EVENT (плюс
    created_at = PROBE_CREATED_AT для дополнительной точности совпадения) —
    их вставляет исключительно _insert_audit_row() этого файла (тесты B/C).
    Вызывается ПОСЛЕ того, как все assertions о сохранности строки после
    failed downgrade уже выполнены — удаление сохранившейся строки является
    ЗАВЕРШЕНИЕМ теста, а не подменой проверяемого append-only-поведения.

    Без этой очистки synthetic-строка с entity_type='schedule_series' навсегда
    остаётся в audit_log одноразовой БД и блокирует downgrade fail-closed guard'ом
    во ВСЕХ последующих тестах файла — независимо от их порядка.
    """
    try:
        _exec(
            "DELETE FROM audit_log WHERE event_type = :e AND created_at = :ts",
            e=_PROBE_EVENT, ts=PROBE_CREATED_AT,
        )
    except Exception:
        pass
    for sql in (
        "DELETE FROM schedule_breaks WHERE psychologist_id IN "
        "(SELECT id FROM users WHERE full_name LIKE 'mig5c0a_%')",
        "DELETE FROM schedule_rules WHERE psychologist_id IN "
        "(SELECT id FROM users WHERE full_name LIKE 'mig5c0a_%')",
        "DELETE FROM users WHERE full_name LIKE 'mig5c0a_%'",
    ):
        try:
            _exec(sql)
        except Exception:
            pass


def _insert_audit_row(entity_type: str, entity_id: int) -> None:
    _exec(
        "INSERT INTO audit_log (event_type, entity_type, entity_id, created_at) "
        "VALUES (:e, :t, :i, :ts)",
        e=_PROBE_EVENT, t=entity_type, i=entity_id, ts=PROBE_CREATED_AT,
    )


# ══════════════════════════════════════════════════════════════════════════
# A. Round-trip без audit-ссылок + backfill из обоих источников
# ══════════════════════════════════════════════════════════════════════════

def test_a_roundtrip_and_backfill_both_sources(safe_test_db):
    psych = _make_user()
    rule_only = _uuid.uuid4()
    break_only = _uuid.uuid4()
    mixed = _uuid.uuid4()

    # downgrade → создать «legacy» серии → upgrade (сработает backfill)
    _alembic("downgrade", PREV_REVISION)
    assert _table_exists("schedule_series") == 0

    _add_rule(psych, rule_only)
    _add_break(psych, break_only)                     # break-only серия реальна
    _add_rule(psych, mixed, created_at="2026-02-05")
    _add_break(psych, mixed, created_at="2026-02-01")  # MIN → 2026-02-01
    _add_rule(psych, None)                             # NULL — серию не образует

    _alembic("upgrade", REV_5C0A)
    assert _table_exists("schedule_series") == 1

    for sid in (rule_only, break_only, mixed):
        assert _scalar(
            "SELECT count(*) FROM schedule_series WHERE series_uuid = :s",
            s=sid,
        ) == 1, sid
        assert _scalar(
            "SELECT psychologist_id FROM schedule_series WHERE series_uuid = :s",
            s=sid,
        ) == psych

    # created_at детерминирован: MIN по объединению строк серии
    assert _scalar(
        "SELECT created_at::date::text FROM schedule_series "
        "WHERE series_uuid = :s", s=mixed,
    ) == "2026-02-01"

    # NULL-серия не создана: identity-строк ровно 3 для этого психолога
    assert _scalar(
        "SELECT count(*) FROM schedule_series WHERE psychologist_id = :p",
        p=psych,
    ) == 3

    # id — integer (пригоден как audit target)
    assert isinstance(_scalar(
        "SELECT id FROM schedule_series WHERE series_uuid = :s", s=rule_only
    ), int)


def test_a_backfill_idempotent_on_repeat(safe_test_db):
    """Повторный прогон backfill (нужен 5C-0C для окна совместимости) не
    создаёт дублей и не падает."""
    psych = _make_user()
    sid = _uuid.uuid4()

    _alembic("downgrade", PREV_REVISION)
    _add_rule(psych, sid)
    _alembic("upgrade", REV_5C0A)
    first_id = _scalar(
        "SELECT id FROM schedule_series WHERE series_uuid = :s", s=sid
    )

    # повторный ON CONFLICT DO NOTHING backfill тем же SQL
    _exec("""
        INSERT INTO schedule_series (series_uuid, psychologist_id, created_at)
        SELECT series_id, MIN(psychologist_id), MIN(created_at)
          FROM (
            SELECT series_id, psychologist_id, created_at
              FROM schedule_rules  WHERE series_id IS NOT NULL
            UNION ALL
            SELECT series_id, psychologist_id, created_at
              FROM schedule_breaks WHERE series_id IS NOT NULL
          ) s
         GROUP BY series_id
        ON CONFLICT (series_uuid) DO NOTHING
    """)
    assert _scalar(
        "SELECT count(*) FROM schedule_series WHERE series_uuid = :s", s=sid
    ) == 1
    assert _scalar(
        "SELECT id FROM schedule_series WHERE series_uuid = :s", s=sid
    ) == first_id      # id не перевыдан


def test_a_backfill_fail_closed_on_conflicting_ownership(safe_test_db):
    """Один series_uuid у двух психологов → миграция падает fail-closed,
    диагностика без UUID/ПДн/SQL."""
    psych_a = _make_user()
    psych_b = _make_user()
    sid = _uuid.uuid4()

    _alembic("downgrade", PREV_REVISION)
    _add_rule(psych_a, sid)
    _add_break(psych_b, sid)          # конфликт владельца той же серии

    with pytest.raises(Exception) as ei:
        _alembic("upgrade", REV_5C0A)

    msg = str(ei.value)
    assert "inconsistent psychologist ownership" in msg
    assert str(sid) not in msg                      # без UUID
    assert str(psych_a) not in msg.split()          # без id
    for token in ("SELECT", "INSERT", "@"):
        assert token not in msg

    # почистить конфликт и вернуть БД на head
    _cleanup_probes()
    _alembic("upgrade", REV_5C0A)


def test_a_owner_delete_sets_null_and_keeps_identity(safe_test_db):
    """ON DELETE SET NULL: удаление владельца не удаляет identity-строку."""
    psych = _make_user()
    sid = _uuid.uuid4()
    _alembic("downgrade", PREV_REVISION)
    _add_rule(psych, sid)
    _alembic("upgrade", REV_5C0A)

    _exec("DELETE FROM schedule_rules WHERE psychologist_id = :p", p=psych)
    _exec("DELETE FROM users WHERE id = :p", p=psych)

    assert _scalar(
        "SELECT count(*) FROM schedule_series WHERE series_uuid = :s", s=sid
    ) == 1
    assert _scalar(
        "SELECT psychologist_id FROM schedule_series WHERE series_uuid = :s",
        s=sid,
    ) is None


# ══════════════════════════════════════════════════════════════════════════
# B/C. Fail-closed downgrade при наличии audit-ссылок
# ══════════════════════════════════════════════════════════════════════════

def test_b_c_downgrade_fail_closed_preserves_identity_mapping(safe_test_db):
    psych = _make_user()
    sid = _uuid.uuid4()

    _alembic("downgrade", PREV_REVISION)
    _add_rule(psych, sid)
    _alembic("upgrade", REV_5C0A)

    series_id_int = _scalar(
        "SELECT id FROM schedule_series WHERE series_uuid = :s", s=sid
    )
    # B. synthetic audit row, ссылающийся на schedule_series как на target
    _insert_audit_row("schedule_series", series_id_int)

    with pytest.raises(Exception) as ei:
        _alembic("downgrade", PREV_REVISION)

    msg = str(ei.value)
    assert "audit_log already references" in msg
    assert str(sid) not in msg                       # без UUID
    assert str(series_id_int) not in msg.split()     # без entity_id
    for token in ("SELECT", "DROP", "@"):
        assert token not in msg

    # таблица осталась (транзакционный rollback DDL)
    assert _table_exists("schedule_series") == 1
    # audit row сохранён (append-only не переписывается)
    assert _scalar(
        "SELECT count(*) FROM audit_log "
        "WHERE event_type = :e AND entity_type = 'schedule_series'",
        e=_PROBE_EVENT,
    ) >= 1

    # C. соответствие audit_log.entity_id → schedule_series.id не изменилось
    assert _scalar(
        "SELECT id FROM schedule_series WHERE series_uuid = :s", s=sid
    ) == series_id_int
    assert _scalar(
        "SELECT count(*) FROM audit_log a "
        "JOIN schedule_series ss ON ss.id = a.entity_id "
        "WHERE a.entity_type = 'schedule_series' AND ss.series_uuid = :s",
        s=sid,
    ) >= 1


def test_b_regression_probe_cleanup_unblocks_subsequent_downgrade(safe_test_db):
    """Regression: без cleanup синтетическая audit-строка теста B/C переживала
    тест и блокировала downgrade fail-closed guard'ом во ВСЕХ последующих тестах
    файла (независимо от их порядка). Явно проверяет весь жизненный цикл:
    fail-closed срабатывает → строка сохранена ДО teardown → cleanup убирает
    ТОЛЬКО её → следующий downgrade/upgrade проходит без вмешательства."""
    psych = _make_user()
    sid = _uuid.uuid4()

    _alembic("downgrade", PREV_REVISION)
    _add_rule(psych, sid)
    _alembic("upgrade", REV_5C0C)

    series_id_int = _scalar(
        "SELECT id FROM schedule_series WHERE series_uuid = :s", s=sid
    )
    _insert_audit_row("schedule_series", series_id_int)

    # fail-closed audit test проходит
    with pytest.raises(Exception):
        _alembic("downgrade", REV_5C0A)

    # synthetic audit row действительно существует после failed downgrade,
    # ДО явного cleanup/teardown.
    assert _scalar(
        "SELECT count(*) FROM audit_log WHERE event_type = :e", e=_PROBE_EVENT,
    ) >= 1

    # Тот же cleanup, что выполнит fixture teardown — здесь вызван явно,
    # чтобы доказать: после него count по _PROBE_EVENT == 0.
    _cleanup_probes()
    assert _scalar(
        "SELECT count(*) FROM audit_log WHERE event_type = :e", e=_PROBE_EVENT,
    ) == 0

    # Непосредственно следующий downgrade/upgrade проходит без стороннего
    # вмешательства: порядок тестов больше не влияет на результат.
    _alembic("downgrade", REV_5C0A)
    _alembic("upgrade", REV_5C0C)


# ══════════════════════════════════════════════════════════════════════════
# D. Stage 5C-0C — FK enforcement (expand/contract)
# ══════════════════════════════════════════════════════════════════════════

def _fk_state(name: str):
    """(exists, convalidated) для FK-констрейнта по имени."""
    row = _engine()
    try:
        with row.connect() as c:
            res = c.execute(text(
                "SELECT convalidated FROM pg_constraint "
                "WHERE conname = :n AND contype = 'f'"
            ), {"n": name}).first()
    finally:
        row.dispose()
    return (res is not None, bool(res[0]) if res is not None else False)


def test_d_fk_created_and_validated(safe_test_db):
    _alembic("upgrade", REV_5C0C)
    for name in (FK_RULES, FK_BREAKS):
        exists, validated = _fk_state(name)
        assert exists, name
        assert validated, name          # VALIDATE CONSTRAINT реально выполнен


def test_d_fk_repeat_backfill_covers_compatibility_window(safe_test_db):
    """Серия, созданная СТАРЫМ writer'ом между 5C-0A и деплоем 5C-0B (без
    identity), должна быть добрана повторным backfill'ом в 5C-0C, иначе
    VALIDATE упал бы на сироте."""
    psych = _make_user()
    orphan = _uuid.uuid4()

    _alembic("downgrade", REV_5C0A)        # FK сняты, таблица есть
    # эмулируем старый writer: rule с series_id, но без identity-строки
    _exec("DELETE FROM schedule_series WHERE series_uuid = :s", s=orphan)
    _add_rule(psych, orphan)
    assert _scalar(
        "SELECT count(*) FROM schedule_series WHERE series_uuid = :s", s=orphan
    ) == 0

    _alembic("upgrade", REV_5C0C)          # повторный backfill + FK + VALIDATE

    assert _scalar(
        "SELECT count(*) FROM schedule_series WHERE series_uuid = :s", s=orphan
    ) == 1
    for name in (FK_RULES, FK_BREAKS):
        assert _fk_state(name) == (True, True), name


def test_d_fk_rejects_orphan_series_id(safe_test_db):
    """После enforcement вставка rule с неизвестным series_id отвергается FK."""
    from sqlalchemy.exc import IntegrityError

    psych = _make_user()
    _alembic("upgrade", REV_5C0C)
    with pytest.raises(IntegrityError):
        _add_rule(psych, _uuid.uuid4())    # identity не создана


def test_d_null_series_id_still_allowed(safe_test_db):
    """Nullable legacy series_id остаётся допустимым — FK не срабатывает на NULL."""
    psych = _make_user()
    _alembic("upgrade", REV_5C0C)
    _add_rule(psych, None)                 # не должно падать
    assert _scalar(
        "SELECT count(*) FROM schedule_rules "
        "WHERE psychologist_id = :p AND series_id IS NULL", p=psych,
    ) == 1


def test_d_alembic_check_no_drift_after_head(safe_test_db):
    """ORM metadata синхронизирована с DDL: autogenerate не должен предлагать
    создание/удаление новых FK и uq_schedule_series_uuid."""
    from alembic import command
    from alembic.config import Config
    from alembic.util.exc import AutogenerateDiffsDetected

    _alembic("upgrade", REV_5C0C)
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    try:
        command.check(cfg)
    except AutogenerateDiffsDetected as exc:
        diffs = str(exc)
        for token in (FK_RULES, FK_BREAKS, "uq_schedule_series_uuid",
                      "schedule_series"):
            assert token not in diffs, diffs


def test_d_identity_owner_mismatch_fails_closed_before_fk(safe_test_db):
    """Corrective item 2: identity уже существует с одним владельцем, а её
    дочерние строки принадлежат другому → 5C-0C падает ДО ADD CONSTRAINT;
    FK не появляются даже частично, строки не меняются."""
    psych_a = _make_user()
    psych_b = _make_user()
    sid = _uuid.uuid4()

    _alembic("downgrade", REV_5C0A)          # FK сняты, identity-таблица есть
    _exec("DELETE FROM schedule_series WHERE series_uuid = :s", s=sid)
    _exec(
        "INSERT INTO schedule_series (series_uuid, psychologist_id) "
        "VALUES (:s, :p)", s=sid, p=psych_a,
    )
    _add_rule(psych_b, sid)                  # владелец дочерней строки другой

    with pytest.raises(Exception) as ei:
        _alembic("upgrade", REV_5C0C)

    msg = str(ei.value)
    assert "existing identity owner does not match" in msg
    assert str(sid) not in msg
    assert str(psych_a) not in msg.split() and str(psych_b) not in msg.split()
    for token in ("SELECT", "INSERT", "@"):
        assert token not in msg

    # FK не созданы даже частично
    for name in (FK_RULES, FK_BREAKS):
        assert _fk_state(name) == (False, False), name
    # строки не изменены
    assert _scalar(
        "SELECT psychologist_id FROM schedule_series WHERE series_uuid = :s",
        s=sid,
    ) == psych_a
    assert _scalar(
        "SELECT count(*) FROM schedule_rules "
        "WHERE series_id = :s AND psychologist_id = :p", s=sid, p=psych_b,
    ) == 1

    # вернуть БД в согласованное состояние для fixture-teardown
    _exec("DELETE FROM schedule_rules WHERE series_id = :s", s=sid)
    _exec("DELETE FROM schedule_series WHERE series_uuid = :s", s=sid)


def test_d_null_created_at_backfills_with_not_null_value(safe_test_db):
    """Corrective item 4: created_at источников NULLABLE → COALESCE(...,
    CURRENT_TIMESTAMP); identity.created_at обязана быть NOT NULL."""
    psych = _make_user()
    rule_only = _uuid.uuid4()
    break_only = _uuid.uuid4()

    _alembic("downgrade", PREV_REVISION)
    _exec(
        "INSERT INTO schedule_rules "
        "(psychologist_id, day_of_week, start_time, end_time, series_id, "
        " effective_from, is_active, auto_extend, created_at) "
        "VALUES (:p, 1, '09:00', '10:00', :s, '2026-01-01', true, false, NULL)",
        p=psych, s=rule_only,
    )
    _exec(
        "INSERT INTO schedule_breaks "
        "(psychologist_id, day_of_week, start_time, end_time, series_id, "
        " effective_from, is_active, created_at) "
        "VALUES (:p, 1, '13:00', '14:00', :s, '2026-01-01', true, NULL)",
        p=psych, s=break_only,
    )

    _alembic("upgrade", REV_5C0C)            # не должно падать

    for sid in (rule_only, break_only):
        row = _fetch_series(sid)
        assert row is not None, sid
        assert row["created_at"] is not None, sid     # NOT NULL заполнено
        assert row["psychologist_id"] == psych, sid
        assert str(row["series_uuid"]) == str(sid)


def test_d_downgrade_from_head_fail_closed_keeps_both_fks(safe_test_db):
    """План §17 тест B: при наличии audit-ссылок downgrade падает ДО снятия FK —
    оба constraint остаются и convalidated=true."""
    psych = _make_user()
    sid = _uuid.uuid4()
    _alembic("upgrade", REV_5C0C)
    _exec(
        "INSERT INTO schedule_series (series_uuid, psychologist_id) "
        "VALUES (:s, :p)", s=sid, p=psych,
    )
    series_id_int = _scalar(
        "SELECT id FROM schedule_series WHERE series_uuid = :s", s=sid
    )
    _insert_audit_row("schedule_series", series_id_int)

    with pytest.raises(Exception) as ei:
        _alembic("downgrade", REV_5C0A)    # снятие FK

    msg = str(ei.value)
    assert "audit_log already references" in msg
    assert str(sid) not in msg and str(series_id_int) not in msg.split()
    for name in (FK_RULES, FK_BREAKS):
        assert _fk_state(name) == (True, True), name
    assert _table_exists("schedule_series") == 1

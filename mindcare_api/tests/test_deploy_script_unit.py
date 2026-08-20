"""
Статические проверки control flow `deploy.sh` (no-DB, без запуска скрипта).

Скрипт развёртывания нельзя прогнать в тестах: он ставит systemd-юниты, гасит
сервисы и мигрирует боевую БД. Но именно его fail-safe свойства ломаются молча,
поэтому они проверяются по исходнику:

  1. `bash -n` — синтаксис (на Linux/CI и в Git Bash);
  2. trap восстановления писателей ставится ДО остановки;
  3. trap снимается только ПОСЛЕ успешного запуска всех остановленных юнитов;
  4. start_writers пытается поднять каждый юнит и лишь затем возвращает провал;
  5. ошибка Alembic не маскируется `|| true`;
  6. отсутствие revision считается новой БД только после проверки пустоты;
  7. отсутствие обязательного maintenance unit-файла прерывает деплой;
  8. таймер IP-анонимизации устанавливается, но НЕ активируется без opt-in
     (Stage 7: первый прогон необратим).
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO_ROOT / "deploy.sh"
DEPLOY_DIR = REPO_ROOT / "deploy"
STAGE7_DOC = DEPLOY_DIR / "STAGE_7_DEPLOYMENT.md"
FAILURE_TEMPLATE = DEPLOY_DIR / "mindcare-maintenance-failure@.service"

AUDIT_PARTITIONED_TABLES = ("audit_log", "auth_log", "data_change_log")

MAINTENANCE_UNITS = (
    "mindcare-complete-group-sessions.service",
    "mindcare-complete-group-sessions.timer",
    "mindcare-extend-schedules.service",
    "mindcare-extend-schedules.timer",
    # Stage 7
    "mindcare-ensure-audit-partitions.service",
    "mindcare-ensure-audit-partitions.timer",
    "mindcare-anonymize-ips.service",
    "mindcare-anonymize-ips.timer",
    "mindcare-maintenance-failure@.service",
)

# Юниты Stage 7, для которых проверяется общий контракт oneshot-job'а.
STAGE7_SERVICE_UNITS = (
    "mindcare-anonymize-ips.service",
    "mindcare-ensure-audit-partitions.service",
)

IP_ANON_TIMER = "mindcare-anonymize-ips.timer"
PARTITIONS_TIMER = "mindcare-ensure-audit-partitions.timer"

# Фактические команды активации: `info "... enable --now ..."` в подсказке
# оператору — это ТЕКСТ, а не команда, и в подсчёт попадать не должен.
_ENABLE_NOW_RE = re.compile(
    r"^[ \t]*sudo systemctl enable --now (\S+)[ \t]*$", re.MULTILINE
)


@pytest.fixture(scope="module")
def src() -> str:
    assert DEPLOY_SH.is_file(), f"не найден {DEPLOY_SH}"
    return DEPLOY_SH.read_text(encoding="utf-8")


def _func_body(src: str, name: str) -> str:
    """Тело shell-функции `name() { ... }` до строки с закрывающей скобкой."""
    marker = f"\n{name}() {{\n"
    assert marker in src, f"функция {name} не найдена"
    tail = src.split(marker, 1)[1]
    end = tail.index("\n}\n")
    return tail[:end]


# ── 1. Синтаксис ─────────────────────────────────────────────────────────────

def test_bash_syntax_check_passes():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash недоступен в этом окружении")
    proc = subprocess.run(
        [bash, "-n", str(DEPLOY_SH)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_strict_mode_enabled(src):
    """`set -euo pipefail` — иначе сбой шага не остановит развёртывание."""
    assert "set -euo pipefail" in src


# ── 2-3. Порядок trap относительно stop/start ────────────────────────────────

def test_restore_trap_is_armed_before_writers_are_stopped(src):
    """Иначе die внутри stop_writers оставит уже погашенные юниты лежать."""
    arm = src.index("trap restore_writers_on_exit EXIT")
    stop = src.index("\n  stop_writers\n")
    assert arm < stop, "trap должен ставиться ДО stop_writers"


def test_trap_is_disarmed_only_after_successful_restart(src):
    """`trap - EXIT` не должен опережать проверку, что писатели поднялись."""
    guard = src.index("if ! start_writers; then")
    disarm = src.index("trap - EXIT")
    assert guard < disarm, "trap снимается раньше успешного start_writers"
    # между ними — die, т.е. при неудаче trap остаётся взведённым
    assert "die" in src[guard:disarm]


def test_no_bare_trap_on_start_writers(src):
    """Обработчиком должен быть restore_writers_on_exit, а не сам start_writers.

    Голый `trap start_writers EXIT` под `set -e` терял бы предупреждение о
    неподнятых юнитах.
    """
    assert "trap start_writers EXIT" not in src


# ── 4. start_writers не прерывается на первом сбое ───────────────────────────

def test_start_writers_tries_every_unit_then_reports_failure(src):
    body = _func_body(src, "start_writers")
    assert "local unit rc=0" in body
    assert "rc=1" in body                      # провал запоминается
    assert "return $rc" in body                # и возвращается ОБЩИМ итогом
    # запуск обёрнут в if — без него `set -e` оборвал бы цикл на первом сбое
    assert 'if sudo systemctl start "$unit"; then' in body
    assert "return 1" not in body              # ранний выход запрещён


def test_restore_handler_delegates_to_start_writers(src):
    body = _func_body(src, "restore_writers_on_exit")
    assert "start_writers" in body
    assert "warn" in body                      # частичный провал виден оператору


# ── 5. Ошибка Alembic не маскируется ─────────────────────────────────────────

def test_alembic_upgrade_failure_is_fatal(src):
    body = _func_body(src, "run_alembic_upgrade")
    assert "if ! .venv/bin/alembic upgrade head" in body
    assert "die " in body
    for line in body.splitlines():
        if "alembic upgrade" in line:
            assert "|| true" not in line, line


# ── 6. «Нет revision» ≠ «новая БД» ───────────────────────────────────────────

def test_missing_revision_requires_verified_empty_database(src):
    branch = src.split('elif [ "$CURRENT_REV" = "none" ]; then', 1)[1]
    branch = branch.split("\nelse\n", 1)[0]
    assert "user_table_count" in branch           # пустота проверяется фактически
    assert 'if [ "$EXISTING_TABLES" != "0" ]; then' in branch
    # непустая БД без revision → fail-closed, а не upgrade
    fail_closed = branch.index('!= "0"')
    upgrade = branch.index("run_alembic_upgrade")
    assert fail_closed < upgrade
    assert "die " in branch[fail_closed:upgrade]
    # недоступная БД тоже не считается пустой
    assert 'if [ -z "$EXISTING_TABLES" ]; then' in branch


def test_alembic_current_failure_is_not_treated_as_empty_db(src):
    assert 'if ! CURRENT_OUT=$(.venv/bin/alembic current 2>&1); then' in src


def test_no_systemd_refuses_existing_db_upgrade(src):
    """Без systemd простой не гарантируется — обновление существующей БД нельзя."""
    assert "if ! $SETUP_SYSTEMD; then" in src


# ── 7. Maintenance-юниты обязательны ─────────────────────────────────────────

def test_missing_maintenance_unit_aborts_deployment(src):
    block = src.split("MAINT_UNITS=(", 1)[1].split("daemon-reload", 1)[0]
    assert 'if [ ! -f "$PROJECT_DIR/deploy/$unit" ]; then' in block
    assert "die " in block
    # прежняя ветка «warn и продолжить» удалена
    assert "MAINT_OK" not in src


def test_all_declared_maintenance_units_exist_in_repo(src):
    declared = src.split("MAINT_UNITS=(", 1)[1].split(")", 1)[0]
    for unit in MAINTENANCE_UNITS:
        assert unit in declared, f"{unit} не объявлен в MAINT_UNITS"
        assert (REPO_ROOT / "deploy" / unit).is_file(), f"нет deploy/{unit}"


def test_timers_are_enabled_unconditionally(src):
    assert "systemctl enable --now mindcare-complete-group-sessions.timer" in src
    assert "systemctl enable --now mindcare-extend-schedules.timer" in src


def test_repo_units_are_retargeted_to_actual_host(src):
    """Юниты в репозитории захардкожены под референсный стенд."""
    block = src.split("MAINT_UNITS=(", 1)[1].split("daemon-reload", 1)[0]
    assert 's|/media/data2/psycho/mindcare|${PROJECT_DIR}|g' in block
    assert "User=${CURRENT_USER}" in block


# ── 8. Stage 7: установка отделена от активации ──────────────────────────────

def _enable_now_targets(src: str) -> list:
    """(позиция, юнит) для КАЖДОЙ фактической команды `enable --now`."""
    return [(m.start(), m.group(1)) for m in _ENABLE_NOW_RE.finditer(src)]


def _ip_anon_optin_span(src: str) -> tuple:
    """Границы then-ветки `if $ENABLE_IP_ANON; then ... else`."""
    start = src.index("if $ENABLE_IP_ANON; then")
    end = src.index("\n  else\n", start)
    return start, end


def test_ip_anonymization_timer_is_not_enabled_without_optin(src):
    """T32 — без флага таймер IP-анонимизации НЕ активируется.

    `enable --now` для него допустим ровно в одном месте: внутри then-ветки
    `if $ENABLE_IP_ANON`. Подсказка оператору (`info "... enable --now ..."`)
    командой не является и в выборку не попадает — см. _ENABLE_NOW_RE.
    """
    optin_start, optin_end = _ip_anon_optin_span(src)

    occurrences = [
        pos for pos, unit in _enable_now_targets(src) if unit == IP_ANON_TIMER
    ]
    assert occurrences, "команда активации таймера отсутствует вовсе"
    for pos in occurrences:
        assert optin_start < pos < optin_end, (
            "enable --now для таймера IP-анонимизации вне ветки --enable-ip-anonymization"
        )


def test_ip_anonymization_optin_flag_is_parsed_and_defaults_to_false(src):
    """T35 — флаг существует, разбирается в `case` и по умолчанию выключен."""
    assert "ENABLE_IP_ANON=false" in src
    assert "--enable-ip-anonymization) ENABLE_IP_ANON=true ;;" in src

    # default стоит ДО парсера, иначе `set -u` уронил бы скрипт без флага
    default_pos = src.index("ENABLE_IP_ANON=false")
    case_pos = src.index("--enable-ip-anonymization)")
    assert default_pos < case_pos

    # и флаг документирован в usage-шапке
    header = src.split("set -euo pipefail", 1)[0]
    assert "--enable-ip-anonymization" in header


def test_partitions_timer_is_enabled_unconditionally(src):
    """T34 — таймер партиций включается сразу: он только создаёт партиции."""
    optin_start, optin_end = _ip_anon_optin_span(src)

    occurrences = [
        pos for pos, unit in _enable_now_targets(src) if unit == PARTITIONS_TIMER
    ]
    assert occurrences, f"{PARTITIONS_TIMER} нигде не активируется"
    for pos in occurrences:
        assert not (optin_start < pos < optin_end), (
            "таймер партиций не должен зависеть от --enable-ip-anonymization"
        )


def test_stage7_units_are_installed_regardless_of_optin(src):
    """T33 — оба юнита Stage 7 ставятся всегда, независимо от флага.

    Установка (`MAINT_UNITS` + `sed` + `tee`) выполняется ДО ветвления по
    `ENABLE_IP_ANON`, поэтому отсутствие флага не оставляет стенд без файлов.
    """
    declared = src.split("MAINT_UNITS=(", 1)[1].split(")", 1)[0]
    for unit in ("mindcare-anonymize-ips.service", IP_ANON_TIMER,
                 "mindcare-ensure-audit-partitions.service", PARTITIONS_TIMER):
        assert unit in declared, f"{unit} не объявлен в MAINT_UNITS"

    install_pos = src.index("MAINT_UNITS=(")
    optin_pos = src.index("if $ENABLE_IP_ANON; then")
    assert install_pos < optin_pos


def test_operator_is_told_how_to_enable_it_later(src):
    """Без флага оператор обязан получить точный порядок действий."""
    _, optin_end = _ip_anon_optin_span(src)
    else_branch = src[optin_end:src.index("\n  fi\n", optin_end)]

    assert "--dry-run" in else_branch
    assert "STAGE_7_DEPLOYMENT.md" in else_branch
    assert f"enable --now {IP_ANON_TIMER}" in else_branch


# ── Stage 7: unit-файлы ──────────────────────────────────────────────────────

@pytest.mark.parametrize("unit", STAGE7_SERVICE_UNITS)
def test_stage7_service_units_are_oneshot_with_failure_handler(unit):
    """T22 — контракт maintenance-job'а: oneshot + OnFailure на общий шаблон."""
    text = (DEPLOY_DIR / unit).read_text(encoding="utf-8")

    assert "[Unit]" in text and "[Service]" in text and "[Install]" in text
    assert "Type=oneshot" in text
    assert f"OnFailure=mindcare-maintenance-failure@{unit}" in text
    assert "TimeoutStartSec=" in text


@pytest.mark.parametrize("unit", (IP_ANON_TIMER, PARTITIONS_TIMER))
def test_stage7_timer_units_are_well_formed(unit):
    text = (DEPLOY_DIR / unit).read_text(encoding="utf-8")

    assert "[Timer]" in text and "[Install]" in text
    assert "OnCalendar=" in text
    assert "Persistent=true" in text
    assert f"Unit={unit.replace('.timer', '.service')}" in text


def test_anonymize_unit_pins_the_retention_window():
    """Неверный `--days` стирал бы свежие IP: значение зафиксировано в юните.

    Сама функция отвергает `days < 1` (SQLSTATE 22023), но юнит не должен
    полагаться на дефолт CLI — окно ретенции является политикой.
    """
    text = (DEPLOY_DIR / "mindcare-anonymize-ips.service").read_text(
        encoding="utf-8"
    )
    exec_lines = [ln for ln in text.splitlines() if ln.startswith("ExecStart=")]
    assert len(exec_lines) == 1
    assert "scripts/anonymize_old_ips.py" in exec_lines[0]
    assert "--days 90" in exec_lines[0]
    # dry-run в таймере бессмыслен: job обязан выполнять работу
    assert "--dry-run" not in exec_lines[0]


@pytest.mark.parametrize("unit", STAGE7_SERVICE_UNITS)
def test_stage7_units_never_delete_or_drop(unit):
    """T23 — ни один Stage 7 job не удаляет строки и не трогает партиции."""
    exec_lines = [
        ln for ln in (DEPLOY_DIR / unit).read_text(encoding="utf-8").splitlines()
        if ln.startswith("ExecStart=") or ln.startswith("ExecStop=")
    ]
    joined = " ".join(exec_lines).upper()
    for forbidden in ("DROP", "DELETE", "DETACH", "TRUNCATE", "--APPLY"):
        assert forbidden not in joined, f"{unit}: {forbidden}"


def test_partitions_unit_only_creates_future_partitions():
    """Скрипт партиций вызывается без флагов, которые могли бы что-то удалить."""
    text = (DEPLOY_DIR / "mindcare-ensure-audit-partitions.service").read_text(
        encoding="utf-8"
    )
    exec_lines = [ln for ln in text.splitlines() if ln.startswith("ExecStart=")]
    assert len(exec_lines) == 1
    assert "scripts/ensure_audit_partitions.py" in exec_lines[0]
    assert "--months-ahead 24" in exec_lines[0]


# ── Stage 7: runbook ─────────────────────────────────────────────────────────

def test_stage7_runbook_requires_dry_run_before_first_live_run():
    """T36 — документ обязан требовать dry-run и ручной прогон ДО активации."""
    assert STAGE7_DOC.is_file(), f"нет {STAGE7_DOC}"
    doc = STAGE7_DOC.read_text(encoding="utf-8")

    dry_run = doc.index("--dry-run")
    live_run = doc.index("scripts/anonymize_old_ips.py --days 90\n")
    enable = doc.index(f"enable --now {IP_ANON_TIMER}")

    assert dry_run < live_run < enable, (
        "порядок в runbook должен быть: dry-run -> ручной live-прогон -> активация"
    )
    assert "необратим" in doc


def test_stage7_runbook_mentions_all_three_partitioned_parents():
    """Health-check и общее описание обязаны называть все три журнала — не
    только audit_log: обнуление/партиционирование затрагивают auth_log и
    data_change_log ровно так же."""
    doc = STAGE7_DOC.read_text(encoding="utf-8")
    for table in AUDIT_PARTITIONED_TABLES:
        assert table in doc, f"{table} не упомянут в runbook"

    # Именно в SQL health-check'а, а не только в описательном тексте выше.
    health_check = doc.split("## Мониторинг и health-check", 1)[1]
    for table in AUDIT_PARTITIONED_TABLES:
        assert table in health_check, f"{table} отсутствует в health-check SQL"


def test_stage7_runbook_health_check_uses_pg_get_expr_and_checks_four_months():
    """Health-check обязан показывать реальную границу партиции
    (`pg_get_expr`) и подтверждать покрытие текущего + трёх ближайших
    календарных месяцев (generate_series(0, 3) = 4 месяца)."""
    doc = STAGE7_DOC.read_text(encoding="utf-8")
    health_check = doc.split("## Мониторинг и health-check", 1)[1]

    assert "pg_get_expr(c.relpartbound, c.oid)" in health_check
    assert "generate_series(0, 3)" in health_check
    assert "LEFT JOIN" in health_check, (
        "без LEFT JOIN отсутствующая партиция молча пропала бы из выборки, "
        "а не осталась строкой с NULL"
    )
    assert "NULL" in health_check


def test_stage7_runbook_does_not_promise_no_locks_literally():
    """dry-run не должен описываться буквальным «без блокировок» — SELECT
    всё равно берёт обычный PostgreSQL read-lock (AccessShareLock); только
    advisory lock, write locks/мутация и запись данных в WAL отрицаются."""
    doc = STAGE7_DOC.read_text(encoding="utf-8")

    assert "ни блокировок" not in doc
    assert "без блокировок" not in doc

    dry_run_note = doc.split("# 1. Узнать объём.", 1)[1].split("\n\n", 1)[0]
    # Комментарий в bash-блоке — каждая строка начинается с "#" и перенесена
    # построчно; склеиваем и убираем маркер комментария, иначе "write locks"
    # не матчится из-за переноса строки внутри самой фразы ("без write\n#
    # locks" даёт "write # locks" после наивной склейки пробелами).
    normalized = " ".join(dry_run_note.replace("#", " ").split())
    assert "advisory lock" in normalized
    assert "write locks" in normalized
    assert "WAL" in normalized


def test_stage7_runbook_describes_deploy_sh_downtime_honestly():
    """Runbook не должен утверждать, что штатный `deploy.sh` никогда не
    останавливает приложение: для ЛЮБОЙ существующей отстающей схемы он идёт
    по общему гарантированному downtime-пути Stage 5C (не только ради Stage 7),
    а для новой пустой БД / БД уже на head простой не нужен."""
    doc = STAGE7_DOC.read_text(encoding="utf-8")
    section_a = doc.split("### A. Штатный", 1)[1].split("### B.", 1)[0]

    # Не должно быть безусловного утверждения «downtime не нужен».
    assert "downtime требует" in section_a or "downtime не требует" in section_a
    assert "не требует downtime" not in section_a.split(
        "Сама ревизия Stage 7", 1
    )[0], "безусловное «не требует downtime» до уточнения про deploy.sh"

    # Явно названы три случая и общий (не Stage-7-специфичный) downtime-путь.
    assert "новая пустая БД" in section_a
    assert "путь Stage 5C" in section_a or "downtime-пути Stage 5C" in section_a
    assert "не специфика Stage 7" in section_a or "не Stage 7" in section_a
    assert "STAGE_5C_DEPLOYMENT.md" in section_a


# ── Stage 7: общий OnFailure-обработчик ──────────────────────────────────────

def test_failure_template_execstart_is_unchanged():
    """Runtime-команда logger — вне охвата этого прохода, менять нельзя."""
    text = FAILURE_TEMPLATE.read_text(encoding="utf-8")
    exec_lines = [ln for ln in text.splitlines() if ln.startswith("ExecStart=")]
    assert exec_lines == [
        'ExecStart=/usr/bin/logger -t mindcare-maintenance -p daemon.err '
        '"FAILED unit=%i (see: journalctl -u %i)"'
    ]


def test_failure_template_is_not_scoped_to_stage_5c_only():
    """Комментарий не должен утверждать, что обработчик обслуживает только
    два скрипта Stage 5C-3 — реально к нему подключены и юниты Stage 7."""
    text = FAILURE_TEMPLATE.read_text(encoding="utf-8")

    assert "Оба скрипта Stage 5C-3 гарантируют" not in text
    # Позитивная формулировка «обслуживает только два скрипта» запрещена, но
    # корректная НЕГАЦИЯ («а не только два скрипта») обязана присутствовать —
    # наивная substring-проверка спутала бы одно с другим.
    assert "а не только два скрипта" in text
    assert "STAGE_7_DEPLOYMENT.md" in text

    for stage7_unit in ("anonymize-ips", "ensure-audit-partitions"):
        assert stage7_unit in text, f"{stage7_unit} не упомянут как подключённый job"

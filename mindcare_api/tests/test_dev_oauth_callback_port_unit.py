"""
DEV-listener для callback VK ID (no-DB).

VK ID принимает localhost в Redirect URL только на стандартных портах
(http://localhost — порт 80), а основной backend в DEV слушает :8000. Поэтому
DEV-launcher'ы (`start.ps1`, `start.sh`) поднимают второй экземпляр приложения
на :80. Здесь проверяется:

  1. решение «нужен ли listener и на каком порту» — чистая функция
     `scripts/dev_oauth_callback_port.py` (включая то, что production-подобная
     конфигурация listener НЕ требует);
  2. CLI helper'а: печатает только номер порта, код возврата всегда 0;
  3. статические свойства launcher'ов и границ: приложение само процессы не
     порождает, production-развёртывание listener не использует.

Сами launcher'ы в тестах не запускаются (они поднимают серверы).
"""
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

_API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = _API_ROOT.parent
HELPER = _API_ROOT / "scripts" / "dev_oauth_callback_port.py"
START_PS1 = REPO_ROOT / "start.ps1"
START_SH = REPO_ROOT / "start.sh"
DEPLOY_SH = REPO_ROOT / "deploy.sh"
DEPLOY_DIR = REPO_ROOT / "deploy"


def _load_helper():
    spec = importlib.util.spec_from_file_location("dev_oauth_callback_port", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _load_helper()


def _config(**over):
    values = {
        "VK_OAUTH_ENABLED": True,
        "VK_OAUTH_CLIENT_ID": "12345678",
        "VK_OAUTH_CALLBACK_BASE_URL": "http://localhost",
        "OAUTH_CALLBACK_BASE_URL": "http://localhost:8000",
    }
    values.update(over)
    return SimpleNamespace(**values)


# ── решение: нужен ли listener ───────────────────────────────────────────────

@pytest.mark.parametrize("base", [
    "http://localhost",
    "http://localhost/",
    "http://localhost:80",
    "http://127.0.0.1",
    "  http://localhost  ",
])
def test_vk_on_localhost_port_80_needs_listener(base):
    assert helper.dev_callback_listener_port(_config(VK_OAUTH_CALLBACK_BASE_URL=base)) == 80


def test_vk_disabled_needs_no_listener():
    assert helper.dev_callback_listener_port(_config(VK_OAUTH_ENABLED=False)) is None


@pytest.mark.parametrize("enabled", ["true", 1, None])
def test_only_real_true_enables_listener(enabled):
    """Не-bool «включено» (частичные объекты конфигурации) listener не включает."""
    assert helper.dev_callback_listener_port(_config(VK_OAUTH_ENABLED=enabled)) is None


@pytest.mark.parametrize("base", ["", "   ", None])
def test_vk_without_own_callback_base_needs_no_listener(base):
    """Своей базы нет — callback VK приходит на основной backend."""
    assert helper.dev_callback_listener_port(_config(VK_OAUTH_CALLBACK_BASE_URL=base)) is None


def test_config_without_vk_settings_needs_no_listener():
    assert helper.dev_callback_listener_port(SimpleNamespace()) is None


@pytest.mark.parametrize("base", [
    "https://mindcare.example.ru",          # production: HTTPS reverse proxy
    "https://mindcare.example.ru:443",
    "https://localhost",                    # https — не локальный http-порт
])
def test_https_callback_base_needs_no_listener(base):
    """Production-подобная конфигурация: отдельный listener не нужен."""
    assert helper.dev_callback_listener_port(_config(VK_OAUTH_CALLBACK_BASE_URL=base)) is None


@pytest.mark.parametrize("base", [
    "http://mindcare.example.ru",           # http не на loopback запрещён вовсе
    "http://192.168.1.10",
    "http://user:pw@localhost",
    "http://localhost?x=1",
    "http://localhost#frag",
    "http://localhost:99999",
    "ftp://localhost",
    "not a url",
])
def test_invalid_or_non_loopback_base_needs_no_listener(base):
    assert helper.dev_callback_listener_port(_config(VK_OAUTH_CALLBACK_BASE_URL=base)) is None


@pytest.mark.parametrize("base", [
    "http://localhost:3000",                # порт фронтенда
    "http://localhost:8000",                # порт основного backend
    "http://localhost:8080",
    "http://localhost:443",
])
def test_non_standard_localhost_port_needs_no_listener(base):
    """VK ID принимает только :80 — launcher не занимает другие порты."""
    assert helper.dev_callback_listener_port(_config(VK_OAUTH_CALLBACK_BASE_URL=base)) is None


def test_main_backend_already_on_port_80_needs_no_listener():
    assert helper.dev_callback_listener_port(_config(), main_port=80) is None


# ── CLI: только номер порта, код возврата 0 ─────────────────────────────────

def _run_main(monkeypatch, capsys, config, argv=()):
    import app.core.config as config_module

    monkeypatch.setattr(config_module, "settings", config)
    code = helper.main(list(argv))
    return code, capsys.readouterr()


def test_cli_prints_only_port(monkeypatch, capsys):
    code, out = _run_main(monkeypatch, capsys, _config(VK_OAUTH_CLIENT_ID="SECRET-LOOKING-ID"))
    assert code == 0
    assert out.out == "80\n"
    assert out.err == ""
    assert "SECRET-LOOKING-ID" not in out.out + out.err      # настройки не печатаются


def test_cli_prints_nothing_when_not_needed(monkeypatch, capsys):
    code, out = _run_main(monkeypatch, capsys, _config(VK_OAUTH_ENABLED=False))
    assert (code, out.out, out.err) == (0, "", "")


def test_cli_respects_main_port(monkeypatch, capsys):
    code, out = _run_main(monkeypatch, capsys, _config(), argv=["--main-port", "80"])
    assert (code, out.out) == (0, "")


def test_cli_swallows_configuration_errors(monkeypatch, capsys):
    """Сломанная конфигурация = «listener не нужен»; запуск backend не блокируется."""
    class Broken:
        def __getattr__(self, name):
            raise RuntimeError("boom SECRET")

    code, out = _run_main(monkeypatch, capsys, Broken())
    assert (code, out.out) == (0, "")
    assert "SECRET" not in out.err


# ── границы: приложение не порождает процессы, production listener не знает ──

def _python_sources(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_app_never_spawns_processes_or_servers():
    """Listener запускает только launcher — не FastAPI lifespan и не app.*."""
    offenders = []
    # Нигде в приложении: второй сервер и обращение к DEV-helper'у.
    for path in _python_sources(_API_ROOT / "app"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"\buvicorn\.(run|Server|Config)\b", text) or "dev_oauth_callback_port" in text:
            offenders.append(path.name)
    # Старт приложения и OAuth-модуль процессы не порождают вовсе.
    startup = [_API_ROOT / "app" / "main.py", *_python_sources(_API_ROOT / "app" / "oauth")]
    for path in startup:
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*(import|from)\s+(subprocess|multiprocessing)\b", text, re.MULTILINE):
            offenders.append(path.name)
        if re.search(r"os\.(system|spawn\w*|exec\w*|popen)\(", text):
            offenders.append(path.name)
    assert offenders == []


def test_production_deployment_does_not_use_dev_listener():
    files = [DEPLOY_SH, *sorted(DEPLOY_DIR.glob("*.service")), *sorted(DEPLOY_DIR.glob("*.timer"))]
    assert files, "deploy files not found"
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "dev_oauth_callback_port" not in text, path.name
        assert not re.search(r"--port[ =]80\b", text), path.name
        assert "start.ps1" not in text and "start.sh" not in text, path.name


# ── launcher'ы: listener привязан к запуску backend ─────────────────────────

def test_start_ps1_is_ascii_and_hosts_listener_in_backend_window():
    raw = START_PS1.read_bytes()
    raw.decode("ascii")          # PowerShell 5.1 читает файл без BOM как ANSI
    text = raw.decode("ascii")

    assert "scripts\\dev_oauth_callback_port.py" in text
    command = text[text.index("function New-BackendCommand"):text.index("# --- Banner")]
    # Listener делит консоль с основным backend (Ctrl+C / закрытие окна гасят оба)…
    assert "-NoNewWindow -PassThru" in command
    # …слушает только loopback…
    assert "'--host','127.0.0.1','--port','$callbackPort'" in command
    assert "0.0.0.0" not in command
    # …и гасится, если основной backend завершился сам.
    assert re.search(r"try \{ & '\$venvUvicorn' app\.main:app --port \$backendPort --reload \} \" \+\s+\"finally \{",
                     command)
    assert "taskkill.exe /PID `$callback.Id /T /F" in command
    # Занятый порт не мешает запуску основного backend.
    assert "Test-LoopbackPortFree $callbackPort" in text
    # Порт нигде не захардкожен: его даёт helper.
    assert not re.search(r"--port',?\s*'?80\b", text)


def test_start_sh_starts_listener_only_on_helper_request_and_documents_stop():
    text = START_SH.read_text(encoding="utf-8")
    assert "scripts/dev_oauth_callback_port.py" in text
    assert '--host 127.0.0.1 --port "$CALLBACK_PORT" --reload' in text
    assert 'echo $! >"$LOG_DIR/vk-callback.pid"' in text
    assert "$(cat logs/vk-callback.pid)" in text.replace("\\$", "$")     # входит в команду остановки
    assert not re.search(r"--port[ =]80\b", text)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash недоступен")
def test_start_sh_syntax():
    result = subprocess.run(
        ["bash", "-n", START_SH.as_posix()], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("path", [START_PS1, START_SH, HELPER])
def test_launchers_explain_why_port_80(path):
    """Причина порта 80 записана рядом с кодом, который его открывает."""
    text = path.read_text(encoding="utf-8")
    assert "VK ID" in text
    assert re.search(r"localhost[^\n]*\(port 80\)|localhost[^\n]*\(порт 80\)", text)

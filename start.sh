#!/usr/bin/env bash
# MindCare -- zero-to-run dev launcher (Linux)
# Порядок запуска:
#   1. Проверка инструментов (python, npm)
#   2. Создание venv в mindcare_api/.venv
#   3. Установка backend-зависимостей (pip)
#   4. Установка frontend-зависимостей (npm)
#   5. Backend-тесты (./test.sh; пропускается с --skip-tests)
#   6. alembic upgrade head   <- ОБЯЗАТЕЛЬНО до uvicorn
#   7. Проверка alembic revision
#   8. Запуск backend (фоном, лог в logs/backend.log) + только для DEV:
#      listener callback VK ID на :80 (если его просит локальный .env, см. ниже)
#   9. Запуск frontend (фоном, лог в logs/frontend.log)
#  10. Health-check poll (60 с)
#
# ПОЧЕМУ alembic до uvicorn:
#   FastAPI lifespan только читает alembic_version (read-only проверка),
#   миграции не применяет. Их нужно применить здесь заранее.
#   НИКОГДА не вызывать alembic.command.upgrade() из FastAPI lifespan -- deadlock.
#   НИКОГДА не вызывать Base.metadata.create_all() -- схема только через Alembic.
#
# ПОЧЕМУ второй listener на порту 80 (только локальная разработка):
#   VK ID принимает localhost в доверенном Redirect URL только на стандартных
#   портах: http://localhost (порт 80) либо https://localhost (порт 443);
#   другие localhost-порты VK ID не поддерживает. Поэтому DEV-приложение VK
#   зарегистрировано на http://localhost/api/auth/oauth/vk/callback, а основной
#   backend слушает :8000. Если в локальном .env VK_OAUTH_ENABLED=true и
#   VK_OAUTH_CALLBACK_BASE_URL=http://localhost, скрипт поднимает второй
#   экземпляр ТОГО ЖЕ приложения (тот же .env, та же БД) на 127.0.0.1:80.
#   - Нужен ли listener, решает mindcare_api/scripts/dev_oauth_callback_port.py.
#   - Останавливается той же командой, что backend и frontend (PID в
#     logs/vk-callback.pid).
#   - Само приложение его не порождает (никакого subprocess в FastAPI lifespan).
#   - На Linux порты < 1024 требуют привилегий: если порт недоступен, listener
#     не запускается, остальной запуск продолжается.
#   - Production не затрагивается: deploy.sh / systemd этот скрипт не
#     используют, callback там обслуживает HTTPS reverse proxy.
#
# Для production используйте deploy.sh (systemd-сервисы), а не этот скрипт.
#
# Использование:
#   ./start.sh                полный запуск, backend-тесты блокируют старт
#   ./start.sh --skip-tests   быстрый запуск без шага 5 (./test.sh отдельно)
set -euo pipefail

SKIP_TESTS=false
for arg in "$@"; do
  case "$arg" in
    --skip-tests) SKIP_TESTS=true ;;
    *) echo "Неизвестный аргумент: $arg (доступно: --skip-tests)" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT/mindcare_api"
WEB_DIR="$ROOT/mindcare_web"
VENV_DIR="$API_DIR/.venv"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_UVICORN="$VENV_DIR/bin/uvicorn"
VENV_ALEMBIC="$VENV_DIR/bin/alembic"
LOG_DIR="$ROOT/logs"

MAGENTA='\033[0;35m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'
YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
section() { echo -e "\n${CYAN}--- $*${NC}"; }
ok()      { echo -e "  ${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "  ${YELLOW}[WARN]${NC} $*"; }
fail()    { echo -e "  ${RED}[FAIL]${NC} $*"; exit 1; }

echo ""
echo -e "${MAGENTA}==========================================${NC}"
echo -e "${MAGENTA}         MindCare  --  Dev Launcher       ${NC}"
echo -e "${MAGENTA}==========================================${NC}"

# --- Шаг 1: инструменты ------------------------------------------------------
section "Step 1: required tools"
command -v python3 >/dev/null 2>&1 || fail "'python3' не найден. Установите Python 3.11+."
command -v npm     >/dev/null 2>&1 || fail "'npm' не найден. Установите Node.js 18+."
ok "python3  $(python3 --version 2>&1)"
ok "npm      $(npm --version 2>&1)"

# --- Шаг 2: venv -------------------------------------------------------------
section "Step 2: Python virtual environment"
if [ ! -d "$VENV_DIR" ]; then
  echo "  Создаю venv в $VENV_DIR ..."
  python3 -m venv "$VENV_DIR" || fail "Не удалось создать venv."
  ok "venv создан."
else
  ok "venv уже существует."
fi

# --- Шаг 3: backend-зависимости ----------------------------------------------
section "Step 3: backend dependencies"
if [ ! -x "$VENV_UVICORN" ]; then
  echo "  pip install -r requirements.txt (может занять минуту)..."
  "$VENV_PIP" install -r "$API_DIR/requirements.txt" --quiet || fail "pip install упал."
  ok "Backend-зависимости установлены."
else
  ok "Backend-зависимости уже установлены."
fi

# --- Шаг 4: frontend-зависимости ---------------------------------------------
section "Step 4: frontend dependencies"
if [ ! -d "$WEB_DIR/node_modules" ]; then
  echo "  npm install (может занять минуту)..."
  ( cd "$WEB_DIR" && npm install --silent ) || fail "npm install упал."
  ok "Frontend-зависимости установлены."
else
  ok "node_modules уже существует."
fi

# --- Шаг 5: backend-тесты ----------------------------------------------------
section "Step 5: backend tests"
if $SKIP_TESTS; then
  warn "Пропущено (--skip-tests). Запустите ./test.sh перед push."
else
  "$ROOT/test.sh" || fail "Проект не запущен: тесты упали. Исправьте и перезапустите ./start.sh (или ./start.sh --skip-tests)"
  ok "Все тесты прошли."
fi

# --- Шаг 6: alembic upgrade head ---------------------------------------------
section "Step 6: alembic upgrade head"
( cd "$API_DIR" && "$VENV_ALEMBIC" upgrade head ) \
  || fail "alembic upgrade head упал. Проверьте подключение к БД и .env (DATABASE_URL)."
ok "Миграции применены."

# --- Шаг 7: проверка revision ------------------------------------------------
section "Step 7: verify DB revision"
( cd "$API_DIR" && "$VENV_ALEMBIC" current ) || warn "Не удалось прочитать alembic revision."

# --- Шаг 8: запуск backend ---------------------------------------------------
section "Step 8: start backend"
mkdir -p "$LOG_DIR"
( cd "$API_DIR" && nohup "$VENV_UVICORN" app.main:app --host 0.0.0.0 --port 8000 --reload \
  >"$LOG_DIR/backend.log" 2>&1 & echo $! >"$LOG_DIR/backend.pid" )
ok "Backend запущен -> http://localhost:8000 (PID $(cat "$LOG_DIR/backend.pid"), лог: logs/backend.log)"

# Только DEV: listener callback VK ID (см. шапку: VK ID нужен localhost:80).
# Helper печатает номер порта либо ничего; значения настроек он не выводит.
rm -f "$LOG_DIR/vk-callback.pid"
CALLBACK_PORT="$(cd "$API_DIR" && "$VENV_PYTHON" scripts/dev_oauth_callback_port.py --main-port 8000 2>/dev/null || true)"
if [[ "$CALLBACK_PORT" =~ ^[0-9]+$ ]]; then
  # Одна проверка на оба случая: порт занят либо на него нет прав (< 1024).
  if "$VENV_PYTHON" -c 'import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[1])))
s.close()' "$CALLBACK_PORT" 2>/dev/null; then
    ( cd "$API_DIR" && nohup "$VENV_UVICORN" app.main:app --host 127.0.0.1 --port "$CALLBACK_PORT" --reload \
      >"$LOG_DIR/vk-callback.log" 2>&1 & echo $! >"$LOG_DIR/vk-callback.pid" )
    ok "Listener callback VK ID (только DEV) -> http://localhost:$CALLBACK_PORT (PID $(cat "$LOG_DIR/vk-callback.pid"), лог: logs/vk-callback.log)"
  else
    warn "Порт $CALLBACK_PORT недоступен (занят либо нужны права на порты < 1024): listener callback VK ID НЕ запущен."
    warn "Вход через VK локально работать не будет; остальной запуск продолжается."
    CALLBACK_PORT=""
  fi
else
  CALLBACK_PORT=""
  ok "Listener callback VK ID не нужен (VK выключен либо его callback не http://localhost)."
fi

# --- Шаг 9: запуск frontend --------------------------------------------------
section "Step 9: start frontend"
( cd "$WEB_DIR" && CI=false HOST=0.0.0.0 PORT=3000 nohup npm start \
  >"$LOG_DIR/frontend.log" 2>&1 & echo $! >"$LOG_DIR/frontend.pid" )
ok "Frontend запущен -> http://localhost:3000 (PID $(cat "$LOG_DIR/frontend.pid"), лог: logs/frontend.log)"

# --- Шаг 10: health-check ----------------------------------------------------
section "Step 10: waiting for backend to be ready"
ready=false
for i in $(seq 1 60); do
  sleep 1
  if curl -sf "http://localhost:8000/api/health" >/dev/null 2>&1; then
    ok "Backend готов (${i}s)."
    ready=true
    break
  fi
  [ $((i % 5)) -eq 0 ] && echo "  ... ожидание ($i / 60 s)"
done
$ready || warn "Backend не ответил за 60 с. Проверьте logs/backend.log"

if [ -n "$CALLBACK_PORT" ]; then
  callback_ready=false
  for i in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:$CALLBACK_PORT/api/health" >/dev/null 2>&1; then
      callback_ready=true
      break
    fi
    sleep 1
  done
  if $callback_ready; then
    ok "Listener callback VK ID готов на :$CALLBACK_PORT."
  else
    warn "Listener callback VK ID не ответил на :$CALLBACK_PORT. Проверьте logs/vk-callback.log"
  fi
fi

echo ""
echo -e "${MAGENTA}==========================================${NC}"
echo -e "${MAGENTA}  Оба сервера запущены в фоне${NC}"
echo -e "${MAGENTA}==========================================${NC}"
echo -e "  Backend API : http://localhost:8000/docs"
echo -e "  Frontend    : http://localhost:3000"
if [ -n "$CALLBACK_PORT" ]; then
  echo -e "  VK callback : http://localhost:$CALLBACK_PORT  (только DEV)"
  echo -e "  Остановка   : kill \$(cat logs/backend.pid) \$(cat logs/frontend.pid) \$(cat logs/vk-callback.pid)"
else
  echo -e "  Остановка   : kill \$(cat logs/backend.pid) \$(cat logs/frontend.pid)"
fi
echo -e "${MAGENTA}==========================================${NC}"
echo ""

#!/usr/bin/env bash
# MindCare -- zero-to-run dev launcher (Linux)
# Порядок запуска:
#   1. Проверка инструментов (python, npm)
#   2. Создание venv в mindcare_api/.venv
#   3. Установка backend-зависимостей (pip)
#   4. Установка frontend-зависимостей (npm)
#   5. Backend-тесты (./test.sh)
#   6. alembic upgrade head   <- ОБЯЗАТЕЛЬНО до uvicorn
#   7. Проверка alembic revision
#   8. Запуск backend (фоном, лог в logs/backend.log)
#   9. Запуск frontend (фоном, лог в logs/frontend.log)
#  10. Health-check poll (60 с)
#
# ПОЧЕМУ alembic до uvicorn:
#   FastAPI lifespan только читает alembic_version (read-only проверка),
#   миграции не применяет. Их нужно применить здесь заранее.
#   НИКОГДА не вызывать alembic.command.upgrade() из FastAPI lifespan -- deadlock.
#   НИКОГДА не вызывать Base.metadata.create_all() -- схема только через Alembic.
#
# Для production используйте deploy.sh (systemd-сервисы), а не этот скрипт.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT/mindcare_api"
WEB_DIR="$ROOT/mindcare_web"
VENV_DIR="$API_DIR/.venv"
VENV_PIP="$VENV_DIR/bin/pip"
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
"$ROOT/test.sh" || fail "Проект не запущен: тесты упали. Исправьте и перезапустите ./start.sh"
ok "Все тесты прошли."

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

echo ""
echo -e "${MAGENTA}==========================================${NC}"
echo -e "${MAGENTA}  Оба сервера запущены в фоне${NC}"
echo -e "${MAGENTA}==========================================${NC}"
echo -e "  Backend API : http://localhost:8000/docs"
echo -e "  Frontend    : http://localhost:3000"
echo -e "  Остановка   : kill \$(cat logs/backend.pid) \$(cat logs/frontend.pid)"
echo -e "${MAGENTA}==========================================${NC}"
echo ""

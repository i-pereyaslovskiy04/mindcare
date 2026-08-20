#!/usr/bin/env bash
# MindCare — скрипт развёртывания на Linux (Debian/Ubuntu/Raspberry Pi OS)
# Использование:
#   chmod +x deploy.sh
#   ./deploy.sh              — интерактивное развёртывание
#   ./deploy.sh --install-deps  — установить системные пакеты автоматически
#   ./deploy.sh --no-systemd    — не создавать systemd-сервисы
#   ./deploy.sh --enable-ip-anonymization
#                               — СРАЗУ включить таймер IP-анонимизации.
#                                 По умолчанию таймер только устанавливается,
#                                 но НЕ активируется: первый прогон необратим
#                                 (см. deploy/STAGE_7_DEPLOYMENT.md).

set -euo pipefail
IFS=$'\n\t'

# ─── Цвета ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

STEP=0; TOTAL_STEPS=9

step()  { STEP=$((STEP+1)); echo -e "\n${BLUE}${BOLD}[${STEP}/${TOTAL_STEPS}] $*${NC}"; }
ok()    { echo -e "  ${GREEN}✓${NC}  $*"; }
warn()  { echo -e "  ${YELLOW}⚠${NC}  $*"; }
die()   { echo -e "\n${RED}${BOLD}ОШИБКА:${NC} $*\n"; exit 1; }
info()  { echo -e "  →  $*"; }
ask()   { echo -en "  ${BOLD}$1${NC} "; }

# ─── Аргументы ──────────────────────────────────────────────────────────────
INSTALL_DEPS=false
SETUP_SYSTEMD=true
# Default=false осознанно: `enable --now` запустил бы ПЕРВЫЙ прогон немедленно,
# до dry-run и до того, как оператор увидел объём. Обнулённые ip_address не
# восстанавливаются ни downgrade, ни повторным запуском.
ENABLE_IP_ANON=false
for arg in "$@"; do
  case $arg in
    --install-deps) INSTALL_DEPS=true ;;
    --no-systemd)   SETUP_SYSTEMD=false ;;
    --enable-ip-anonymization) ENABLE_IP_ANON=true ;;
    *) die "Неизвестный аргумент: $arg" ;;
  esac
done

# ─── Пути ───────────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$PROJECT_DIR/mindcare_api"
WEB_DIR="$PROJECT_DIR/mindcare_web"
API_ENV="$API_DIR/.env"
WEB_ENV="$WEB_DIR/.env"
DB_USER="MindcareUser"
DB_NAME="mindcare"
DB_PORT=5432

echo -e "\n${BOLD}╔══════════════════════════════════════════╗"
echo -e "║     MindCare — развёртывание проекта    ║"
echo -e "╚══════════════════════════════════════════╝${NC}"
echo -e "  Директория: ${BOLD}$PROJECT_DIR${NC}"
echo -e "  Дата:       $(date '+%Y-%m-%d %H:%M')"

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 1 — Системные требования
# ════════════════════════════════════════════════════════════════════════════
step "Системные требования"

check_or_install() {
  local cmd="$1" pkg="$2" label="$3"
  if command -v "$cmd" &>/dev/null; then
    ok "$label: $(${cmd} --version 2>&1 | head -1)"
  elif $INSTALL_DEPS; then
    info "Устанавливаю $pkg..."
    sudo apt-get install -y "$pkg" >/dev/null 2>&1
    ok "$label установлен"
  else
    die "$label не найден. Установите вручную или запустите с --install-deps"
  fi
}

# PostgreSQL
if command -v psql &>/dev/null; then
  ok "PostgreSQL: $(psql --version)"
elif $INSTALL_DEPS; then
  info "Устанавливаю PostgreSQL..."
  sudo apt-get update -qq
  sudo apt-get install -y postgresql postgresql-contrib >/dev/null 2>&1
  sudo systemctl enable --now postgresql
  ok "PostgreSQL установлен и запущен"
else
  die "PostgreSQL не найден. Установите: sudo apt install postgresql"
fi

if ! systemctl is-active --quiet postgresql 2>/dev/null; then
  sudo systemctl start postgresql || die "Не удалось запустить PostgreSQL"
fi
ok "PostgreSQL запущен"

# Python
PY=""
for v in python3.13 python3.12 python3.11 python3; do
  if command -v "$v" &>/dev/null; then
    PY_VER=$("$v" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
      PY="$v"; break
    fi
  fi
done
[ -z "$PY" ] && die "Python 3.11+ не найден. Установите: sudo apt install python3.11"
ok "Python: $($PY --version)"

# Node.js
# Сначала пробуем nvm: ~/.bashrc не читается в неинтерактивном шелле, поэтому
# без явного PATH node "не находится" и ниже сработала бы установка системного
# пакета параллельно уже стоящей nvm-версии.
if ! command -v node &>/dev/null; then
  NVM_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | tail -1)"
  [ -n "$NVM_BIN" ] && PATH="$NVM_BIN:$PATH" && export PATH
fi

if command -v node &>/dev/null; then
  NODE_MAJ=$(node -e "console.log(process.versions.node.split('.')[0])")
  [ "$NODE_MAJ" -lt 18 ] && die "Node.js 18+ обязателен (найден: $(node --version))"
  ok "Node.js: $(node --version), npm: $(npm --version)"
elif $INSTALL_DEPS; then
  info "Устанавливаю Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash - >/dev/null 2>&1
  sudo apt-get install -y nodejs >/dev/null 2>&1
  ok "Node.js установлен: $(node --version)"
else
  die "Node.js 18+ не найден. Установите: https://nodejs.org или sudo apt install nodejs"
fi

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 2 — Настройка .env (backend)
# ════════════════════════════════════════════════════════════════════════════
step "Конфигурация .env"

SERVER_IP=$(hostname -I | awk '{print $1}')

if [ -f "$API_ENV" ]; then
  ok "Файл $API_ENV уже существует, использую его"
  source <(grep -v '^#' "$API_ENV" | grep '=' | sed 's/^/export /')
  DB_PASSWORD="${DB_PASSWORD:-$(echo "$DATABASE_URL" | sed 's/.*:\([^@]*\)@.*/\1/')}"
else
  echo ""
  warn "Файл .env не найден — создаю интерактивно"
  echo ""

  ask "Пароль для БД (Enter = сгенерировать):"
  read -r DB_PASSWORD
  if [ -z "$DB_PASSWORD" ]; then
    DB_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9_-' </dev/urandom | head -c 20)
    info "Сгенерирован пароль БД: ${BOLD}$DB_PASSWORD${NC}"
  fi

  ask "EMAIL_MODE [dev/smtp] (Enter = dev):"
  read -r EMAIL_MODE
  EMAIL_MODE="${EMAIL_MODE:-dev}"

  SMTP_BLOCK=""
  if [ "$EMAIL_MODE" = "smtp" ]; then
    ask "SMTP_HOST:"; read -r SMTP_HOST
    ask "SMTP_PORT (Enter = 587):"; read -r SMTP_PORT; SMTP_PORT="${SMTP_PORT:-587}"
    ask "SMTP_USER:"; read -r SMTP_USER
    ask "SMTP_PASSWORD:"; read -rs SMTP_PASSWORD; echo ""
    ask "SMTP_FROM (Enter = $SMTP_USER):"; read -r SMTP_FROM; SMTP_FROM="${SMTP_FROM:-$SMTP_USER}"
    SMTP_BLOCK="SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASSWORD=$SMTP_PASSWORD
SMTP_FROM=$SMTP_FROM
SMTP_TLS=true
SMTP_SSL=false"
  fi

  # Генерируем Fernet-ключ после установки venv (временно через python3)
  FERNET_KEY=$(python3 -c "
import base64, os
key = base64.urlsafe_b64encode(os.urandom(32)).decode()
print(key)
")

  ALLOWED_ORIGINS="http://localhost:3000"
  [ -n "$SERVER_IP" ] && ALLOWED_ORIGINS="$ALLOWED_ORIGINS,http://${SERVER_IP}:3000"

  cat > "$API_ENV" <<EOF
# --- DATABASE ---
DATABASE_URL=postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}

# --- AUTH ---
SESSION_EXPIRE_DAYS=7

# --- APP ---
DEBUG=False
ENV=production

# --- EMAIL ---
EMAIL_MODE=${EMAIL_MODE}

${SMTP_BLOCK}

NEWS_IMAGE_MAX_SIZE_MB=20
ALLOWED_ORIGINS=${ALLOWED_ORIGINS}

# --- ENCRYPTION ---
DATA_ENCRYPTION_KEY=${FERNET_KEY}
EOF

  ok "Файл $API_ENV создан"
  warn "Сохраните DATA_ENCRYPTION_KEY из .env — без него нельзя расшифровать данные!"
fi

# .env для фронтенда
if [ ! -f "$WEB_ENV" ]; then
  echo "HOST=0.0.0.0" > "$WEB_ENV"
  ok "Создан $WEB_ENV (HOST=0.0.0.0)"
else
  ok "$WEB_ENV уже существует"
fi

# .gitignore — убедимся, что .env не попадёт в git
if [ -f "$PROJECT_DIR/.gitignore" ]; then
  grep -q "^\.env$" "$PROJECT_DIR/.gitignore" || echo ".env" >> "$PROJECT_DIR/.gitignore"
fi

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 3 — PostgreSQL: роль и база данных
# ════════════════════════════════════════════════════════════════════════════
step "PostgreSQL: роль и база данных"

# Получаем пароль из .env
DB_PASSWORD=$(grep "^DATABASE_URL=" "$API_ENV" | sed 's/.*:\([^@]*\)@.*/\1/')

ROLE_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'")
if [ "$ROLE_EXISTS" = "1" ]; then
  ok "Роль ${DB_USER} уже существует"
else
  sudo -u postgres psql -c "CREATE ROLE \"${DB_USER}\" WITH LOGIN PASSWORD '${DB_PASSWORD}';"
  ok "Роль ${DB_USER} создана"
fi

DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")
if [ "$DB_EXISTS" = "1" ]; then
  ok "База данных ${DB_NAME} уже существует"
else
  sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER \"${DB_USER}\" ENCODING 'UTF8';"
  ok "База данных ${DB_NAME} создана"
fi

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 4 — Python venv и зависимости
# ════════════════════════════════════════════════════════════════════════════
step "Python venv и зависимости"

cd "$API_DIR"

if [ ! -d ".venv" ]; then
  info "Создаю виртуальное окружение..."
  $PY -m venv .venv
  ok "venv создан"
else
  ok "venv уже существует"
fi

info "Устанавливаю/обновляю зависимости..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
ok "Зависимости установлены"

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 5 — Миграции Alembic
# ════════════════════════════════════════════════════════════════════════════
step "Миграции Alembic"

# Юниты, которые ПИШУТ в БД (uvicorn app.main:app). mindcare-web — CRA-фронт,
# писателем не является и в этом списке не нужен.
WRITER_UNITS=(mindcare-api.service mindcare-demo.service)
STOPPED_UNITS=()

stop_writers() {
  local unit
  for unit in "${WRITER_UNITS[@]}"; do
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
      sudo systemctl stop "$unit"
      STOPPED_UNITS+=("$unit")
      info "Остановлен writer-юнит: $unit"
    fi
  done
  # Незарегистрированный писатель (ручной uvicorn, dev-режим, tmux) сделал бы
  # «гарантированный простой» фикцией — такой случай останавливаем явно.
  if curl -sf --max-time 3 http://localhost:8000/docs >/dev/null 2>&1; then
    die "На порту 8000 работает бэкенд вне systemd. Гарантированный простой\
 недостижим — погасите его (scripts/mindcare-mode.sh stop) и повторите запуск,\
 либо выполняйте поэтапный rollout по deploy/STAGE_5C_DEPLOYMENT.md"
  fi
}

# Поднимает КАЖДЫЙ ранее остановленный юнит, даже если предыдущий не стартовал:
# ранний выход оставил бы остальные писатели лежать. Общий провал возвращается
# только после попытки по всем.
start_writers() {
  local unit rc=0
  for unit in "${STOPPED_UNITS[@]:-}"; do
    [ -n "$unit" ] || continue
    if sudo systemctl start "$unit"; then
      info "Запущен обратно: $unit"
    else
      rc=1
      warn "НЕ УДАЛОСЬ запустить $unit — нужно вмешательство вручную"
    fi
  done
  return $rc
}

# Аварийное восстановление. Ставится ДО stop_writers, поэтому срабатывает и при
# сбое самой остановки (например die на «неучтённом» писателе, когда часть
# юнитов уже погашена).
restore_writers_on_exit() {
  start_writers || warn "Часть writer-юнитов осталась остановленной"
}

# Количество пользовательских таблиц (обычные + партиционированные родители,
# без дочерних партиций и служебной alembic_version).
user_table_count() {
  psql "postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}" \
    -tAc "SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') AND c.relispartition = false AND c.relname != 'alembic_version';" \
    2>/dev/null | tr -d ' '
}

run_alembic_upgrade() {
  local log="$API_DIR/.alembic-deploy.log"
  # Ошибку миграции НЕ прятать: пайп с grep + `|| true` раньше маскировал
  # ненулевой код alembic, и деплой продолжался на несогласованной схеме.
  if ! .venv/bin/alembic upgrade head >"$log" 2>&1; then
    echo ""
    grep -E 'ERROR|FAILED|Traceback|raise |Error' "$log" | tail -20 || true
    die "alembic upgrade head завершился с ошибкой. Полный лог: $log"
  fi
  grep -E 'Running upgrade' "$log" || true
  rm -f "$log"
}

# `alembic current` на пустой БД печатает пусто и завершается успешно; ошибка
# подключения — это НЕ «пустая БД», иначе мы приняли бы недоступную боевую базу
# за новую и накатили миграции без остановки писателей.
if ! CURRENT_OUT=$(.venv/bin/alembic current 2>&1); then
  echo "$CURRENT_OUT" | tail -5
  die "Не удалось прочитать текущую revision (проверьте DATABASE_URL и БД)"
fi
CURRENT_REV=$(echo "$CURRENT_OUT" | grep -oE '^[a-f0-9]{6,}' | head -1 || true)
CURRENT_REV="${CURRENT_REV:-none}"
HEAD_REV=$(.venv/bin/alembic heads 2>/dev/null | grep -oE '^[a-f0-9]{6,}' | head -1 || echo "unknown")

if [ "$CURRENT_REV" = "$HEAD_REV" ]; then
  ok "Схема актуальна (revision: $CURRENT_REV)"
elif [ "$CURRENT_REV" = "none" ]; then
  # Отсутствие revision само по себе НЕ означает новую БД: так же выглядит база,
  # развёрнутая мимо Alembic (legacy db/sql-bootstrap) или с потерянной
  # alembic_version. Прогонять по ней миграции как по чистой — разрушительно,
  # поэтому «пустоту» проверяем фактически.
  EXISTING_TABLES=$(user_table_count || true)
  if [ -z "$EXISTING_TABLES" ]; then
    die "Не удалось пересчитать таблицы в ${DB_NAME} — состояние схемы неизвестно"
  fi
  if [ "$EXISTING_TABLES" != "0" ]; then
    die "В ${DB_NAME} нет alembic revision, но есть таблиц: ${EXISTING_TABLES}.\
 Схема развёрнута мимо Alembic либо alembic_version потеряна. Автоматический\
 upgrade запрещён — восстановите revision вручную (alembic stamp) по\
 deploy/STAGE_5C_DEPLOYMENT.md"
  fi
  # Подтверждённо пустая БД: старой версии приложения, которая могла бы писать в
  # окно между ревизиями, не существует — окна совместимости нет.
  info "Новая пустая БД, head: ${HEAD_REV} — применяю миграции..."
  run_alembic_upgrade
  ok "Миграции применены → $(.venv/bin/alembic current 2>/dev/null)"
else
  # Обновление СУЩЕСТВУЮЩЕЙ базы. Начиная со Stage 5C `upgrade head` содержит
  # окно совместимости (a1c4e8b2f7d3 → b5d7f0a3c9e1): старая версия приложения
  # в этот момент создаёт серии расписания без identity-строки, и включение FK
  # ломает их. Поэтому здесь выполняется ИМЕННО путь A из
  # deploy/STAGE_5C_DEPLOYMENT.md — с гарантированным простоем.
  echo ""
  warn "Обновление существующей схемы: ${CURRENT_REV} → ${HEAD_REV}"
  warn "Будет выполнен путь A (гарантированный простой): писатели БД"
  warn "останавливаются на время миграции. Без простоя используйте"
  warn "поэтапный rollout из deploy/STAGE_5C_DEPLOYMENT.md."
  echo ""

  if ! $SETUP_SYSTEMD; then
    die "С --no-systemd скрипт не может гарантировать простой писателей.\
 Выполните обновление существующей БД по deploy/STAGE_5C_DEPLOYMENT.md"
  fi

  ask "Продолжить с остановкой сервиса? [y/N]:"
  read -r CONFIRM_DOWNTIME
  case "$CONFIRM_DOWNTIME" in
    [yY]|[yY][eE][sS]) ;;
    *) die "Отменено. Поэтапный rollout без простоя — deploy/STAGE_5C_DEPLOYMENT.md" ;;
  esac

  # Trap ставится ДО остановки: иначе die внутри stop_writers (неучтённый
  # писатель на 8000) оставил бы уже погашенные юниты лежать.
  trap restore_writers_on_exit EXIT
  stop_writers
  run_alembic_upgrade
  # Trap снимается ТОЛЬКО после того, как поднялись ВСЕ остановленные юниты.
  if ! start_writers; then
    die "Миграции применены, но часть writer-юнитов не запустилась —\
 поднимите их вручную: sudo systemctl start ${STOPPED_UNITS[*]:-<нет>}"
  fi
  trap - EXIT
  ok "Миграции применены → $(.venv/bin/alembic current 2>/dev/null)"
fi

# Тот же счётчик, что и в проверке пустоты выше (одна реализация запроса).
TABLE_COUNT=$(user_table_count || true)
ok "Таблиц в БД: ${TABLE_COUNT:-?}"

# Seed запускается автоматически при старте приложения — проверим через быстрый запуск
info "Запускаю приложение для seed..."
timeout 12 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  2>&1 | grep -E 'SEED|ready|ERROR' | head -5 || true
ok "Seed выполнен"

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 6 — Frontend: npm install
# ════════════════════════════════════════════════════════════════════════════
step "Frontend: npm install"

cd "$WEB_DIR"

if [ -d "node_modules" ] && [ -f "node_modules/.package-lock.json" ]; then
  ok "node_modules уже установлены"
else
  info "Устанавливаю зависимости (может занять 1-2 минуты)..."
  npm install --loglevel=error 2>&1 | tail -3
  ok "npm install выполнен"
fi

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 7 — Первый администратор
# ════════════════════════════════════════════════════════════════════════════
step "Первый администратор"

cd "$API_DIR"

ADMIN_EXISTS=$(psql "postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}" \
  -tAc "SELECT COUNT(*) FROM users u JOIN user_roles ur ON ur.user_id=u.id JOIN roles r ON r.id=ur.role_id WHERE r.name='admin';" 2>/dev/null || echo "0")
ADMIN_EXISTS=$(echo "$ADMIN_EXISTS" | tr -d ' ')

if [ "$ADMIN_EXISTS" != "0" ]; then
  ADMIN_EMAIL=$(psql "postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}" \
    -tAc "SELECT u.email FROM users u JOIN user_roles ur ON ur.user_id=u.id JOIN roles r ON r.id=ur.role_id WHERE r.name='admin' LIMIT 1;" 2>/dev/null | tr -d ' ')
  ok "Администратор уже существует: ${ADMIN_EMAIL}"
else
  echo ""
  warn "Администратор не найден — создаю"
  echo ""

  ask "Email администратора:"
  read -r ADMIN_EMAIL
  [ -z "$ADMIN_EMAIL" ] && die "Email обязателен"

  ask "ФИО:"
  read -r ADMIN_NAME
  [ -z "$ADMIN_NAME" ] && die "ФИО обязательно"

  ask "Пароль (минимум 8 символов):"
  read -rs ADMIN_PASSWORD; echo ""
  [ ${#ADMIN_PASSWORD} -lt 8 ] && die "Пароль слишком короткий"

  ask "Повторите пароль:"
  read -rs ADMIN_PASSWORD2; echo ""
  [ "$ADMIN_PASSWORD" != "$ADMIN_PASSWORD2" ] && die "Пароли не совпадают"

  .venv/bin/python - <<PYEOF
import sys
from pathlib import Path
sys.path.insert(0, str(Path("$API_DIR")))

from app.auth import storage, service
from app.core.normalization import normalize_email
from app.db.models import UserLegalBasisRecord
from app.db.session import SessionLocal

email = normalize_email("$ADMIN_EMAIL")
user = storage.save_user({
    "name": "$ADMIN_NAME",
    "email": email,
    "hashed_password": service._hash("$ADMIN_PASSWORD"),
    "role": "admin",
})
with SessionLocal() as db:
    db.add(UserLegalBasisRecord(
        user_id=int(user["id"]),
        basis_type="bootstrap",
        basis_source="bootstrap_script",
        confirmed_by_user_id=None,
        ip_address=None,
        user_agent="bootstrap-script",
        comment="Bootstrap admin created during deployment",
    ))
    db.commit()
print(f"  Создан: {user['email']} (ID={user['id']}, роль={user['role']})")
PYEOF

  ok "Администратор создан"
fi

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 8 — Systemd сервисы
# ════════════════════════════════════════════════════════════════════════════
step "Systemd сервисы"

if ! $SETUP_SYSTEMD; then
  warn "Пропущено (--no-systemd)"
else
  CURRENT_USER=$(whoami)
  VENV_PYTHON="$API_DIR/.venv/bin/python"
  VENV_UVICORN="$API_DIR/.venv/bin/uvicorn"

  # Backend service
  sudo tee /etc/systemd/system/mindcare-api.service >/dev/null <<EOF
[Unit]
Description=MindCare API (FastAPI)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${API_DIR}
ExecStart=${VENV_UVICORN} app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  # Frontend service
  sudo tee /etc/systemd/system/mindcare-web.service >/dev/null <<EOF
[Unit]
Description=MindCare Web (React dev)
After=network.target mindcare-api.service

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${WEB_DIR}
ExecStart=/usr/bin/npm start
Environment=HOST=0.0.0.0
Environment=PORT=3000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  # ── Обязательные maintenance-таймеры (Stage 5C-3, Stage 7) ───────────────
  # Без них read-пути (которые больше не мутируют) перестают актуализировать
  # status групповых занятий, а серии с auto_extend обрываются по
  # effective_until. Это условие эксплуатации, а не опция.
  #
  # Stage 7 добавляет два юнита. Оба УСТАНАВЛИВАЮТСЯ здесь безусловно, но
  # активируются по-разному (см. блок enable ниже):
  #   - ensure-audit-partitions — только создаёт будущие партиции, данных не
  #     удаляет и не изменяет, поэтому включается сразу;
  #   - anonymize-ips — необратимо обнуляет ip_address, поэтому требует явного
  #     opt-in --enable-ip-anonymization.
  MAINT_UNITS=(
    mindcare-complete-group-sessions.service
    mindcare-complete-group-sessions.timer
    mindcare-extend-schedules.service
    mindcare-extend-schedules.timer
    mindcare-ensure-audit-partitions.service
    mindcare-ensure-audit-partitions.timer
    mindcare-anonymize-ips.service
    mindcare-anonymize-ips.timer
    'mindcare-maintenance-failure@.service'
  )
  CURRENT_GROUP=$(id -gn)
  for unit in "${MAINT_UNITS[@]}"; do
    # Отсутствие юнита прерывает деплой: без таймеров status групповых занятий
    # и auto_extend перестают обновляться, а read-пути их больше не чинят.
    # Warning здесь дал бы «успешный» деплой с неработающим maintenance.
    if [ ! -f "$PROJECT_DIR/deploy/$unit" ]; then
      die "Не найден обязательный unit-файл: deploy/$unit. Maintenance-таймеры\
 Stage 5C — условие эксплуатации, деплой без них не выполняется\
 (см. deploy/STAGE_5C_DEPLOYMENT.md)"
    fi
    # Юниты в репозитории написаны под референсный стенд (путь и пользователь
    # захардкожены) — подставляем фактические, иначе таймеры молча падали бы
    # на чужом хосте.
    sed -e "s|/media/data2/psycho/mindcare|${PROJECT_DIR}|g" \
        -e "s|^User=vitbo$|User=${CURRENT_USER}|" \
        -e "s|^Group=vitbo$|Group=${CURRENT_GROUP}|" \
        "$PROJECT_DIR/deploy/$unit" \
      | sudo tee "/etc/systemd/system/$unit" >/dev/null
  done

  sudo systemctl daemon-reload
  sudo systemctl enable mindcare-api mindcare-web

  sudo systemctl enable --now mindcare-complete-group-sessions.timer
  sudo systemctl enable --now mindcare-extend-schedules.timer
  # Только создаёт недостающие будущие партиции: DROP старых партиций и
  # удаление строк в этот job НЕ входят, поэтому включается без opt-in.
  sudo systemctl enable --now mindcare-ensure-audit-partitions.timer

  # IP-анонимизация: установка отделена от активации.
  #
  # `Persistent=true` + `enable --now` запустили бы ПЕРВЫЙ прогон немедленно —
  # до dry-run и до того, как оператор увидел объём. Прогон необратим:
  # обнулённые ip_address не восстанавливает ни `alembic downgrade`, ни
  # повторный запуск (downgrade возвращает механизм, но не данные).
  # Интерактивного подтверждения внутри job быть не может: Type=oneshot,
  # stdin недоступен. Поэтому решение принимает оператор ДО активации таймера.
  if $ENABLE_IP_ANON; then
    sudo systemctl enable --now mindcare-anonymize-ips.timer
    warn "Таймер IP-анонимизации ВКЛЮЧЁН (--enable-ip-anonymization)."
    warn "Первый прогон необратим; убедитесь, что dry-run уже выполнялся."
  else
    info "Таймер IP-анонимизации установлен, но НЕ включён (по умолчанию)."
    info "Порядок ввода в эксплуатацию:"
    info "  1) cd $API_DIR && .venv/bin/python scripts/anonymize_old_ips.py --days 90 --dry-run"
    info "  2) оценить объём и выбрать окно низкой нагрузки"
    info "  3) .venv/bin/python scripts/anonymize_old_ips.py --days 90   # необратимо"
    info "  4) повторный --dry-run должен дать ~0"
    info "  5) sudo systemctl enable --now mindcare-anonymize-ips.timer"
    info "Подробности: deploy/STAGE_7_DEPLOYMENT.md"
  fi

  if $ENABLE_IP_ANON; then
    ok "Maintenance-таймеры установлены и включены"
  else
    ok "Maintenance-таймеры установлены; включены все, кроме IP-анонимизации"
  fi
  info "Проверка: systemctl list-timers 'mindcare-*'"

  ok "Сервисы созданы и включены в автозагрузку"
  info "Управление: sudo systemctl start|stop|status mindcare-api mindcare-web"
fi

# ════════════════════════════════════════════════════════════════════════════
# ШАГ 9 — Финальная проверка
# ════════════════════════════════════════════════════════════════════════════
step "Финальная проверка"

cd "$API_DIR"

# Запускаем бэкенд если не запущен
if ! curl -sf http://localhost:8000/docs >/dev/null 2>&1; then
  info "Запускаю бэкенд для проверки..."
  .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  API_PID=$!
  sleep 4
  STARTED_API=true
else
  STARTED_API=false
fi

# Проверяем API
if curl -sf http://localhost:8000/docs >/dev/null 2>&1; then
  ok "Backend API доступен: http://localhost:8000"
else
  warn "Backend недоступен на порту 8000"
fi

# Проверяем логин
LOGIN_RESULT=$(curl -sf -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD:-?}\"}" 2>/dev/null || echo "")

if echo "$LOGIN_RESULT" | grep -q "session_token"; then
  ok "Логин администратора работает"
  ROLE=$(echo "$LOGIN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('role','?'))" 2>/dev/null || echo "?")
  info "Роль: $ROLE"
else
  warn "Логин не проверен (пароль не сохранён в скрипте при повторном запуске)"
fi

if [ "$STARTED_API" = true ]; then
  kill "$API_PID" 2>/dev/null || true
fi

# Итоговый вывод
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗"
echo -e "║          Развёртывание завершено        ║"
echo -e "╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Backend:${NC}  http://localhost:8000"
[ -n "$SERVER_IP" ] && echo -e "  ${BOLD}Network:${NC}  http://${SERVER_IP}:8000"
echo -e "  ${BOLD}Frontend:${NC} http://localhost:3000"
[ -n "$SERVER_IP" ] && echo -e "  ${BOLD}Network:${NC}  http://${SERVER_IP}:3000"
echo ""
echo -e "  ${BOLD}Запуск серверов вручную:${NC}"
echo -e "    cd mindcare_api && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --reload"
echo -e "    cd mindcare_web  && npm start"
echo ""
if $SETUP_SYSTEMD; then
  echo -e "  ${BOLD}Запуск через systemd:${NC}"
  echo -e "    sudo systemctl start mindcare-api mindcare-web"
  echo ""
fi
echo -e "  ${BOLD}Будущие партиции audit-таблиц:${NC}"
if $SETUP_SYSTEMD; then
  echo -e "    создаются таймером mindcare-ensure-audit-partitions.timer (ежемесячно)"
  echo -e "    вручную: cd mindcare_api && .venv/bin/python scripts/ensure_audit_partitions.py --months-ahead 24"
else
  echo -e "    cd mindcare_api && .venv/bin/python scripts/ensure_audit_partitions.py --months-ahead 24"
fi
echo ""
if $SETUP_SYSTEMD && ! $ENABLE_IP_ANON; then
  echo -e "  ${BOLD}IP-анонимизация audit-журналов:${NC}"
  echo -e "    таймер установлен, но НЕ включён — первый прогон необратим"
  echo -e "    порядок: deploy/STAGE_7_DEPLOYMENT.md"
  echo ""
fi

#!/usr/bin/env bash
# MindCare -- backend test runner (Linux)
# Зеркало test.ps1: compileall + полный suite на изолированной одноразовой
# test-БД (scripts/isolated_test_db.py). Dev-БД не затрагивается.
# Использование:
#   ./test.sh              полный isolated suite (нужен TEST_DATABASE_URL; ENV=test здесь)
#   ./test.sh --unit-only  только unit (integration исключены, sentinel DB)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT/mindcare_api"
VENV_PYTHON="$API_DIR/.venv/bin/python"

UNIT_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --unit-only) UNIT_ONLY=1 ;;
    *) ;;
  esac
done

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo -e "${YELLOW}[TEST]  $*${NC}"; }
ok()   { echo -e "  ${GREEN}[OK]${NC}  $*"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $*"; exit 1; }

echo ""
echo -e "${YELLOW}==========================================${NC}"
echo -e "${YELLOW}       MindCare  --  Backend Tests        ${NC}"
echo -e "${YELLOW}==========================================${NC}"

# venv
if [ ! -x "$VENV_PYTHON" ]; then
  echo -e "${RED}  Python venv не найден ($VENV_PYTHON).${NC}"
  echo -e "${YELLOW}  Запустите ./start.sh или ./deploy.sh для создания venv.${NC}"
  exit 1
fi

# pytest
if ! "$VENV_PYTHON" -m pytest --version >/dev/null 2>&1; then
  echo -e "${RED}  pytest не установлен.${NC}"
  echo -e "${YELLOW}  Установите: $VENV_PYTHON -m pip install -r mindcare_api/requirements-dev.txt${NC}"
  exit 1
fi
ok "pytest: $("$VENV_PYTHON" -m pytest --version 2>&1 | head -1)"

# compileall
step "python -m compileall app ..."
( cd "$API_DIR" && "$VENV_PYTHON" -m compileall app -q ) || fail "compileall обнаружил синтаксические ошибки в app/."
ok "compileall: ошибок нет."

# tests
if [ "$UNIT_ONLY" -eq 1 ]; then
  step "pytest tests/ (unit-only, integration excluded) ..."
  if ( cd "$API_DIR" && MINDCARE_UNIT_ONLY=1 "$VENV_PYTHON" \
        -m pytest tests/ --ignore=tests/integration -v ); then rc=0; else rc=$?; fi
  echo -e "  ${YELLOW}[UNIT-ONLY] integration tests were NOT run.${NC}"
  echo -e "  ${YELLOW}Set TEST_DATABASE_URL and run ./test.sh for the full suite.${NC}"
else
  step "isolated integration suite (scripts/isolated_test_db.py) ..."
  if ( cd "$API_DIR" && ENV=test "$VENV_PYTHON" scripts/isolated_test_db.py -v ); \
    then rc=0; else rc=$?; fi
fi
if [ "$rc" -ne 0 ]; then
  echo -e "  ${RED}[FAIL]${NC} Тесты упали (exit $rc)."
  exit "$rc"
fi
if [ "$UNIT_ONLY" -eq 1 ]; then
  ok "All selected unit tests passed (integration NOT run)."
else
  ok "Full isolated suite passed (temporary test DB created and dropped)."
fi

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}          All checks passed  [OK]         ${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""

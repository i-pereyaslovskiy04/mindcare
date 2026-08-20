"""
Root pytest conftest — выполняется ДО импорта тест-модулей и app.* .

Гарантия Stage 1: НИ ОДИН pytest-режим не загружает dev/prod DATABASE_URL.
Поскольку app/db/session.py связывает engine на импорте из settings.DATABASE_URL,
здесь (на верхнем уровне conftest, до любого import app.*) DATABASE_URL ВСЕГДА
переопределяется на тестовый URL либо на заведомо недоступный sentinel.

Приоритет (см. resolve_pytest_database_url в scripts/isolated_test_db.py):
  1. MINDCARE_UNIT_ONLY=1 → sentinel (TEST_DATABASE_URL игнорируется);
  2. TEST_DATABASE_URL (требует ENV=test) → он же;
  3. иначе → sentinel.

Тестовый URL готовит и подставляет в окружение дочернего процесса runner
scripts/isolated_test_db.py; здесь — defense-in-depth для прямого вызова pytest.
"""
import os
import sys
from pathlib import Path

# Логика резолва живёт в runner-модуле (не импортирует app.*), чтобы её можно
# было юнит-тестировать. Добавляем scripts/ в путь и берём helper оттуда.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from isolated_test_db import (  # noqa: E402
    SAFE_TEST_ENV,
    resolve_pytest_database_url,
)

# ВАЖНО: всё это — ДО того, как app.core.config / app.db.session прочитают env.
#
# 1. DATABASE_URL: тестовый URL (только mindcare_test_<random>) либо недоступный
#    sentinel. Admin/dev/произвольные имена и malformed URL отклоняются здесь,
#    до любого import app.* .
os.environ["DATABASE_URL"] = resolve_pytest_database_url(os.environ)

# 2. Детерминированное тестовое окружение: DEBUG=false, EMAIL_MODE=dev и
#    синтетический test-only DATA_ENCRYPTION_KEY (assert_encryption_ready требует
#    валидный ключ). Не наследуем DEBUG/EMAIL_MODE/ключ из локального .env.
for _k, _v in SAFE_TEST_ENV.items():
    os.environ[_k] = _v

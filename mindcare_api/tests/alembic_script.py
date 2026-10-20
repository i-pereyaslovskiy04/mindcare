"""
Доступ к Alembic ScriptDirectory без подключения к PostgreSQL.

Не тест-модуль (имя не начинается с `test_`), поэтому pytest его не собирает.
`ScriptDirectory` читает только файлы ревизий: URL базы ему не нужен, поэтому
проверки цепочки миграций работают и в unit-only режиме.
"""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[1]


def script_directory() -> ScriptDirectory:
    config = Config(str(API_ROOT / "alembic.ini"))
    # Путь задаётся абсолютным: alembic.ini содержит относительный
    # script_location, а pytest может запускаться из другого каталога.
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)

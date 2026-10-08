#!/usr/bin/env python3
"""
dev_oauth_callback_port.py — нужен ли локальной разработке дополнительный
listener для OAuth callback, и на каком порту.

Зачем. VK ID для localhost принимает доверенный Redirect URL только на
стандартных портах: `http://localhost` (порт 80) либо `https://localhost`
(порт 443); другие localhost-порты VK ID не поддерживает. Основной backend в
DEV слушает `:8000`, поэтому callback VK
(`http://localhost/api/auth/oauth/vk/callback`) приходит на порт, который
основной backend не слушает. DEV-launcher'ы (`start.ps1`, `start.sh`)
поднимают на этом порту второй экземпляр того же приложения — та же БД и тот
же `.env` — и гасят его вместе с основным backend.

Скрипт только ОТВЕЧАЕТ на вопрос и ничего не запускает:
  печатает номер порта — launcher должен поднять на нём listener;
  не печатает ничего    — listener не нужен.

Listener нужен, только если ОДНОВРЕМЕННО:
  - VK_OAUTH_ENABLED=true;
  - VK_OAUTH_CALLBACK_BASE_URL задан и это http:// на loopback-хосте
    (localhost / 127.0.0.1 / ::1) с портом 80 — единственным http-портом
    localhost, который принимает VK ID;
  - основной backend слушает другой порт.
Production этому не соответствует по построению: там база callback —
https-адрес сайта за reverse proxy, отдельный listener не нужен и этот скрипт
в deploy не участвует.

Использование (из mindcare_api/):
    python scripts/dev_oauth_callback_port.py [--main-port 8000]

Правила:
  - НЕ вызывать из FastAPI lifespan / app.main: приложение не должно само
    порождать процессы (reload, workers, тесты).
  - Значения настроек не печатаются — только номер порта.
  - Код возврата всегда 0: проблема с конфигурацией означает «listener не
    нужен», запуск основного backend она не блокирует.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

# Путь к корню mindcare_api/ — для импорта app.*
_SCRIPT_DIR = Path(__file__).resolve().parent
_API_ROOT = _SCRIPT_DIR.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

DEFAULT_MAIN_PORT = 8000
# Единственный http-порт localhost, который VK ID принимает в Redirect URL.
VK_LOCALHOST_HTTP_PORT = 80


def dev_callback_listener_port(config, main_port: int = DEFAULT_MAIN_PORT) -> Optional[int]:
    """Порт дополнительного DEV-listener для callback VK ID либо None."""
    # Импорт здесь: модуль остаётся импортируемым в тестах без настроек приложения.
    from app.oauth.providers.bootstrap import is_allowed_callback_url

    if getattr(config, "VK_OAUTH_ENABLED", False) is not True:
        return None
    base = getattr(config, "VK_OAUTH_CALLBACK_BASE_URL", "")
    if not isinstance(base, str) or not base.strip():
        # Своей базы у VK нет — callback приходит на основной backend.
        return None
    base = base.strip().rstrip("/")
    # Те же правила, что при регистрации адаптера: https либо http на loopback.
    if not is_allowed_callback_url(base, allow_query=False):
        return None
    parts = urlsplit(base)
    if parts.scheme != "http":
        # https — это reverse proxy (production/staging), а не локальный порт.
        return None
    port = parts.port or VK_LOCALHOST_HTTP_PORT
    if port != VK_LOCALHOST_HTTP_PORT or port == main_port:
        # Другой порт VK ID всё равно не примет; launcher не занимает чужие
        # порты (например, порт фронтенда) из-за опечатки в настройке.
        return None
    return port


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--main-port", type=int, default=DEFAULT_MAIN_PORT)
    args = parser.parse_args(argv)
    try:
        from app.core.config import settings

        port = dev_callback_listener_port(settings, main_port=args.main_port)
    except Exception:   # noqa: BLE001 — любая проблема конфигурации = listener не нужен
        return 0
    if port is not None:
        print(port)
    return 0


if __name__ == "__main__":
    sys.exit(main())

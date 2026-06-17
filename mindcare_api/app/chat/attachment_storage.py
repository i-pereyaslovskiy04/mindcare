"""
Локальное приватное хранилище файлов чата (Stage 32c).

Файлы хранятся в CHAT_FILE_STORAGE_DIR/<yyyy>/<mm>/<uuid>.
original_filename НИКОГДА не используется как путь — только storage_key.
Директория НЕ подключена через StaticFiles/Nginx — доступ только через
download endpoint с проверкой прав.

Path traversal защита на двух уровнях:
  1. _validate_key: отклоняет абсолютные пути и компоненты '..'.
  2. resolve_path: проверяет, что resolved target находится внутри storage root.
"""

import hashlib
import os
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings


class PathTraversalError(ValueError):
    """storage_key содержит небезопасные компоненты пути."""


def _validate_key(storage_key: str) -> None:
    """Отклоняет storage_key с абсолютным путём или компонентом '..'."""
    if not storage_key or not storage_key.strip():
        raise PathTraversalError("storage_key пустой")
    if os.path.isabs(storage_key):
        raise PathTraversalError("storage_key не должен быть абсолютным путём")
    parts = Path(storage_key).parts
    if ".." in parts:
        raise PathTraversalError("storage_key содержит '..'")


def _storage_root() -> Path:
    return Path(settings.CHAT_FILE_STORAGE_DIR)


def resolve_path(storage_key: str) -> Path:
    """
    Возвращает абсолютный Path для storage_key.
    Выбрасывает PathTraversalError если ключ небезопасен или выходит за
    пределы storage root.
    """
    _validate_key(storage_key)
    root = _storage_root().resolve()
    target = (root / storage_key).resolve()
    # Строгая проверка: target должен находиться внутри root.
    # Сравниваем с os.sep на конце, чтобы избежать false-match для
    # /storage/priv vs /storage/private.
    root_with_sep = str(root) + os.sep
    if not (str(target) == str(root) or str(target).startswith(root_with_sep)):
        raise PathTraversalError(
            f"storage_key выходит за пределы storage root: {storage_key!r}"
        )
    return target


def generate_storage_key() -> str:
    """
    Генерирует UUID-based относительный ключ.
    Формат: <yyyy>/<mm>/<uuid4>
    Оригинальное имя файла и расширение в ключ не включаются.
    """
    now = datetime.now(timezone.utc)
    return f"{now.year}/{now.month:02d}/{_uuid.uuid4()}"


def save_file(data: bytes, storage_key: str) -> str:
    """
    Записывает байты по storage_key. Создаёт родительские директории.
    Возвращает SHA-256 hex digest файла.
    Выбрасывает PathTraversalError или OSError при ошибке.
    """
    path = resolve_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def open_for_read(storage_key: str) -> Path:
    """
    Возвращает абсолютный Path для скачивания.
    FileNotFoundError если файла нет на диске.
    """
    path = resolve_path(storage_key)
    if not path.is_file():
        raise FileNotFoundError(f"Файл вложения не найден: {storage_key!r}")
    return path


def delete_file(storage_key: str) -> bool:
    """
    Удаляет физический файл.
    Возвращает True если файл удалён, False если файла уже не было.
    """
    try:
        path = resolve_path(storage_key)
    except PathTraversalError:
        return False
    if path.exists():
        path.unlink()
        return True
    return False


def file_exists(storage_key: str) -> bool:
    """Проверяет наличие физического файла по storage_key."""
    try:
        return resolve_path(storage_key).is_file()
    except PathTraversalError:
        return False

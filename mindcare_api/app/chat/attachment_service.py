"""
Валидация и вспомогательные функции для вложений чата (Stage 32c).

ОГРАНИЧЕНИЕ: MIME-by-magic-bytes не реализован (python-magic недоступен).
Используется заявленный UploadFile.content_type + blocklist расширений.
Upload-клиент обязан передавать корректный Content-Type.
"""

import os
from urllib.parse import quote

from fastapi import UploadFile

from app.core.config import CHAT_FILE_ALLOWED_MIME_TYPES, settings

# Расширения, запрещённые независимо от заявленного MIME.
# Исполняемые файлы и скрипты на всех платформах.
_BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".msi",
    ".sh",  ".ps1",
    ".js",  ".html", ".htm", ".svg", ".php", ".jar",
})

_MAX_FILENAME_BYTES: int = 500   # соответствует DB String(500)


class AttachmentValidationError(ValueError):
    """Ошибка валидации вложения с HTTP-статусом."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_upload(file: UploadFile, data: bytes) -> None:
    """
    Валидирует upload до записи на диск или в БД.

    Проверяет (в порядке):
      1. Пустой файл (len == 0).
      2. Превышение max size (CHAT_FILE_MAX_SIZE_MB).
      3. Отсутствие или пустое имя файла.
      4. Превышение max длины имени файла.
      5. Заблокированное расширение (_BLOCKED_EXTENSIONS).
      6. Отсутствие Content-Type.
      7. MIME-тип не в allowlist (CHAT_FILE_ALLOWED_MIME_TYPES).

    Выбрасывает AttachmentValidationError при первом нарушении.
    """
    if not data:
        raise AttachmentValidationError("Файл пустой")

    max_bytes = settings.CHAT_FILE_MAX_SIZE_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise AttachmentValidationError(
            f"Файл слишком большой. Максимум {settings.CHAT_FILE_MAX_SIZE_MB} МБ",
            status_code=413,
        )

    filename = (file.filename or "").strip()
    if not filename:
        raise AttachmentValidationError("Имя файла не указано")
    if len(filename.encode("utf-8")) > _MAX_FILENAME_BYTES:
        raise AttachmentValidationError(
            f"Имя файла слишком длинное (максимум {_MAX_FILENAME_BYTES} байт)"
        )

    ext = os.path.splitext(filename)[1].lower()
    if ext in _BLOCKED_EXTENSIONS:
        raise AttachmentValidationError(
            f"Файлы с расширением {ext!r} не допускаются"
        )

    mime = (file.content_type or "").lower().strip()
    if not mime:
        raise AttachmentValidationError("MIME-тип файла не определён")
    if mime not in CHAT_FILE_ALLOWED_MIME_TYPES:
        raise AttachmentValidationError(
            f"Тип файла {mime!r} не разрешён"
        )


def safe_content_disposition(filename: str) -> str:
    """
    Строит значение заголовка Content-Disposition с именем по RFC 5987.
    Пример: attachment; filename*=UTF-8''%D0%BE%D1%82%D1%87%D1%91%D1%82.pdf
    """
    encoded = quote(filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


def is_image_mime(mime: str) -> bool:
    """True для image/* MIME-типов (используется для is_image поля)."""
    return mime.startswith("image/")


def normalize_mime(file: UploadFile) -> str:
    """Возвращает нормализованный (lowercase, stripped) MIME из content_type."""
    return (file.content_type or "").lower().strip()

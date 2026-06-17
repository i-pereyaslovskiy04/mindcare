"""
Unit-тесты настроек chat attachments (Stage 32b).

Проверяет значения по умолчанию и корректность типов без обращения к БД.
"""

from app.core.config import (
    CHAT_FILE_ALLOWED_MIME_TYPES,
    settings,
)


class TestChatFileSettings:
    def test_max_size_mb_default(self):
        assert settings.CHAT_FILE_MAX_SIZE_MB == 20

    def test_max_files_per_message_default(self):
        assert settings.CHAT_FILE_MAX_FILES_PER_MESSAGE == 5

    def test_storage_dir_default(self):
        assert settings.CHAT_FILE_STORAGE_DIR == "storage/private/chat_attachments"

    def test_storage_backend_default(self):
        assert settings.CHAT_FILE_STORAGE_BACKEND == "local_private"

    def test_max_size_mb_is_positive(self):
        assert settings.CHAT_FILE_MAX_SIZE_MB > 0

    def test_max_files_is_positive(self):
        assert settings.CHAT_FILE_MAX_FILES_PER_MESSAGE > 0

    def test_storage_dir_is_private(self):
        # Убеждаемся, что путь не указывает на публичный media-каталог.
        d = settings.CHAT_FILE_STORAGE_DIR
        assert "private" in d or "chat" in d
        assert "uploads" not in d          # не пересекается с public media


class TestChatFileAllowedMimeTypes:
    def test_is_frozenset(self):
        assert isinstance(CHAT_FILE_ALLOWED_MIME_TYPES, frozenset)

    def test_images_included(self):
        assert "image/jpeg" in CHAT_FILE_ALLOWED_MIME_TYPES
        assert "image/png"  in CHAT_FILE_ALLOWED_MIME_TYPES
        assert "image/webp" in CHAT_FILE_ALLOWED_MIME_TYPES

    def test_pdf_included(self):
        assert "application/pdf" in CHAT_FILE_ALLOWED_MIME_TYPES

    def test_doc_docx_included(self):
        assert "application/msword" in CHAT_FILE_ALLOWED_MIME_TYPES
        assert (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in CHAT_FILE_ALLOWED_MIME_TYPES
        )

    def test_text_plain_included(self):
        assert "text/plain" in CHAT_FILE_ALLOWED_MIME_TYPES

    def test_dangerous_types_not_included(self):
        dangerous = [
            "application/x-msdownload",     # .exe
            "application/x-sh",             # .sh
            "application/x-bat",            # .bat
            "application/javascript",       # .js
            "application/zip",              # .zip
            "application/x-rar-compressed", # .rar
        ]
        for mime in dangerous:
            assert mime not in CHAT_FILE_ALLOWED_MIME_TYPES, (
                f"Опасный MIME-тип {mime!r} не должен быть в allowlist"
            )

    def test_non_empty(self):
        assert len(CHAT_FILE_ALLOWED_MIME_TYPES) > 0

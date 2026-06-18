"""
Unit-тесты валидации вложений attachment_service.validate_upload (Stage 32c).

Не требует БД или файловой системы.
"""

import io
from unittest.mock import MagicMock, patch

import pytest

from app.chat.attachment_service import (
    AttachmentValidationError,
    is_image_mime,
    normalize_mime,
    safe_content_disposition,
    validate_upload,
)


def _make_file(
    filename: str = "test.pdf",
    content_type: str = "application/pdf",
) -> MagicMock:
    """Создаёт фиктивный UploadFile."""
    f = MagicMock()
    f.filename     = filename
    f.content_type = content_type
    return f


class TestValidateUpload:
    # ─── Нормальный случай ──────────────────────────────────────────────────

    def test_valid_pdf(self):
        validate_upload(_make_file("doc.pdf", "application/pdf"), b"x" * 100)

    def test_valid_jpeg(self):
        validate_upload(_make_file("img.jpg", "image/jpeg"), b"x" * 1000)

    def test_valid_png(self):
        validate_upload(_make_file("img.png", "image/png"), b"x" * 500)

    def test_valid_webp(self):
        validate_upload(
            _make_file("study_abroad_scholarships_2024.webp", "image/webp"),
            b"x" * 500,
        )

    def test_valid_docx(self):
        validate_upload(
            _make_file(
                "report.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            b"x" * 200,
        )

    def test_valid_xlsx(self):
        validate_upload(
            _make_file(
                "data.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            b"x" * 200,
        )

    def test_valid_pptx(self):
        validate_upload(
            _make_file(
                "slides.pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ),
            b"x" * 200,
        )

    def test_valid_text(self):
        validate_upload(_make_file("notes.txt", "text/plain"), b"hello world")

    # ─── Пустой файл ────────────────────────────────────────────────────────

    def test_empty_file_rejected(self):
        with pytest.raises(AttachmentValidationError, match="пустой"):
            validate_upload(_make_file(), b"")

    # ─── Превышение размера ──────────────────────────────────────────────────

    def test_too_large_file_rejected(self):
        max_bytes = 20 * 1024 * 1024
        with pytest.raises(AttachmentValidationError) as exc_info:
            validate_upload(_make_file(), b"x" * (max_bytes + 1))
        assert exc_info.value.status_code == 413

    def test_exactly_max_size_accepted(self):
        max_bytes = 20 * 1024 * 1024
        validate_upload(_make_file(), b"x" * max_bytes)

    # ─── Имя файла ───────────────────────────────────────────────────────────

    def test_empty_filename_rejected(self):
        with pytest.raises(AttachmentValidationError, match="Имя файла"):
            validate_upload(_make_file(filename=""), b"data")

    def test_whitespace_only_filename_rejected(self):
        with pytest.raises(AttachmentValidationError, match="Имя файла"):
            validate_upload(_make_file(filename="   "), b"data")

    def test_too_long_filename_rejected(self):
        long_name = "a" * 501 + ".pdf"
        with pytest.raises(AttachmentValidationError, match="длинное"):
            validate_upload(_make_file(filename=long_name), b"data")

    def test_exactly_500_byte_filename_accepted(self):
        # 496 символов + ".pdf" = 500 байт
        name = "a" * 496 + ".pdf"
        validate_upload(_make_file(filename=name), b"data")

    # ─── Заблокированные расширения ──────────────────────────────────────────

    @pytest.mark.parametrize("ext,filename", [
        (".exe",  "malware.exe"),
        (".bat",  "run.bat"),
        (".cmd",  "script.cmd"),
        (".com",  "old.com"),
        (".msi",  "setup.msi"),
        (".sh",   "exploit.sh"),
        (".ps1",  "pwshell.ps1"),
        (".vbs",  "macro.vbs"),
        (".scr",  "screensaver.scr"),
        (".js",   "attack.js"),
        (".html", "phish.html"),
        (".htm",  "phish.htm"),
        (".svg",  "xss.svg"),
        (".php",  "shell.php"),
        (".jar",  "evil.jar"),
    ])
    def test_blocked_extension_rejected(self, ext, filename):
        with pytest.raises(AttachmentValidationError, match="расширени"):
            validate_upload(
                _make_file(filename=filename, content_type="application/octet-stream"),
                b"x" * 100,
            )

    def test_case_insensitive_extension(self):
        with pytest.raises(AttachmentValidationError, match="расширени"):
            validate_upload(
                _make_file(filename="MALWARE.EXE", content_type="application/octet-stream"),
                b"x",
            )

    def test_svg_rejected_with_image_mime(self):
        # SVG запрещён даже с корректным image/svg+xml MIME — может содержать скрипты.
        with pytest.raises(AttachmentValidationError, match="расширени"):
            validate_upload(_make_file("xss.svg", "image/svg+xml"), b"x")

    def test_double_extension_exe_rejected(self):
        # Последнее расширение .exe должно блокировать файл.
        with pytest.raises(AttachmentValidationError, match="расширени"):
            validate_upload(
                _make_file("document.pdf.exe", "application/pdf"), b"x"
            )

    def test_dangerous_extension_with_safe_mime_rejected(self):
        # .exe с заявленным text/plain — расширение проверяется до MIME.
        with pytest.raises(AttachmentValidationError, match="расширени"):
            validate_upload(_make_file("run.exe", "text/plain"), b"x")

    # ─── MIME-тип ─────────────────────────────────────────────────────────────

    def test_missing_content_type_rejected(self):
        with pytest.raises(AttachmentValidationError, match="MIME"):
            validate_upload(_make_file(content_type=""), b"data")

    def test_none_content_type_rejected(self):
        with pytest.raises(AttachmentValidationError, match="MIME"):
            validate_upload(_make_file(content_type=None), b"data")

    def test_dangerous_mime_rejected(self):
        # Имя файла с безопасным расширением, но опасный MIME
        with pytest.raises(AttachmentValidationError, match="не разрешён"):
            validate_upload(
                _make_file("document.pdf", "application/x-msdownload"), b"x"
            )

    def test_zip_rejected(self):
        with pytest.raises(AttachmentValidationError, match="не разрешён"):
            validate_upload(_make_file("archive.zip", "application/zip"), b"x")


class TestHelpers:
    def test_is_image_mime_true(self):
        assert is_image_mime("image/jpeg") is True
        assert is_image_mime("image/png")  is True
        assert is_image_mime("image/webp") is True

    def test_is_image_mime_false(self):
        assert is_image_mime("application/pdf")  is False
        assert is_image_mime("text/plain")        is False

    def test_safe_content_disposition_ascii(self):
        result = safe_content_disposition("report.pdf")
        assert result.startswith("attachment; filename*=UTF-8''")
        assert "report.pdf" in result

    def test_safe_content_disposition_cyrillic(self):
        result = safe_content_disposition("отчёт.pdf")
        assert "%" in result   # закодировано

    def test_normalize_mime_lowercase(self):
        f = _make_file(content_type="Image/JPEG")
        assert normalize_mime(f) == "image/jpeg"

    def test_normalize_mime_strips(self):
        f = _make_file(content_type="  application/pdf  ")
        assert normalize_mime(f) == "application/pdf"

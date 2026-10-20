"""
Unit-тесты attachment_storage (Stage 32c).

Проверяет: path traversal protection, generate_storage_key,
save_file/open_for_read/delete_file/file_exists.
Не требует БД — работает с tmp-директорией.
"""

import hashlib
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.chat.attachment_storage import (
    PathTraversalError,
    delete_file,
    file_exists,
    generate_storage_key,
    open_for_read,
    resolve_path,
    save_file,
)


# ─── Фикстура временного storage root ────────────────────────────────────────

@pytest.fixture()
def tmp_storage(tmp_path):
    """Перенаправляет CHAT_FILE_STORAGE_DIR в tmp_path на время теста."""
    storage_dir = str(tmp_path / "chat_attachments")
    with patch("app.chat.attachment_storage.settings") as mock_settings:
        mock_settings.CHAT_FILE_STORAGE_DIR = storage_dir
        yield storage_dir


# ─── PathTraversalError ───────────────────────────────────────────────────────

class TestPathTraversalProtection:
    def test_empty_key_rejected(self, tmp_storage):
        with pytest.raises(PathTraversalError):
            resolve_path("")

    def test_whitespace_only_key_rejected(self, tmp_storage):
        with pytest.raises(PathTraversalError):
            resolve_path("   ")

    def test_absolute_path_rejected(self, tmp_storage):
        with pytest.raises(PathTraversalError):
            resolve_path("/etc/passwd")

    def test_dotdot_root_rejected(self, tmp_storage):
        with pytest.raises(PathTraversalError):
            resolve_path("../outside")

    def test_dotdot_nested_rejected(self, tmp_storage):
        with pytest.raises(PathTraversalError):
            resolve_path("2026/06/../../../etc/passwd")

    def test_dotdot_component_rejected(self, tmp_storage):
        with pytest.raises(PathTraversalError):
            resolve_path("foo/../../etc/shadow")

    def test_valid_key_accepted(self, tmp_storage):
        path = resolve_path("2026/06/some-uuid")
        # Должен быть внутри storage root
        assert str(path).startswith(tmp_storage)

    def test_valid_uuid_key_accepted(self, tmp_storage):
        key = f"2026/07/{uuid.uuid4()}"
        path = resolve_path(key)
        assert str(path).startswith(tmp_storage)


# ─── generate_storage_key ─────────────────────────────────────────────────────

class TestGenerateStorageKey:
    def test_format_yyyy_mm_uuid(self):
        key = generate_storage_key()
        parts = key.split("/")
        assert len(parts) == 3
        year, month, uid = parts
        assert year.isdigit() and len(year) == 4
        assert month.isdigit() and 1 <= int(month) <= 12
        # Должен быть валидным UUID
        uuid.UUID(uid)

    def test_no_original_filename(self):
        key = generate_storage_key()
        assert "." not in key.split("/")[-1]   # нет расширения

    def test_uniqueness(self):
        keys = {generate_storage_key() for _ in range(20)}
        assert len(keys) == 20

    def test_relative_path(self):
        key = generate_storage_key()
        assert not os.path.isabs(key)


# ─── save_file / open_for_read / delete_file / file_exists ───────────────────

class TestSaveFile:
    def test_writes_data(self, tmp_storage):
        key  = f"2026/06/{uuid.uuid4()}"
        data = b"hello test file"
        save_file(data, key)
        path = Path(tmp_storage) / key
        assert path.read_bytes() == data

    def test_returns_sha256(self, tmp_storage):
        key      = f"2026/06/{uuid.uuid4()}"
        data     = b"checksum test"
        checksum = save_file(data, key)
        expected = hashlib.sha256(data).hexdigest()
        assert checksum == expected

    def test_creates_parent_dirs(self, tmp_storage):
        key = f"2026/12/deep/{uuid.uuid4()}"
        save_file(b"data", key)
        assert (Path(tmp_storage) / key).exists()

    def test_traversal_rejected(self, tmp_storage):
        with pytest.raises(PathTraversalError):
            save_file(b"x", "../escape")


class TestOpenForRead:
    def test_returns_path_for_existing_file(self, tmp_storage):
        key = f"2026/06/{uuid.uuid4()}"
        save_file(b"content", key)
        path = open_for_read(key)
        assert path.is_file()

    def test_raises_for_missing_file(self, tmp_storage):
        with pytest.raises(FileNotFoundError):
            open_for_read(f"2026/06/{uuid.uuid4()}")

    def test_traversal_rejected(self, tmp_storage):
        with pytest.raises(PathTraversalError):
            open_for_read("../../etc/passwd")


class TestDeleteFile:
    def test_deletes_existing_file(self, tmp_storage):
        key = f"2026/06/{uuid.uuid4()}"
        save_file(b"to_delete", key)
        result = delete_file(key)
        assert result is True
        assert not (Path(tmp_storage) / key).exists()

    def test_returns_false_for_missing_file(self, tmp_storage):
        result = delete_file(f"2026/06/{uuid.uuid4()}")
        assert result is False

    def test_traversal_returns_false(self, tmp_storage):
        result = delete_file("../../escape")
        assert result is False


class TestFileExists:
    def test_true_for_existing(self, tmp_storage):
        key = f"2026/06/{uuid.uuid4()}"
        save_file(b"exists", key)
        assert file_exists(key) is True

    def test_false_for_missing(self, tmp_storage):
        assert file_exists(f"2026/06/{uuid.uuid4()}") is False

    def test_false_for_traversal(self, tmp_storage):
        assert file_exists("../../etc/passwd") is False

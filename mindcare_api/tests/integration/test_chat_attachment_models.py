"""
DB/model constraint tests for Chat Attachments foundation (Stage 32b).

Покрывает схему и ограничения БД:
  - ChatAttachment можно создать с корректными данными;
  - message_id nullable (orphan pre-upload attachment);
  - message_id NOT NULL (attachment привязан к message);
  - uuid UNIQUE (дубликат отклоняется);
  - storage_key UNIQUE (дубликат отклоняется);
  - file_size NOT NULL;
  - original_filename NOT NULL;
  - mime_type NOT NULL;
  - checksum_sha256 nullable (вычисляется при upload, Stage 32c);
  - relationship ChatAttachment.message, .conversation, .uploader работают;
  - relationship ChatMessage.attachments работает;
  - soft delete через deleted_at.

Требования: dev PostgreSQL на alembic head (a9b3e1f7c2d4).
Upload/download API в этом тесте НЕ проверяются — Stage 32c.
"""

import uuid as _uuid

import bcrypt
import pytest
from sqlalchemy.exc import IntegrityError

from app.auth import storage as auth_storage
from app.db.models import (
    ChatAttachment, ChatConversation, ChatMessage, TherapyEngagement,
)
from app.db.session import SessionLocal

PASSWORD = "SecurePass42!"

_DUMMY_STORAGE_KEY_PREFIX = "2026/06/"
_DUMMY_MIME = "application/pdf"
_DUMMY_SIZE = 102_400  # 100 KB


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(role: str) -> int:
    user = auth_storage.save_user({
        "name":            f"Attach Test {role.capitalize()}",
        "email":           f"integ_att_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    return int(user["id"])


def _make_engagement(student_id: int, psychologist_id: int) -> int:
    with SessionLocal() as db:
        eng = TherapyEngagement(
            client_id=student_id,
            psychologist_id=psychologist_id,
            status="active",
        )
        db.add(eng)
        db.commit()
        db.refresh(eng)
        return eng.id


def _make_conversation(engagement_id: int) -> int:
    with SessionLocal() as db:
        conv = ChatConversation(engagement_id=engagement_id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv.id


def _make_message(conversation_id: int, sender_id: int) -> int:
    with SessionLocal() as db:
        msg = ChatMessage(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content="enc:v1:dummyciphertextfortest",
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg.id


def _unique_key() -> str:
    return f"{_DUMMY_STORAGE_KEY_PREFIX}{_uuid.uuid4()}.pdf"


def _make_attachment(
    *,
    conversation_id: int,
    uploader_id: int,
    message_id: int | None = None,
    storage_key: str | None = None,
    mime_type: str = _DUMMY_MIME,
    file_size: int = _DUMMY_SIZE,
    checksum: str | None = None,
    is_image: bool = False,
) -> int:
    key = storage_key or _unique_key()
    with SessionLocal() as db:
        att = ChatAttachment(
            conversation_id=conversation_id,
            message_id=message_id,
            uploader_id=uploader_id,
            original_filename="test_document.pdf",
            storage_key=key,
            mime_type=mime_type,
            file_size=file_size,
            checksum_sha256=checksum,
            is_image=is_image,
        )
        db.add(att)
        db.commit()
        db.refresh(att)
        return att.id


# ─── 1. Создание attachment ───────────────────────────────────────────────────

class TestChatAttachmentCreate:
    def test_orphan_attachment_message_id_null(self, client):
        """Attachment без message_id (pre-upload window) создаётся."""
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        att_id = _make_attachment(conversation_id=conv_id, uploader_id=student_id)

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.message_id is None          # nullable — pre-upload
            assert att.conversation_id == conv_id
            assert att.uploader_id == student_id
            assert att.uuid is not None
            assert att.storage_key is not None
            assert att.mime_type == _DUMMY_MIME
            assert att.file_size == _DUMMY_SIZE
            assert att.checksum_sha256 is None     # заполняется при upload (Stage 32c)
            assert att.is_image is False
            assert att.encrypted_at_rest is False
            assert att.storage_backend == "local_private"
            assert att.created_at is not None
            assert att.deleted_at is None

    def test_attachment_with_message_id(self, client):
        """Attachment привязан к message_id после создания сообщения."""
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)
        msg_id     = _make_message(conv_id, student_id)

        att_id = _make_attachment(
            conversation_id=conv_id,
            uploader_id=student_id,
            message_id=msg_id,
        )

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.message_id == msg_id

    def test_attachment_with_checksum(self, client):
        """checksum_sha256 сохраняется, если передан."""
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        sha = "a" * 64   # valid SHA-256 hex length
        att_id = _make_attachment(
            conversation_id=conv_id,
            uploader_id=student_id,
            checksum=sha,
        )

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.checksum_sha256 == sha

    def test_image_attachment(self, client):
        """is_image=True корректно сохраняется."""
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        att_id = _make_attachment(
            conversation_id=conv_id,
            uploader_id=student_id,
            mime_type="image/jpeg",
            is_image=True,
        )

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.is_image is True
            assert att.mime_type == "image/jpeg"


# ─── 2. Relationships ─────────────────────────────────────────────────────────

class TestChatAttachmentRelationships:
    def test_attachment_conversation_relationship(self, client):
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        att_id = _make_attachment(conversation_id=conv_id, uploader_id=student_id)

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.conversation.id == conv_id

    def test_attachment_uploader_relationship(self, client):
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        att_id = _make_attachment(conversation_id=conv_id, uploader_id=student_id)

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.uploader.id == student_id

    def test_attachment_message_relationship(self, client):
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)
        msg_id     = _make_message(conv_id, student_id)

        att_id = _make_attachment(
            conversation_id=conv_id,
            uploader_id=student_id,
            message_id=msg_id,
        )

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.message is not None
            assert att.message.id == msg_id

    def test_message_attachments_relationship(self, client):
        """ChatMessage.attachments возвращает список вложений."""
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)
        msg_id     = _make_message(conv_id, student_id)

        att_id_1 = _make_attachment(
            conversation_id=conv_id,
            uploader_id=student_id,
            message_id=msg_id,
        )
        att_id_2 = _make_attachment(
            conversation_id=conv_id,
            uploader_id=student_id,
            message_id=msg_id,
        )

        with SessionLocal() as db:
            msg = db.query(ChatMessage).filter(ChatMessage.id == msg_id).one()
            assert len(msg.attachments) == 2
            ids = {a.id for a in msg.attachments}
            assert att_id_1 in ids
            assert att_id_2 in ids

    def test_orphan_attachment_message_relationship_is_none(self, client):
        """Orphan attachment (message_id=NULL) → att.message is None."""
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        att_id = _make_attachment(conversation_id=conv_id, uploader_id=student_id)

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.message is None


# ─── 3. Unique constraints ────────────────────────────────────────────────────

class TestChatAttachmentUniqueConstraints:
    def test_duplicate_uuid_rejected(self, client):
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        shared_uuid = _uuid.uuid4()
        with SessionLocal() as db:
            db.add(ChatAttachment(
                uuid=shared_uuid,
                conversation_id=conv_id,
                uploader_id=student_id,
                original_filename="f1.pdf",
                storage_key=_unique_key(),
                mime_type="application/pdf",
                file_size=1000,
            ))
            db.commit()

        with pytest.raises(IntegrityError):
            with SessionLocal() as db:
                db.add(ChatAttachment(
                    uuid=shared_uuid,     # дублирует uuid
                    conversation_id=conv_id,
                    uploader_id=student_id,
                    original_filename="f2.pdf",
                    storage_key=_unique_key(),
                    mime_type="application/pdf",
                    file_size=2000,
                ))
                db.commit()

    def test_duplicate_storage_key_rejected(self, client):
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        shared_key = _unique_key()
        with SessionLocal() as db:
            db.add(ChatAttachment(
                conversation_id=conv_id,
                uploader_id=student_id,
                original_filename="file1.pdf",
                storage_key=shared_key,
                mime_type="application/pdf",
                file_size=1000,
            ))
            db.commit()

        with pytest.raises(IntegrityError):
            with SessionLocal() as db:
                db.add(ChatAttachment(
                    conversation_id=conv_id,
                    uploader_id=student_id,
                    original_filename="file2.pdf",
                    storage_key=shared_key,   # дублирует storage_key
                    mime_type="application/pdf",
                    file_size=2000,
                ))
                db.commit()


# ─── 4. NOT NULL constraints ──────────────────────────────────────────────────

class TestChatAttachmentNotNullConstraints:
    def _base_kwargs(self, conv_id: int, uploader_id: int) -> dict:
        return {
            "conversation_id":  conv_id,
            "uploader_id":      uploader_id,
            "original_filename": "test.pdf",
            "storage_key":      _unique_key(),
            "mime_type":        "application/pdf",
            "file_size":        1024,
        }

    def _setup(self) -> tuple[int, int]:
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)
        return conv_id, student_id

    def test_file_size_not_null_rejected(self, client):
        conv_id, uploader_id = self._setup()
        kwargs = self._base_kwargs(conv_id, uploader_id)
        kwargs["file_size"] = None
        with pytest.raises((IntegrityError, Exception)):
            with SessionLocal() as db:
                db.add(ChatAttachment(**kwargs))
                db.commit()

    def test_original_filename_not_null_rejected(self, client):
        conv_id, uploader_id = self._setup()
        kwargs = self._base_kwargs(conv_id, uploader_id)
        kwargs["original_filename"] = None
        with pytest.raises((IntegrityError, Exception)):
            with SessionLocal() as db:
                db.add(ChatAttachment(**kwargs))
                db.commit()

    def test_mime_type_not_null_rejected(self, client):
        conv_id, uploader_id = self._setup()
        kwargs = self._base_kwargs(conv_id, uploader_id)
        kwargs["mime_type"] = None
        with pytest.raises((IntegrityError, Exception)):
            with SessionLocal() as db:
                db.add(ChatAttachment(**kwargs))
                db.commit()

    def test_storage_key_not_null_rejected(self, client):
        conv_id, uploader_id = self._setup()
        kwargs = self._base_kwargs(conv_id, uploader_id)
        kwargs["storage_key"] = None
        with pytest.raises((IntegrityError, Exception)):
            with SessionLocal() as db:
                db.add(ChatAttachment(**kwargs))
                db.commit()


# ─── 5. FK constraints ────────────────────────────────────────────────────────

class TestChatAttachmentFKConstraints:
    def test_nonexistent_conversation_rejected(self, client):
        student_id = _make_user("student")
        with pytest.raises(IntegrityError):
            with SessionLocal() as db:
                db.add(ChatAttachment(
                    conversation_id=999_999_999,   # не существует
                    uploader_id=student_id,
                    original_filename="f.pdf",
                    storage_key=_unique_key(),
                    mime_type="application/pdf",
                    file_size=500,
                ))
                db.commit()

    def test_nonexistent_uploader_rejected(self, client):
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        with pytest.raises(IntegrityError):
            with SessionLocal() as db:
                db.add(ChatAttachment(
                    conversation_id=conv_id,
                    uploader_id=999_999_999,   # не существует
                    original_filename="f.pdf",
                    storage_key=_unique_key(),
                    mime_type="application/pdf",
                    file_size=500,
                ))
                db.commit()

    def test_nonexistent_message_id_rejected(self, client):
        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        with pytest.raises(IntegrityError):
            with SessionLocal() as db:
                db.add(ChatAttachment(
                    conversation_id=conv_id,
                    message_id=999_999_999,    # не существует
                    uploader_id=student_id,
                    original_filename="f.pdf",
                    storage_key=_unique_key(),
                    mime_type="application/pdf",
                    file_size=500,
                ))
                db.commit()


# ─── 6. Soft delete ───────────────────────────────────────────────────────────

class TestChatAttachmentSoftDelete:
    def test_soft_delete_sets_deleted_at(self, client):
        from datetime import datetime, timezone

        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        att_id = _make_attachment(conversation_id=conv_id, uploader_id=student_id)

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            assert att.deleted_at is None

            att.deleted_at = now
            db.commit()
            db.refresh(att)
            assert att.deleted_at is not None

    def test_soft_delete_does_not_remove_row(self, client):
        from datetime import datetime, timezone

        student_id = _make_user("student")
        psych_id   = _make_user("psychologist")
        eng_id     = _make_engagement(student_id, psych_id)
        conv_id    = _make_conversation(eng_id)

        att_id = _make_attachment(conversation_id=conv_id, uploader_id=student_id)

        with SessionLocal() as db:
            att = db.query(ChatAttachment).filter(ChatAttachment.id == att_id).one()
            att.deleted_at = datetime.now(timezone.utc)
            db.commit()

        # Запись по-прежнему доступна (без фильтра deleted_at IS NULL).
        with SessionLocal() as db:
            still_exists = (
                db.query(ChatAttachment).filter(ChatAttachment.id == att_id).first()
            )
            assert still_exists is not None
            assert still_exists.deleted_at is not None

"""
SQLAlchemy-запросы Chat MVP.

Принципы (по паттерну session_notes/storage.py):
  - permission-фильтры применяются в SQL до выборки;
  - decrypt_text вызывается ТОЛЬКО при формировании ответа участнику
    (после проверки прав в service);
  - plaintext никогда не пишется в БД (encrypt_text перед INSERT)
    и не логируется;
  - deleted_at IS NULL — во всех выборках сообщений (soft delete).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError

from app.core.encryption import decrypt_text, encrypt_text
from app.db.session import SessionLocal
from app.db.models import ChatConversation, ChatMessage, TherapyEngagement, User


# ─── Mappers ──────────────────────────────────────────────────────────────────

def _message_to_dict(
    msg: ChatMessage,
    *,
    current_user_id: int,
    client_id: Optional[int],
) -> dict:
    """Response dict с расшифрованным content. Вызывать только после проверки прав.

    system-сообщение (message_kind='system', sender_id IS NULL) не обращается
    к engagement.client_id: sender_role='system', is_mine=False.
    """
    try:
        plaintext = decrypt_text(msg.content)
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Message decryption failed (id={msg.id})") from exc

    if msg.message_kind == "system":
        sender_role = "system"
        is_mine = False
    else:
        sender_role = "student" if msg.sender_id == client_id else "psychologist"
        is_mine = msg.sender_id == current_user_id

    return {
        "id":          msg.id,
        "uuid":        str(msg.uuid),
        "sender_id":   msg.sender_id,
        "sender_role": sender_role,
        "is_mine":     is_mine,
        "content":     plaintext,
        "created_at":  msg.created_at,
        "read_at":     msg.read_at,
    }


# ─── Engagements / conversations ─────────────────────────────────────────────

def get_engagement_for_student(student_id: int) -> Optional[TherapyEngagement]:
    """Активный engagement приоритетно, иначе самый свежий исторический."""
    with SessionLocal() as db:
        eng = (
            db.query(TherapyEngagement)
            .filter(
                TherapyEngagement.client_id == student_id,
                TherapyEngagement.status == "active",
                TherapyEngagement.ended_at.is_(None),
            )
            .first()
        )
        if eng is None:
            eng = (
                db.query(TherapyEngagement)
                .filter(TherapyEngagement.client_id == student_id)
                .order_by(desc(TherapyEngagement.started_at))
                .first()
            )
        if eng is not None:
            db.expunge(eng)
        return eng


def get_conversation_for_engagement(engagement_id: int) -> Optional[ChatConversation]:
    with SessionLocal() as db:
        conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.engagement_id == engagement_id)
            .first()
        )
        if conv is not None:
            db.expunge(conv)
        return conv


def get_or_create_conversation(engagement_id: int) -> tuple[ChatConversation, bool]:
    """
    Lazy-create беседы. Возвращает (conversation, created).
    Race condition закрыт UNIQUE(engagement_id): проигравший INSERT
    ловит IntegrityError и перечитывает существующую строку.
    """
    existing = get_conversation_for_engagement(engagement_id)
    if existing is not None:
        return existing, False

    with SessionLocal() as db:
        conv = ChatConversation(engagement_id=engagement_id)
        db.add(conv)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            conv = (
                db.query(ChatConversation)
                .filter(ChatConversation.engagement_id == engagement_id)
                .one()
            )
            db.expunge(conv)
            return conv, False
        db.refresh(conv)
        db.expunge(conv)
        return conv, True


def get_conversation_by_uuid(
    conversation_uuid: str,
) -> Optional[tuple[ChatConversation, TherapyEngagement]]:
    """Беседа вместе с её engagement (для проверки участника в service)."""
    with SessionLocal() as db:
        row = (
            db.query(ChatConversation, TherapyEngagement)
            .join(
                TherapyEngagement,
                TherapyEngagement.id == ChatConversation.engagement_id,
            )
            .filter(ChatConversation.uuid == conversation_uuid)
            .first()
        )
        if row is None:
            return None
        conv, eng = row
        db.expunge(conv)
        db.expunge(eng)
        return conv, eng


def get_user_brief(user_id: int) -> Optional[dict]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return None
        return {"id": user.id, "full_name": user.full_name}


def list_conversations_for_psychologist(
    psychologist_id: int,
    *,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """Список бесед психолога: студент, статус engagement, unread_count.
    Preview последнего сообщения намеренно не возвращается (N decrypt)."""
    with SessionLocal() as db:
        unread_subq = (
            select(func.count(ChatMessage.id))
            .where(
                ChatMessage.conversation_id == ChatConversation.id,
                ChatMessage.sender_id != psychologist_id,
                ChatMessage.read_at.is_(None),
                ChatMessage.deleted_at.is_(None),
            )
            .correlate(ChatConversation)
            .scalar_subquery()
        )

        base = (
            db.query(ChatConversation, TherapyEngagement, User, unread_subq)
            .join(
                TherapyEngagement,
                TherapyEngagement.id == ChatConversation.engagement_id,
            )
            .join(User, User.id == TherapyEngagement.client_id)
            .filter(TherapyEngagement.psychologist_id == psychologist_id)
        )

        total = (
            db.query(func.count(ChatConversation.id))
            .join(
                TherapyEngagement,
                TherapyEngagement.id == ChatConversation.engagement_id,
            )
            .filter(TherapyEngagement.psychologist_id == psychologist_id)
            .scalar()
        ) or 0

        rows = (
            base.order_by(
                desc(func.coalesce(
                    ChatConversation.last_message_at, ChatConversation.created_at,
                ))
            )
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for conv, eng, student, unread in rows:
            items.append({
                "uuid":              str(conv.uuid),
                "student":           {"id": student.id, "full_name": student.full_name},
                "engagement_status": eng.status,
                "last_message_at":   conv.last_message_at,
                "unread_count":      int(unread or 0),
            })
        return items, total


# ─── Messages ─────────────────────────────────────────────────────────────────

def get_messages(
    conversation_id: int,
    *,
    current_user_id: int,
    client_id: int,
    limit: int = 50,
    before_id: Optional[int] = None,
    after_id: Optional[int] = None,
) -> list[dict]:
    """
    Сообщения беседы по возрастанию id.
      before_id — история: limit сообщений старше указанного;
      after_id  — polling: только новые после указанного;
      без курсоров — последние limit сообщений.
    """
    with SessionLocal() as db:
        q = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.deleted_at.is_(None),
        )

        if after_id is not None:
            msgs = (
                q.filter(ChatMessage.id > after_id)
                .order_by(ChatMessage.id)
                .limit(limit)
                .all()
            )
        elif before_id is not None:
            msgs = (
                q.filter(ChatMessage.id < before_id)
                .order_by(desc(ChatMessage.id))
                .limit(limit)
                .all()
            )
            msgs.reverse()
        else:
            msgs = (
                q.order_by(desc(ChatMessage.id))
                .limit(limit)
                .all()
            )
            msgs.reverse()

        return [
            _message_to_dict(
                m, current_user_id=current_user_id, client_id=client_id,
            )
            for m in msgs
        ]


def create_message(
    conversation_id: int,
    *,
    sender_id: int,
    content: str,
    client_id: int,
) -> dict:
    """Encrypt-on-write + обновление last_message_at в одной транзакции."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        msg = ChatMessage(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=encrypt_text(content),
        )
        db.add(msg)
        db.query(ChatConversation).filter(
            ChatConversation.id == conversation_id
        ).update(
            {"last_message_at": now, "updated_at": now},
            synchronize_session=False,
        )
        db.commit()
        db.refresh(msg)

        return {
            "id":          msg.id,
            "uuid":        str(msg.uuid),
            "sender_id":   msg.sender_id,
            "sender_role": "student" if sender_id == client_id else "psychologist",
            "is_mine":     True,
            "content":     content,   # plaintext отправителю, без повторного decrypt
            "created_at":  msg.created_at,
            "read_at":     msg.read_at,
        }


def mark_read(conversation_id: int, *, reader_id: int) -> int:
    """Помечает прочитанными только входящие непрочитанные сообщения."""
    with SessionLocal() as db:
        updated = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.sender_id != reader_id,
                ChatMessage.read_at.is_(None),
                ChatMessage.deleted_at.is_(None),
            )
            .update(
                {"read_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )
        db.commit()
        return updated


def unread_count(conversation_id: int, *, user_id: int) -> int:
    """Входящие непрочитанные для user_id."""
    with SessionLocal() as db:
        return (
            db.query(func.count(ChatMessage.id))
            .filter(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.sender_id != user_id,
                ChatMessage.read_at.is_(None),
                ChatMessage.deleted_at.is_(None),
            )
            .scalar()
        ) or 0


# ─── System conversation (Stage 29b) ────────────────────────────────────────
#
# Read-only беседа type='system' с одним получателем (recipient_id). У неё нет
# engagement и нет client_id; sender_id всех сообщений IS NULL (message_kind=
# 'system'). content шифруется тем же encrypt_text, что и engagement-переписка.

def get_system_conversation(recipient_id: int) -> Optional[ChatConversation]:
    with SessionLocal() as db:
        conv = (
            db.query(ChatConversation)
            .filter(
                ChatConversation.type == "system",
                ChatConversation.recipient_id == recipient_id,
            )
            .first()
        )
        if conv is not None:
            db.expunge(conv)
        return conv


def get_or_create_system_conversation(
    recipient_id: int,
) -> tuple[ChatConversation, bool]:
    """Lazy-create system-беседы. Гонку закрывает partial UNIQUE(recipient_id)."""
    existing = get_system_conversation(recipient_id)
    if existing is not None:
        return existing, False

    with SessionLocal() as db:
        conv = ChatConversation(type="system", recipient_id=recipient_id)
        db.add(conv)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            conv = (
                db.query(ChatConversation)
                .filter(
                    ChatConversation.type == "system",
                    ChatConversation.recipient_id == recipient_id,
                )
                .one()
            )
            db.expunge(conv)
            return conv, False
        db.refresh(conv)
        db.expunge(conv)
        return conv, True


def create_system_message(
    recipient_id: int,
    *,
    event_key: str,
    text: str,
) -> dict:
    """
    Get-or-create system-беседы + encrypt-on-write одного сообщения.
    Идемпотентность: повторный вызов с тем же (conversation, event_key)
    не создаёт дубль (partial UNIQUE → IntegrityError → skipped).

    Возвращает {"created": bool, "conversation_id": int}.
    Plaintext text не возвращается и не логируется.
    """
    conv, _created_conv = get_or_create_system_conversation(recipient_id)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        msg = ChatMessage(
            conversation_id=conv.id,
            message_kind="system",
            sender_id=None,
            event_key=event_key,
            content=encrypt_text(text),
        )
        db.add(msg)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return {"created": False, "conversation_id": conv.id}

        db.query(ChatConversation).filter(
            ChatConversation.id == conv.id
        ).update(
            {"last_message_at": now, "updated_at": now},
            synchronize_session=False,
        )
        db.commit()
        return {"created": True, "conversation_id": conv.id}


def get_system_messages(
    recipient_id: int,
    *,
    limit: int = 50,
    before_id: Optional[int] = None,
    after_id: Optional[int] = None,
) -> list[dict]:
    """Сообщения system-беседы получателя по возрастанию id (та же пагинация)."""
    conv = get_system_conversation(recipient_id)
    if conv is None:
        return []

    with SessionLocal() as db:
        q = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id,
            ChatMessage.deleted_at.is_(None),
        )

        if after_id is not None:
            msgs = (
                q.filter(ChatMessage.id > after_id)
                .order_by(ChatMessage.id)
                .limit(limit)
                .all()
            )
        elif before_id is not None:
            msgs = (
                q.filter(ChatMessage.id < before_id)
                .order_by(desc(ChatMessage.id))
                .limit(limit)
                .all()
            )
            msgs.reverse()
        else:
            msgs = (
                q.order_by(desc(ChatMessage.id))
                .limit(limit)
                .all()
            )
            msgs.reverse()

        return [
            _message_to_dict(m, current_user_id=recipient_id, client_id=None)
            for m in msgs
        ]


def mark_system_read(recipient_id: int) -> int:
    """Помечает прочитанными непрочитанные system-сообщения получателя."""
    conv = get_system_conversation(recipient_id)
    if conv is None:
        return 0

    with SessionLocal() as db:
        updated = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.conversation_id == conv.id,
                ChatMessage.message_kind == "system",
                ChatMessage.read_at.is_(None),
                ChatMessage.deleted_at.is_(None),
            )
            .update(
                {"read_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )
        db.commit()
        return updated


def system_unread_count(recipient_id: int) -> int:
    """Непрочитанные system-сообщения получателя."""
    conv = get_system_conversation(recipient_id)
    if conv is None:
        return 0
    with SessionLocal() as db:
        return (
            db.query(func.count(ChatMessage.id))
            .filter(
                ChatMessage.conversation_id == conv.id,
                ChatMessage.message_kind == "system",
                ChatMessage.read_at.is_(None),
                ChatMessage.deleted_at.is_(None),
            )
            .scalar()
        ) or 0

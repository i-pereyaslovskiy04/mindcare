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

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.encryption import decrypt_text, encrypt_text
from app.db.session import SessionLocal
from app.db.models import (
    ChatAttachment, ChatConversation, ChatMessage, TherapyEngagement, User, UserSession,
)


# ─── Presence (Stage 30c) ───────────────────────────────────────────────────
#
# MVP online/offline без real-time: пользователь считается online, если у него
# есть активная (не revoked, не expired) сессия с last_active не старше порога.
# Порог 10 минут намеренно мягче, чем debounce touch_session (300с): при
# 5-минутном пороге активный пользователь выглядел бы offline в окне между
# двумя debounce-обновлениями last_active. Статус приблизительный — не realtime.

ONLINE_THRESHOLD_SECONDS = 600


def get_online_user_ids(user_ids: list[int]) -> set[int]:
    """Подмножество user_ids со свежей активной сессией. Один запрос — без N+1."""
    ids = [i for i in user_ids if i is not None]
    if not ids:
        return set()
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS)
    with SessionLocal() as db:
        rows = (
            db.query(UserSession.user_id)
            .filter(
                UserSession.user_id.in_(ids),
                ~UserSession.is_revoked,
                UserSession.expires_at > now,
                UserSession.last_active.isnot(None),
                UserSession.last_active >= threshold,
            )
            .distinct()
            .all()
        )
    return {row[0] for row in rows}


def is_user_online(user_id: int) -> bool:
    return user_id in get_online_user_ids([user_id])


# ─── Mappers ──────────────────────────────────────────────────────────────────

def _attachment_to_dict(att: ChatAttachment) -> dict:
    """Сериализация вложения. storage_key и checksum наружу не отдаются."""
    return {
        "uuid":              str(att.uuid),
        "original_filename": att.original_filename,
        "mime_type":         att.mime_type,
        "file_size":         att.file_size,
        "is_image":          att.is_image,
        "created_at":        att.created_at,
    }


def _message_to_dict(
    msg: ChatMessage,
    *,
    current_user_id: int,
    client_id: Optional[int],
) -> dict:
    """Response dict. Вызывать только после проверки прав.

    system-сообщение (message_kind='system', sender_id IS NULL) не обращается
    к engagement.client_id: sender_role='system', is_mine=False.

    Удалённое сообщение (deleted_at IS NOT NULL): content НЕ расшифровывается
    и наружу не отдаётся (плейсхолдер на стороне UI); возвращается is_deleted=True.
    """
    if msg.message_kind == "system":
        sender_role = "system"
        is_mine = False
    else:
        sender_role = "student" if msg.sender_id == client_id else "psychologist"
        is_mine = msg.sender_id == current_user_id

    # Вложения: исключаем soft-deleted; relationship уже загружен (selectinload).
    atts = [
        _attachment_to_dict(a)
        for a in (msg.attachments or [])
        if a.deleted_at is None
    ]

    if msg.deleted_at is not None:
        return {
            "id":          msg.id,
            "uuid":        str(msg.uuid),
            "sender_id":   msg.sender_id,
            "sender_role": sender_role,
            "is_mine":     is_mine,
            "content":     "",          # исходный текст удалённого не отдаём
            "created_at":  msg.created_at,
            "read_at":     msg.read_at,
            "edited_at":   None,
            "is_deleted":  True,
            "attachments": atts,
        }

    try:
        plaintext = decrypt_text(msg.content)
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Message decryption failed (id={msg.id})") from exc

    return {
        "id":          msg.id,
        "uuid":        str(msg.uuid),
        "sender_id":   msg.sender_id,
        "sender_role": sender_role,
        "is_mine":     is_mine,
        "content":     plaintext,
        "created_at":  msg.created_at,
        "read_at":     msg.read_at,
        "edited_at":   msg.edited_at,
        "is_deleted":  False,
        "attachments": atts,
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


def ensure_engagement_conversation(
    db, engagement_id: int,
) -> tuple[ChatConversation, bool]:
    """
    Session-aware get-or-create engagement-беседы (Stage 31o).

    В отличие от get_or_create_conversation, работает ВНУТРИ уже открытой
    транзакции caller'а: НЕ открывает свою Session и НЕ делает commit, только
    flush. Создание беседы откатывается вместе с транзакцией caller'а
    (например, assign/transfer психолога), поэтому engagement не может
    остаться без беседы.

    Идемпотентна; уважает UNIQUE(engagement_id). Возвращает (conversation,
    created). Статус engagement здесь не проверяется — это ответственность
    caller'а (assign/transfer передают свежую active-связь; repair-скрипт
    фильтрует active).
    """
    existing = (
        db.query(ChatConversation)
        .filter(ChatConversation.engagement_id == engagement_id)
        .first()
    )
    if existing is not None:
        return existing, False

    conv = ChatConversation(engagement_id=engagement_id)
    db.add(conv)
    db.flush()   # назначает conv.id/conv.uuid; без commit
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


def conversation_has_messages(conversation_id: int) -> bool:
    """True, если у беседы есть хотя бы одно не удалённое сообщение (Stage 31p)."""
    with SessionLocal() as db:
        return (
            db.query(ChatMessage.id)
            .filter(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.deleted_at.is_(None),
            )
            .first()
            is not None
        )


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
    Preview последнего сообщения намеренно не возвращается (N decrypt).

    Видимость (Stage 31p): active-беседа показывается всегда (даже пустая);
    inactive/transferred/closed — только если есть хотя бы одно не удалённое
    сообщение. Пустые неактивные беседы (артефакты ошибочного назначения)
    скрываются на уровне query, физически не удаляются."""
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

        # active ИЛИ есть хотя бы одно не удалённое сообщение.
        has_message = (
            select(ChatMessage.id)
            .where(
                ChatMessage.conversation_id == ChatConversation.id,
                ChatMessage.deleted_at.is_(None),
            )
            .correlate(ChatConversation)
            .exists()
        )
        visible = (TherapyEngagement.status == "active") | has_message

        base = (
            db.query(ChatConversation, TherapyEngagement, User, unread_subq)
            .join(
                TherapyEngagement,
                TherapyEngagement.id == ChatConversation.engagement_id,
            )
            .join(User, User.id == TherapyEngagement.client_id)
            .filter(TherapyEngagement.psychologist_id == psychologist_id)
            .filter(visible)
        )

        total = (
            db.query(func.count(ChatConversation.id))
            .join(
                TherapyEngagement,
                TherapyEngagement.id == ChatConversation.engagement_id,
            )
            .filter(TherapyEngagement.psychologist_id == psychologist_id)
            .filter(visible)
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
        # Презенс клиентов одним запросом по странице (не N+1).
        online = get_online_user_ids([it["student"]["id"] for it in items])
        for it in items:
            it["peer_is_online"] = it["student"]["id"] in online
        return items, total


def list_conversations_for_student(
    student_id: int,
    *,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """Список бесед студента: психолог (partner), статус engagement, unread_count
    (Stage 31t). Та же visibility policy, что у психолога (Stage 31p/31s):
    active — всегда; inactive — только если есть не удалённые сообщения."""
    with SessionLocal() as db:
        unread_subq = (
            select(func.count(ChatMessage.id))
            .where(
                ChatMessage.conversation_id == ChatConversation.id,
                ChatMessage.sender_id != student_id,
                ChatMessage.read_at.is_(None),
                ChatMessage.deleted_at.is_(None),
            )
            .correlate(ChatConversation)
            .scalar_subquery()
        )

        has_message = (
            select(ChatMessage.id)
            .where(
                ChatMessage.conversation_id == ChatConversation.id,
                ChatMessage.deleted_at.is_(None),
            )
            .correlate(ChatConversation)
            .exists()
        )
        visible = (TherapyEngagement.status == "active") | has_message

        base = (
            db.query(ChatConversation, TherapyEngagement, User, unread_subq)
            .join(
                TherapyEngagement,
                TherapyEngagement.id == ChatConversation.engagement_id,
            )
            .join(User, User.id == TherapyEngagement.psychologist_id)
            .filter(TherapyEngagement.client_id == student_id)
            .filter(visible)
        )

        total = (
            db.query(func.count(ChatConversation.id))
            .join(
                TherapyEngagement,
                TherapyEngagement.id == ChatConversation.engagement_id,
            )
            .filter(TherapyEngagement.client_id == student_id)
            .filter(visible)
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
        for conv, eng, psych, unread in rows:
            items.append({
                "uuid":              str(conv.uuid),
                "partner":           {"id": psych.id, "full_name": psych.full_name},
                "engagement_status": eng.status,
                "last_message_at":   conv.last_message_at,
                "unread_count":      int(unread or 0),
            })
        online = get_online_user_ids([it["partner"]["id"] for it in items])
        for it in items:
            it["peer_is_online"] = it["partner"]["id"] in online
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

    Удалённые сообщения (deleted_at IS NOT NULL) НЕ возвращаются (Stage 31y-hotfix):
    в пользовательской ленте они скрыты полностью, без плейсхолдера «Сообщение
    удалено» (в психологическом чате такой маркер тревожит). Soft delete и audit
    остаются в БД; скрытие — только на уровне выдачи. Порядок оставшихся сообщений
    и last_message_at не меняются.
    """
    with SessionLocal() as db:
        q = (
            db.query(ChatMessage)
            .options(selectinload(ChatMessage.attachments))
            .filter(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.deleted_at.is_(None),
            )
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
    attachment_uuids: Optional[list] = None,
) -> dict:
    """
    Encrypt-on-write + обновление last_message_at в одной транзакции.

    Stage 32c: attachment_uuids — список UUID уже загруженных вложений.
    Привязка attachment.message_id = msg.id в той же транзакции.
    ValueError если вложения недоступны (чужие/не orphan/другой conversation).
    """
    now = datetime.now(timezone.utc)
    uuid_strs = [str(u) for u in (attachment_uuids or [])]

    with SessionLocal() as db:
        msg = ChatMessage(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=encrypt_text(content),
        )
        db.add(msg)
        db.flush()   # получаем msg.id до commit

        # Привязать вложения в той же транзакции.
        atts: list[ChatAttachment] = []
        if uuid_strs:
            atts = _link_attachments_to_message(
                db,
                attachment_uuids=uuid_strs,
                message_id=msg.id,
                uploader_id=sender_id,
                conversation_id=conversation_id,
            )

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
            "edited_at":   msg.edited_at,
            "attachments": [_attachment_to_dict(a) for a in atts],
        }


# ─── Attachments (Stage 32c) ──────────────────────────────────────────────────

def _link_attachments_to_message(
    db,
    *,
    attachment_uuids: list[str],
    message_id: int,
    uploader_id: int,
    conversation_id: int,
) -> list[ChatAttachment]:
    """
    Привязывает orphan-вложения к сообщению внутри открытой транзакции.

    Проверяет: вложения существуют, принадлежат этой беседе, загружены текущим
    пользователем, не привязаны к другому сообщению, не удалены.
    Проверяет лимит CHAT_FILE_MAX_FILES_PER_MESSAGE.

    Выбрасывает ValueError при любом нарушении — транзакция caller'а откатится.
    """
    if not attachment_uuids:
        return []

    max_count = settings.CHAT_FILE_MAX_FILES_PER_MESSAGE
    if len(attachment_uuids) > max_count:
        raise ValueError(
            f"Слишком много вложений. Максимум {max_count} файлов в одном сообщении"
        )

    atts = (
        db.query(ChatAttachment)
        .filter(
            ChatAttachment.uuid.in_(attachment_uuids),
            ChatAttachment.conversation_id == conversation_id,
            ChatAttachment.uploader_id == uploader_id,
            ChatAttachment.message_id.is_(None),
            ChatAttachment.deleted_at.is_(None),
        )
        .all()
    )

    if len(atts) != len(attachment_uuids):
        raise ValueError(
            "Некоторые вложения недоступны, уже использованы или принадлежат другому пользователю"
        )

    for att in atts:
        att.message_id = message_id

    return atts


def create_attachment_record(
    *,
    conversation_id:   int,
    uploader_id:       int,
    original_filename: str,
    storage_key:       str,
    mime_type:         str,
    file_size:         int,
    checksum_sha256:   str,
    is_image:          bool,
) -> dict:
    """
    Создаёт строку chat_attachments (message_id=NULL — pre-upload).
    Запись идёт ПОСЛЕ успешной записи файла на диск (caller убеждается).
    Возвращает dict с uuid и метаданными для ответа API.
    """
    att = ChatAttachment(
        conversation_id=conversation_id,
        message_id=None,
        uploader_id=uploader_id,
        original_filename=original_filename,
        storage_key=storage_key,
        mime_type=mime_type,
        file_size=file_size,
        checksum_sha256=checksum_sha256,
        is_image=is_image,
    )
    with SessionLocal() as db:
        db.add(att)
        db.commit()
        db.refresh(att)
        return _attachment_to_dict(att)


def save_attachment(
    *,
    conversation_id:   int,
    uploader_id:       int,
    original_filename: str,
    storage_key:       str,
    mime_type:         str,
    file_size:         int,
    is_image:          bool,
    data:              bytes,
) -> dict:
    """
    Атомарное сохранение: сначала запись файла на диск, затем DB-строка.

    Порядок операций:
      1. Resolve path + write bytes → получаем checksum.
      2. Открываем транзакцию.
      3. flush attachment row (получаем uuid).
      4. db.commit().

    Если запись на диск упала — DB-строка не создаётся.
    Если DB commit упал — файл остаётся orphan на диске (очищает cleanup-скрипт).
    """
    from app.chat import attachment_storage as fs

    checksum = fs.save_file(data, storage_key)

    att = ChatAttachment(
        conversation_id=conversation_id,
        message_id=None,
        uploader_id=uploader_id,
        original_filename=original_filename,
        storage_key=storage_key,
        mime_type=mime_type,
        file_size=file_size,
        checksum_sha256=checksum,
        is_image=is_image,
    )
    with SessionLocal() as db:
        db.add(att)
        db.commit()
        db.refresh(att)
        return _attachment_to_dict(att)


def get_attachment_for_download(
    attachment_uuid: str,
    conversation_id: int,
) -> Optional[ChatAttachment]:
    """
    Возвращает ChatAttachment если он принадлежит беседе и не удалён.
    Проверка участника беседы — на уровне service (через resolve_conversation).
    """
    with SessionLocal() as db:
        att = (
            db.query(ChatAttachment)
            .filter(
                ChatAttachment.uuid == attachment_uuid,
                ChatAttachment.conversation_id == conversation_id,
                ChatAttachment.deleted_at.is_(None),
            )
            .first()
        )
        if att is not None:
            db.expunge(att)
        return att


def get_orphan_attachments(cutoff: datetime) -> list[ChatAttachment]:
    """
    Возвращает orphan-вложения (message_id IS NULL, created_at < cutoff,
    deleted_at IS NULL) для cleanup-скрипта.
    """
    with SessionLocal() as db:
        rows = (
            db.query(ChatAttachment)
            .filter(
                ChatAttachment.message_id.is_(None),
                ChatAttachment.created_at < cutoff,
                ChatAttachment.deleted_at.is_(None),
            )
            .order_by(ChatAttachment.created_at)
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def soft_delete_attachment(attachment_id: int, now: Optional[datetime] = None) -> None:
    """Soft-delete одной attachment-записи по id (для cleanup-скрипта)."""
    ts = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.query(ChatAttachment).filter(
            ChatAttachment.id == attachment_id
        ).update({"deleted_at": ts}, synchronize_session=False)
        db.commit()


def update_message_content(
    *,
    conversation_id: int,
    message_uuid: str,
    actor_user_id: int,
    client_id: int,
    new_content: str,
    remove_attachment_uuids: Optional[list] = None,
    now: Optional[datetime] = None,
) -> dict:
    """
    Редактирование своего user-сообщения (Stage 31x/32g).

    Permission/kind-проверки делаются здесь (нужна строка) и возвращаются
    как status-discriminator — service маппит его в HTTP. Возможные результаты:
      {"status": "ok", "message": <read dict с plaintext + edited_at + attachments>}
      {"status": "not_found"}            — сообщения нет в этой беседе
      {"status": "forbidden_system"}     — message_kind != 'user' (system нельзя)
      {"status": "not_owner"}            — чужое сообщение
      {"status": "deleted"}              — удалённое (deleted_at не NULL)
      {"status": "attachment_not_found"} — UUID не принадлежит этому сообщению (Stage 32g)
      {"status": "would_be_empty"}       — trim(content)=='' и все вложения будут удалены (Stage 32g)

    Stage 32g: remove_attachment_uuids — soft-delete вложений в той же транзакции.
    content перезаписывается encrypt_text(new) без old decrypt и без логирования.
    История версий не ведётся (only edited_at). Time-limit отсутствует.
    """
    now = now or datetime.now(timezone.utc)
    remove_uuids_set = {str(u) for u in (remove_attachment_uuids or [])}

    with SessionLocal() as db:
        msg = (
            db.query(ChatMessage)
            .options(selectinload(ChatMessage.attachments))
            .filter(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.uuid == message_uuid,
            )
            .first()
        )
        if msg is None:
            return {"status": "not_found"}
        if msg.message_kind != "user":
            return {"status": "forbidden_system"}
        if msg.sender_id != actor_user_id:
            return {"status": "not_owner"}
        if msg.deleted_at is not None:
            return {"status": "deleted"}

        # Stage 32g: обработка soft-delete вложений.
        active_atts = [a for a in (msg.attachments or []) if a.deleted_at is None]
        atts_to_remove = []
        if remove_uuids_set:
            atts_to_remove = [a for a in active_atts if str(a.uuid) in remove_uuids_set]
            # Все запрошенные UUID должны принадлежать этому сообщению и быть активны.
            if len(atts_to_remove) != len(remove_uuids_set):
                return {"status": "attachment_not_found"}

        remaining_uuids = {str(a.uuid) for a in active_atts} - remove_uuids_set
        trimmed = new_content.strip()
        if not trimmed and not remaining_uuids:
            return {"status": "would_be_empty"}

        # Soft-delete вложений атомарно с content+edited_at.
        for att in atts_to_remove:
            att.deleted_at = now

        msg.content = encrypt_text(trimmed)   # перезапись ciphertext, без old decrypt
        msg.edited_at = now
        db.commit()
        db.refresh(msg)

        # Активные вложения после commit (ORM-коллекция обновлена soft-delete выше).
        final_atts = [
            _attachment_to_dict(a)
            for a in (msg.attachments or [])
            if a.deleted_at is None
        ]

        return {
            "status": "ok",
            "message": {
                "id":          msg.id,
                "uuid":        str(msg.uuid),
                "sender_id":   msg.sender_id,
                "sender_role": "student" if msg.sender_id == client_id else "psychologist",
                "is_mine":     True,
                "content":     trimmed,       # plaintext отправителю, без повторного decrypt
                "created_at":  msg.created_at,
                "read_at":     msg.read_at,
                "edited_at":   msg.edited_at,
                "is_deleted":  False,
                "attachments": final_atts,
            },
        }


def soft_delete_message(
    *,
    conversation_id: int,
    message_uuid: str,
    actor_user_id: int,
    client_id: int,
    now: Optional[datetime] = None,
) -> dict:
    """
    Soft delete своего user-сообщения (Stage 31y).

    Permission/kind-проверки здесь (нужна строка), результат — status-discriminator,
    который service маппит в HTTP:
      {"status": "ok", "message": <deleted placeholder dict>}
      {"status": "not_found"}         — сообщения нет в этой беседе
      {"status": "forbidden_system"}  — message_kind != 'user' (system нельзя)
      {"status": "not_owner"}         — чужое сообщение

    Идемпотентность: повторное удаление уже удалённого своего сообщения —
    тоже "ok" (тот же плейсхолдер), без ошибки.

    Физического DELETE нет: проставляется deleted_at. content (ciphertext)
    НЕ перезаписывается plaintext'ом и наружу не отдаётся (_message_to_dict).
    last_message_at и read_at не трогаются: удаление не создаёт unread-событий
    и не меняет порядок ленты.
    """
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        msg = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.uuid == message_uuid,
            )
            .first()
        )
        if msg is None:
            return {"status": "not_found"}
        if msg.message_kind != "user":
            return {"status": "forbidden_system"}
        if msg.sender_id != actor_user_id:
            return {"status": "not_owner"}

        if msg.deleted_at is None:
            msg.deleted_at = now
            db.commit()
            db.refresh(msg)

        return {
            "status": "ok",
            "message": {
                "id":          msg.id,
                "uuid":        str(msg.uuid),
                "sender_id":   msg.sender_id,
                "sender_role": "student" if msg.sender_id == client_id else "psychologist",
                "is_mine":     True,
                "content":     "",          # исходный текст удалённого не отдаём
                "created_at":  msg.created_at,
                "read_at":     msg.read_at,
                "edited_at":   None,
                "is_deleted":  True,
            },
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
        q = (
            db.query(ChatMessage)
            .options(selectinload(ChatMessage.attachments))
            .filter(
                ChatMessage.conversation_id == conv.id,
                ChatMessage.deleted_at.is_(None),
            )
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

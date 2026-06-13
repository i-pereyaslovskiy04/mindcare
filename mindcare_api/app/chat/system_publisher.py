"""
System message publisher (Stage 29b).

Единственная точка создания системных сообщений: внутренний service-layer
helper. Пользователь не может публиковать system-сообщения (write-эндпоинта нет).

Гарантии:
  - lazy-create system-беседы получателя;
  - encrypt-on-write (storage.create_system_message → encrypt_text);
  - идемпотентность по event_key (повторный вызов с тем же ключом не плодит дубль);
  - soft-fail: ошибка публикации НЕ роняет основную операцию (регистрация,
    создание пользователя, смена пароля) и не раскрывает plaintext;
  - text сообщения НЕ логируется (ни при успехе, ни при ошибке).

text должен быть plain text без HTML.
"""

import sys
from typing import Optional

from app.chat import storage
from app.chat.audit import log_system_conversation_created


def publish_system_message(
    recipient_id: int,
    event_key: str,
    text: str,
) -> Optional[dict]:
    """
    Публикует system-сообщение получателю. Возвращает результат storage
    ({"created": bool, "conversation_id": int}) или None при сбое.

    Никогда не бросает наружу: вызывающий код (auth/users) не должен падать
    из-за проблемы с уведомлением.
    """
    try:
        existed = storage.get_system_conversation(recipient_id) is not None
        result = storage.create_system_message(
            recipient_id, event_key=event_key, text=text,
        )
        if not existed:
            conv = storage.get_system_conversation(recipient_id)
            if conv is not None:
                log_system_conversation_created(
                    recipient_id=recipient_id,
                    conversation_id=conv.id,
                    conversation_uuid=str(conv.uuid),
                )
        return result
    except Exception as exc:
        # Без text и без ciphertext — только тип ошибки и event_key (не ПДн).
        print(
            f"[SYSTEM MSG FAIL] event_key={event_key} "
            f"recipient_id={recipient_id}: {type(exc).__name__}",
            file=sys.stderr,
        )
        return None

"""
System message publisher (Stage 29b; audit перенесён на record_event в Stage 4B-3).

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

from app.audit import Actor, AuditError, Outcome, Target, record_event
from app.chat import storage


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

    Audit (Stage 4B-3): conversation_created — race-safe флаг, вычисленный
    атомарно внутри storage.create_system_message() (через get_or_create_
    system_conversation, partial UNIQUE + IntegrityError-catch для проигравшей
    параллельной транзакции). Нет preflight/postflight get_system_conversation:
    единственный источник сигнала "беседа создана впервые" — этот флаг, чтобы
    два параллельных вызова для одного recipient_id не написали дублирующий
    system_conversation_created.
    """
    try:
        result, conversation_created = storage.create_system_message(
            recipient_id, event_key=event_key, text=text,
        )
    except Exception as exc:
        # Только фаза и класс исключения — без recipient_id/event_key (оба
        # содержат пользовательские/доменные идентификаторы, напр.
        # "welcome:user:{id}") и без текста исходного исключения.
        print(f"[SYSTEM MSG] phase=publish error={type(exc).__name__}", file=sys.stderr)
        return None

    if conversation_created:
        try:
            record_event(
                event="system_conversation_created",
                actor=Actor.system(),
                target=Target("chat_conversation", result["conversation_id"]),
                outcome=Outcome.SUCCESS,
                context=None,
                db=None,
            )
        except AuditError as exc:
            # Узкий catch: защищает уже успешную публикацию от contract-ошибки
            # audit-вызова (INDEPENDENT/SOFT storage-сбой не бросает — уже
            # возвращается как AuditResult(SOFT_FAILED), сюда не долетает).
            # Только event и класс исключения — без recipient_id/event_key/
            # conversation_id/UUID/текста исходного исключения/ПДн.
            print(
                f"[CHAT SYSTEM AUDIT] event=system_conversation_created "
                f"error={type(exc).__name__}",
                file=sys.stderr,
            )

    return result

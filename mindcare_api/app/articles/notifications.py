"""
Уведомления автора о решении по статье (ADR-034, Дополнение 2026-10-28).

Post-commit, soft-fail: решение проверяющего уже зафиксировано своим
audit-событием; сбой доставки system-сообщения его не откатывает и наружу не
выходит (publish_system_message не бросает). Текст — только название и итог:
комментарий проверяющего хранится зашифрованным в статье и виден автору в
«Мои материалы», в сообщение он не копируется.
"""
from typing import Optional

from app.chat.system_publisher import publish_system_message

MY_MATERIALS_LINK = "/psychologist/materials#my-materials"


def published_text(title: str) -> str:
    return f"Материал «{title}» опубликован и доступен в библиотеке. {MY_MATERIALS_LINK}"


def returned_text(title: str) -> str:
    return (
        f"Материал «{title}» возвращён на доработку. "
        f"Комментарий проверяющего — в разделе {MY_MATERIALS_LINK}"
    )


def event_key(kind: str, notify: dict) -> str:
    """Один ключ на переход: повтор того же решения не дублирует сообщение."""
    return f"article_{kind}:article:{notify['article_uuid']}:{notify['occurrence']}"


def notify_author(kind: str, notify: Optional[dict]) -> None:
    """kind ∈ {"published", "returned"}; notify=None — уведомлять некого."""
    if not notify:
        return
    text = published_text(notify["title"]) if kind == "published" else returned_text(notify["title"])
    publish_system_message(
        recipient_id=notify["author_id"],
        event_key=event_key(kind, notify),
        text=text,
    )

"""
Уведомления автора о решении модерации по его тесту (ADR-016, Дополнение
2026-10-28 к ADR-034).

Только решение по тесту, отправленному на проверку (in_review → published /
needs_changes): прямая публикация staff'ом своего или чужого черновика автора
не уведомляет. Своё решение (автор = проверяющий) — без уведомления.

Post-commit, soft-fail (publish_system_message не бросает). Причина возврата
нигде больше не хранится (tests без поля комментария), поэтому передаётся
автору только внутри system-сообщения — оно шифруется (encrypt-on-write), в
audit metadata и логи не попадает.
"""
from typing import Optional

from app.chat.system_publisher import publish_system_message

MY_TESTS_LINK = "/psychologist/tests"
REASON_MAX = 1000


def published_text(title: str) -> str:
    return f"Тест «{title}» опубликован. {MY_TESTS_LINK}"


def returned_text(title: str, reason: Optional[str]) -> str:
    text = f"Тест «{title}» возвращён на доработку."
    reason = (reason or "").strip()
    if reason:
        if len(reason) > REASON_MAX:
            reason = reason[:REASON_MAX].rstrip() + "…"
        text += f" Комментарий проверяющего: {reason}"
    return f"{text} {MY_TESTS_LINK}"


def notify_author(
    kind: str, *, author_id: Optional[int], actor_id: int, test: dict,
    reason: Optional[str] = None,
) -> None:
    """kind ∈ {"published", "returned"}."""
    if author_id is None or int(author_id) == int(actor_id):
        return
    updated = test.get("updated_at")
    occurrence = updated.strftime("%Y%m%d%H%M%S%f") if hasattr(updated, "strftime") else str(updated)
    title = test.get("title") or "без названия"
    text = published_text(title) if kind == "published" else returned_text(title, reason)
    publish_system_message(
        recipient_id=int(author_id),
        event_key=f"test_{kind}:test:{test['uuid']}:{occurrence}",
        text=text,
    )

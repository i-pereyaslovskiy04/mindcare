"""
Тексты приветственных system-сообщений (System Conversation Naming Cleanup).

Системная беседа подписана «Психология ДонГУ» (frontend); в тексты новых
приветствий внутреннее имя проекта «MindCare» больше не попадает. Все места
создания берут текст из констант app.chat.system_publisher.
"""
from pathlib import Path

from app.chat.system_publisher import ACCOUNT_CREATED_TEXT, WELCOME_SELF_REGISTERED_TEXT

APP = Path(__file__).resolve().parents[1] / "app"


def test_welcome_texts():
    assert WELCOME_SELF_REGISTERED_TEXT == "Добро пожаловать в Психологию ДонГУ."
    assert ACCOUNT_CREATED_TEXT == "Ваша учётная запись создана."


def test_creation_sites_use_constants_without_mindcare():
    sites = {
        "auth/service.py": "WELCOME_SELF_REGISTERED_TEXT",
        "users/service.py": "ACCOUNT_CREATED_TEXT",
        "supervisor/service.py": "ACCOUNT_CREATED_TEXT",
    }
    for rel, const in sites.items():
        src = (APP / rel).read_text(encoding="utf-8")
        assert f"text={const}" in src, rel
        assert "Добро пожаловать в MindCare." not in src, rel
        assert "учётная запись MindCare создана" not in src, rel

"""
Каталог контактов — единственный источник типов, сервисов и лимитов (ADR-031).

Фронтенд получает его в ответах API и не хранит копию. Каталог только
РАСШИРЯЕТСЯ: удаление сервиса сделало бы невозможным повторное сохранение
ранее сохранённого элемента (invalid_service). Прежние сервисы старой формы
настроек (Telegram, Instagram, LinkedIn, VK, Facebook, X (Twitter), «Сайт»)
сохранены целиком.
"""
MAX_ITEMS = 10          # дополнительных контактов на пользователя
HARD_ITEMS_CAP = 50     # потолок разбора тела запроса (защита от перегрузки)
LABEL_MAX = 80
VALUE_MAX = 500

# (код, подпись, вид сервиса или None)
TYPES = (
    ("phone", "Телефон", None),
    ("email", "Email", None),
    ("messenger", "Мессенджер", "messenger"),
    ("social", "Социальная сеть", "social"),
    ("website", "Сайт", None),
    ("other", "Другое", None),
)

SERVICES = {
    "messenger": (
        ("telegram", "Telegram"),
        ("whatsapp", "WhatsApp"),
        ("viber", "Viber"),
        ("max", "MAX"),
        ("signal", "Signal"),
        ("skype", "Skype"),
        ("other", "Другой мессенджер"),
    ),
    "social": (
        ("vk", "VK"),
        ("ok", "Одноклассники"),
        ("instagram", "Instagram"),
        ("facebook", "Facebook"),
        ("linkedin", "LinkedIn"),
        ("x", "X (Twitter)"),
        ("youtube", "YouTube"),
        ("rutube", "RUTUBE"),
        ("other", "Другая соцсеть"),
    ),
}

TYPE_CODES = frozenset(code for code, _, _ in TYPES)
SERVICE_KIND = {code: kind for code, _, kind in TYPES if kind}
SERVICE_CODES = {
    kind: frozenset(code for code, _ in items) for kind, items in SERVICES.items()
}
OTHER_SERVICE = "other"


def limits_dto() -> dict:
    return {"max_items": MAX_ITEMS, "label_max": LABEL_MAX, "value_max": VALUE_MAX}


def catalog_dto() -> dict:
    return {
        "types": [
            {"code": code, "label": label, "service_kind": kind}
            for code, label, kind in TYPES
        ],
        "services": {
            kind: [{"code": code, "label": label} for code, label in items]
            for kind, items in SERVICES.items()
        },
    }

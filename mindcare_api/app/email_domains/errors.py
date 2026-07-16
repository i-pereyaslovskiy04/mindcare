"""
Исключения модуля email_domains.

Размещены в отдельном низкоуровневом модуле, чтобы `email_domains.storage` и
внешние storages (auth/users/supervisor) могли импортировать их без циклов и
без обратной зависимости на `email_domains.service`. Направление слоёв
`service → storage` не нарушается: storage поднимает эти ошибки, service их
транслирует в HTTP-специфику.
"""


class EmailDomainNotAllowedError(Exception):
    """
    Домен email не входит в активный allowlist при создании нового аккаунта.

    НЕ подкласс ValueError — чтобы существующие `except ValueError` в
    creation-путях (users.service.create_user → 409 и т.п.) его НЕ
    перехватывали. Обрабатывается только явными except и мапится в HTTP 422.
    """


class DomainError(Exception):
    """
    Типизированная ошибка admin CRUD над allowlist с явным HTTP-статусом.

    409 — duplicate / попытка отключить последний активный домен;
    422 — невалидный домен / пустое тело PATCH;
    404 — домен не найден.
    """

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

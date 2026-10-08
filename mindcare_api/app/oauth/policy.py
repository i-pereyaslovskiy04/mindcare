"""
Политика регистрации через провайдера (Stage Social Auth 4 / VK-1B).

Модуль-лист: не импортирует service/storage/routes. Ядро OAuth остаётся
провайдер-нейтральным — отличия провайдеров сведены к двум признакам.

  email_choice       — email выбирает/подтверждает пользователь на шаге email:
                       адрес провайдера — только предложение, его можно заменить
                       до успешного confirm; занятый email не сжигает ticket.
                       False — email задан провайдером и фиксирован: клиент его
                       не передаёт, код уходит на него автоматически.
  enforce_allowlist  — применять allowlist доменов (тот же, что у регистрации
                       по email и паролю) на init и повторно внутри транзакции
                       confirm.

Яндекс: email провайдера фиксирован, allowlist не применяется (ADR-027 п. 5).
VK:     email выбирает пользователь, allowlist обязателен (ADR-030).
Асимметрия allowlist между провайдерами — осознанное продуктовое решение, а не
инвариант безопасности системы: меняется только отдельным решением.

Провайдера нет в таблице → регистрации через него нет (только вход по уже
привязанной identity).
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RegistrationPolicy:
    email_choice: bool
    enforce_allowlist: bool


REGISTRATION_POLICIES: dict[str, RegistrationPolicy] = {
    "yandex": RegistrationPolicy(email_choice=False, enforce_allowlist=False),
    "vk": RegistrationPolicy(email_choice=True, enforce_allowlist=True),
}


def registration_policy(provider: str) -> Optional[RegistrationPolicy]:
    """Политика провайдера или None (регистрации через него нет)."""
    return REGISTRATION_POLICIES.get(provider)

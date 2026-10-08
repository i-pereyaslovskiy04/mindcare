"""
Integration: GET /api/public/email-domains — публичная подсказка формы
регистрации по email. Запускается только через Stage 1 isolated runner.

Инварианты:
  - без авторизации (в т.ч. с протухшим токеном — иначе клиент решил бы, что
    сессия истекла); только имена АКТИВНЫХ доменов по возрастанию;
  - ответ — ровно {"domains": [...]}: без id, comment, дат и отключённых строк;
  - Cache-Control: no-store; чтение не пишет ни audit_log, ни auth_log;
  - подсказка соответствует политике: перечисленный домен регистрация принимает,
    неперечисленный — отклоняет.
"""

import re
import uuid as _uuid

from app.db.models import AllowedEmailDomain, AuditLog, AuthLog
from app.db.session import SessionLocal

URL = "/api/public/email-domains"
PASSWORD = "SecurePass42!"
_SECRET_COMMENT = "внутренний-комментарий-администратора"


def _domain(tag: str) -> str:
    # Префикс `integ-` обязателен: по нему reset_email_domains удаляет test-строки.
    return f"integ-{tag}-{_uuid.uuid4().hex[:8]}.ru"


def _set_active(*active: str, inactive: tuple[str, ...] = (), comment=None) -> None:
    """Активными остаются РОВНО `active` (новые строки); остальные отключаются.
    Прежнее состояние возвращает фикстура reset_email_domains."""
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).update(
            {"is_active": False}, synchronize_session=False,
        )
        for name in active:
            db.add(AllowedEmailDomain(domain=name, is_active=True, comment=comment))
        for name in inactive:
            db.add(AllowedEmailDomain(domain=name, is_active=False, comment=comment))
        db.commit()


def _set_domain_active(domain: str, active: bool) -> None:
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).filter(
            AllowedEmailDomain.domain == domain,
        ).update({"is_active": active}, synchronize_session=False)
        db.commit()


def _journal_counts() -> tuple[int, int]:
    with SessionLocal() as db:
        return db.query(AuditLog).count(), db.query(AuthLog).count()


# ── состав и форма ответа ────────────────────────────────────────────────────

def test_only_active_names_sorted_without_service_fields(client, reset_email_domains):
    a, b, off = _domain("a"), _domain("b"), _domain("off")
    _set_active(b, a, inactive=(off,), comment=_SECRET_COMMENT)

    r = client.get(URL)                                     # без Authorization

    assert r.status_code == 200, r.text
    assert r.json() == {"domains": [a, b]}                  # по возрастанию, только активные
    assert set(r.json()) == {"domains"}                     # никаких id/comment/дат
    assert off not in r.text
    assert _SECRET_COMMENT not in r.text
    assert all(isinstance(name, str) for name in r.json()["domains"])


def test_single_active_domain(client, reset_email_domains):
    only = _domain("a")
    _set_active(only)
    assert client.get(URL).json() == {"domains": [only]}


def test_no_active_domains_gives_empty_list(client, reset_email_domains):
    _set_active()
    r = client.get(URL)
    assert r.status_code == 200
    assert r.json() == {"domains": []}


def test_seeded_domains_are_normalized_names(client, reset_email_domains):
    names = client.get(URL).json()["domains"]
    assert names == sorted(names)
    assert names, "в seed allowlist есть активные домены"
    assert all(re.fullmatch(r"[a-z0-9.-]+", n) for n in names)


# ── авторизация, кэш, аудит ──────────────────────────────────────────────────

def test_public_even_with_a_stale_token(client, reset_email_domains):
    # Протухший токен не должен давать 401: на 401 клиент считает сессию истекшей.
    r = client.get(URL, headers={"Authorization": "Bearer not-a-real-session"})
    assert r.status_code == 200


def test_response_is_not_cacheable(client, reset_email_domains):
    assert client.get(URL).headers["Cache-Control"] == "no-store"


def test_read_writes_no_audit_rows(client, reset_email_domains):
    before = _journal_counts()
    for _ in range(3):
        assert client.get(URL).status_code == 200
    assert _journal_counts() == before


# ── актуальность и связь с политикой ─────────────────────────────────────────

def test_reflects_disable_and_reactivation(client, reset_email_domains):
    a, b = _domain("a"), _domain("b")
    _set_active(a, b)
    assert client.get(URL).json() == {"domains": [a, b]}

    _set_domain_active(a, False)
    assert client.get(URL).json() == {"domains": [b]}

    _set_domain_active(a, True)
    assert client.get(URL).json() == {"domains": [a, b]}


def test_listed_domain_is_accepted_and_unlisted_is_refused(
    client, capture_emails, reset_email_domains,
):
    listed = _domain("a")
    _set_active(listed)
    assert client.get(URL).json() == {"domains": [listed]}

    def init(domain):
        return client.post("/api/auth/register/init", json={
            "name": "Test User",
            "email": f"integ_{_uuid.uuid4().hex[:12]}@{domain}",
            "password": PASSWORD,
        })

    assert init(listed).status_code == 200
    refused = init(_domain("unlisted"))
    assert refused.status_code == 422
    assert f"@{listed}" in refused.json()["detail"]         # тот же список, что в подсказке

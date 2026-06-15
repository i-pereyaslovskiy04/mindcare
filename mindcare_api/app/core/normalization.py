def normalize_email(email: str) -> str:
    """Return the canonical form of an email address: stripped and lowercased."""
    return email.strip().lower()


def mask_email(email: str) -> str:
    """
    Mask an email for safe logging: keep the first local char and the full
    domain, hide the rest. ``ivan@domain.ru`` -> ``i***@domain.ru``.

    Used so application logs carry enough context for diagnostics without
    storing full PII. Invalid/empty input falls back to ``***``.
    """
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if not local or not domain:
        return "***"
    return f"{local[0]}***@{domain}"

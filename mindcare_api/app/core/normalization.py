def normalize_email(email: str) -> str:
    """Return the canonical form of an email address: stripped and lowercased."""
    return email.strip().lower()

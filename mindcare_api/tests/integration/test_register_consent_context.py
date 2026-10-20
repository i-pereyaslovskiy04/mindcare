"""
Stage 31m-fix-b1 — registration confirm propagates IP / User-Agent into
consent_records (previously the route computed them but did not pass them to
the service, so consent records were stored with NULL ip_address/user_agent).

Requires dev PostgreSQL on alembic head (seeded consents) + EMAIL_MODE=dev.
"""

from app.db.session import SessionLocal
from app.db.models import ConsentRecord, User


def test_register_confirm_persists_consent_ip_and_user_agent(
    client, test_email, capture_emails,
):
    init = client.post("/api/auth/register/init", json={
        "name": "Тест Тестов",
        "email": test_email,
        "password": "SecurePass42!",
    })
    assert init.status_code == 200
    code = capture_emails[test_email][-1]

    confirm = client.post(
        "/api/auth/register/confirm",
        json={"email": test_email, "code": code},
        headers={"User-Agent": "pytest-agent/1.0"},
    )
    assert confirm.status_code == 201

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == test_email).first()
        assert user is not None
        records = (
            db.query(ConsentRecord)
            .filter(ConsentRecord.user_id == user.id)
            .all()
        )

    # both required consents (privacy_policy + data_processing) recorded
    assert len(records) >= 1
    for rec in records:
        assert rec.ip_address is not None          # 127.0.0.1 from TestClient
        assert rec.user_agent == "pytest-agent/1.0"

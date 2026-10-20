"""social_auth_foundation

Stage Social Auth 2A — фундамент для будущего входа через Яндекс ID / VK ID,
без самого OAuth flow:

  1. users.password_hash → NULLABLE. NULL = social-only аккаунт без пароля.
     Существующие строки не меняются; плейсхолдер/случайный пароль не пишется.
  2. otp_verifications.password_hash → NULLABLE. Reset-OTP больше не хранит
     копию текущего хеша пароля (лишнее хранение credential-derived значения;
     у social-only аккаунта хеша нет вовсе). Регистрационный OTP по-прежнему
     несёт хеш из register_init.
  3. user_oauth_identities — привязка provider identity к пользователю.
  4. oauth_auth_requests   — незавершённый OAuth-запрос (state hash + PKCE
     verifier только как enc:v1: ciphertext), одноразовый.
  5. oauth_pending_tickets — одноразовые ticket'ы callback → frontend (hash).

Ни одна таблица не хранит provider token / authorization code / raw state /
raw ticket / plaintext verifier / client secret / сырой профиль провайдера.

Downgrade fail-closed: при наличии users с password_hash IS NULL откат
останавливается ДО любых изменений (пароль не придумывается, аккаунты не
удаляются). Reset-OTP строки с NULL — короткоживущие (TTL 10 мин) коды сброса:
перед возвратом NOT NULL они удаляются, пользователь просто запросит код заново.

Revision ID: c6e1a4f8b2d7
Revises: f3b8d1e6a4c2
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c6e1a4f8b2d7"
down_revision = "f3b8d1e6a4c2"
branch_labels = None
depends_on = None

_PROVIDER_CHECK = "provider IN ('yandex', 'vk')"
_SHA256_HEX = "'^[0-9a-f]{64}$'"


def upgrade() -> None:
    # ── 1–2. Пароль больше не обязателен ────────────────────────────────────
    op.alter_column(
        "users", "password_hash",
        existing_type=sa.String(length=255), nullable=True,
    )
    op.alter_column(
        "otp_verifications", "password_hash",
        existing_type=sa.String(length=255), nullable=True,
    )

    # ── 3. user_oauth_identities ────────────────────────────────────────────
    op.create_table(
        "user_oauth_identities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="user_oauth_identities_pkey"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="user_oauth_identities_user_id_fkey",
        ),
        sa.UniqueConstraint("uuid", name="ux_user_oauth_identities_uuid"),
        sa.UniqueConstraint(
            "provider", "provider_subject",
            name="ux_user_oauth_identities_provider_subject",
        ),
        sa.UniqueConstraint(
            "user_id", "provider", name="ux_user_oauth_identities_user_provider",
        ),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_user_oauth_identities_provider"),
        sa.CheckConstraint(
            "char_length(provider_subject) > 0",
            name="ck_user_oauth_identities_subject_nonempty",
        ),
    )
    op.create_index(
        "ix_user_oauth_identities_user_id", "user_oauth_identities", ["user_id"],
    )

    # ── 4. oauth_auth_requests ──────────────────────────────────────────────
    op.create_table(
        "oauth_auth_requests",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("intent", sa.String(length=20), nullable=False),
        sa.Column("code_verifier_enc", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("state_hash", name="oauth_auth_requests_pkey"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="oauth_auth_requests_user_id_fkey",
        ),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_oauth_auth_requests_provider"),
        sa.CheckConstraint(
            "intent IN ('login', 'link')", name="ck_oauth_auth_requests_intent",
        ),
        sa.CheckConstraint(
            f"state_hash ~ {_SHA256_HEX}",
            name="ck_oauth_auth_requests_state_hash_format",
        ),
        sa.CheckConstraint(
            "code_verifier_enc LIKE 'enc:v1:%'",
            name="ck_oauth_auth_requests_verifier_encrypted",
        ),
        sa.CheckConstraint(
            "(intent = 'link' AND user_id IS NOT NULL) "
            "OR (intent = 'login' AND user_id IS NULL)",
            name="ck_oauth_auth_requests_intent_user",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_oauth_auth_requests_expiry",
        ),
    )
    op.create_index(
        "ix_oauth_auth_requests_expires_at", "oauth_auth_requests", ["expires_at"],
    )

    # ── 5. oauth_pending_tickets ────────────────────────────────────────────
    op.create_table(
        "oauth_pending_tickets",
        sa.Column("ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("suggested_name", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("ticket_hash", name="oauth_pending_tickets_pkey"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="oauth_pending_tickets_user_id_fkey",
        ),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_oauth_pending_tickets_provider"),
        sa.CheckConstraint(
            "kind IN ('login', 'registration', 'link_required')",
            name="ck_oauth_pending_tickets_kind",
        ),
        sa.CheckConstraint(
            f"ticket_hash ~ {_SHA256_HEX}",
            name="ck_oauth_pending_tickets_ticket_hash_format",
        ),
        sa.CheckConstraint(
            "char_length(provider_subject) > 0",
            name="ck_oauth_pending_tickets_subject_nonempty",
        ),
        sa.CheckConstraint(
            "kind <> 'login' OR user_id IS NOT NULL",
            name="ck_oauth_pending_tickets_login_user",
        ),
        sa.CheckConstraint(
            "kind <> 'registration' OR user_id IS NULL",
            name="ck_oauth_pending_tickets_registration_no_user",
        ),
        sa.CheckConstraint(
            "email IS NULL OR email = lower(trim(email))",
            name="ck_oauth_pending_tickets_email_normalized",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_oauth_pending_tickets_expiry",
        ),
    )
    op.create_index(
        "ix_oauth_pending_tickets_expires_at", "oauth_pending_tickets",
        ["expires_at"],
    )


def downgrade() -> None:
    conn = op.get_context().connection

    # Fail-closed ДО любых изменений: аккаунты без пароля нельзя вернуть под
    # NOT NULL, не придумав пароль или не удалив пользователей — ни то ни другое
    # не делаем. Только количество, без email/id (ПДн).
    passwordless = conn.execute(sa.text(
        "SELECT COUNT(*) FROM users WHERE password_hash IS NULL"
    )).scalar()
    if passwordless:
        raise RuntimeError(
            "Cannot downgrade c6e1a4f8b2d7: "
            f"{passwordless} user(s) have no password (password_hash IS NULL). "
            "Downgrade would require inventing passwords or deleting accounts; "
            "resolve these accounts manually first."
        )

    op.drop_index("ix_oauth_pending_tickets_expires_at", table_name="oauth_pending_tickets")
    op.drop_table("oauth_pending_tickets")
    op.drop_index("ix_oauth_auth_requests_expires_at", table_name="oauth_auth_requests")
    op.drop_table("oauth_auth_requests")
    op.drop_index("ix_user_oauth_identities_user_id", table_name="user_oauth_identities")
    op.drop_table("user_oauth_identities")

    # Reset-OTP без хеша — короткоживущие коды сброса (TTL 10 мин); под старой
    # схемой их нельзя сохранить. Удаляются, пользователь запросит код заново.
    dropped = conn.execute(sa.text(
        "DELETE FROM otp_verifications WHERE password_hash IS NULL"
    )).rowcount
    if dropped:
        print(f"[INFO] c6e1a4f8b2d7 downgrade: removed {dropped} pending reset OTP(s)")

    op.alter_column(
        "otp_verifications", "password_hash",
        existing_type=sa.String(length=255), nullable=False,
    )
    op.alter_column(
        "users", "password_hash",
        existing_type=sa.String(length=255), nullable=False,
    )

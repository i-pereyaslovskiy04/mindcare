# Backend Architecture — MindCare API

> **Historical snapshot.** This document reflects backend architecture as of 2026-05-21 and is not the current source of truth.
> For current status see `README.md`, `docs/BACKLOG.md`, `docs/DECISIONS.md`, and `alembic history`.
> Known stale items: "41 tables" (actual: 46), head revision `e9a3d7f2b5c0` (actual: `b6e1f4a7c9d3`),
> missing modules: tags, categories, news, articles, media, session_notes, supervisor, psychologist,
> core/encryption.py, core/rate_limit.py, db/models/legal_basis.py.
> Known security debt section below is also stale — все перечисленные риски закрыты,
> включая rate limiting (Stage 21), hashed session tokens (Stage 22b) и legal basis (Stage 23b) — see BACKLOG.md.
> **Section 4 (Auth Flow) is superseded** by the atomic unit-of-work refactor (Stage 31m-fix-b2/b3):
> registration confirm, password reset confirm и change password теперь выполняются как
> одна Session/один commit (password update + revoke sessions + consume OTP в одной транзакции),
> а не последовательностью независимых commit как описано ниже. Current source: `README.md` § Безопасность,
> `CLAUDE.md`, `ARCHITECTURE.md`.

> Last snapshot: 2026-05-21

---

## 1. Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.11+, FastAPI |
| ORM | SQLAlchemy 2.x, **sync mode** (psycopg2) |
| DB | PostgreSQL 15+ |
| Migrations | Alembic (sole schema owner) |
| Auth | Session tokens in `user_sessions` (no JWT) |
| Email | SMTP via smtplib; dev mode prints to stdout |

**Critical:** All endpoints are `def` (not `async def`). Do not switch to asyncpg without a team decision.

---

## 2. Module Responsibilities

| File | Responsibility |
|------|---------------|
| `main.py` | FastAPI app, CORS, lifespan, router registration |
| `auth/routes.py` | HTTP only — parse request, call service, return response |
| `auth/service.py` | Business logic — validation, orchestration, no HTTP concepts |
| `auth/storage.py` | All SQLAlchemy queries for users, sessions, consents |
| `auth/otp_service.py` | OTP lifecycle — create (SHA-256 hash), verify, cleanup |
| `auth/audit.py` | `log_auth_event()` into auth_log (fire-and-forget, swallows errors) |
| `auth/deps.py` | FastAPI deps — `get_current_user`, `require_role` |
| `auth/security.py` | `generate_session_token()` via `secrets.token_urlsafe` |
| `auth/schemas.py` | Pydantic schemas for `/api/auth/*` |
| `users/routes_admin.py` | HTTP only — `/api/admin/users/*` (admin role required) |
| `users/service.py` | Business logic — user CRUD, password generation |
| `users/storage.py` | All SQLAlchemy queries for user management |
| `users/schemas.py` | Pydantic schemas for admin user management |
| `core/config.py` | pydantic-settings reading `.env` |
| `db/base.py` | `Base = declarative_base()` — single source of truth |
| `db/session.py` | engine singleton, `SessionLocal` factory, `get_db()` dep |
| `db/init_db.py` | Startup — `ensure_database` + `check_migrations` + `seed` |
| `db/seed.py` | Idempotent seed — roles, permissions, consents |
| `db/models/` | 10 ORM modules, 41 tables total |
| `services/email_service.py` | High-level email API (per-event functions) |
| `services/_smtp.py` | Internal SMTP transport — do not import directly |

**Layer rules:**
- `routes.*` — HTTP concerns only, no DB access, no business logic
- `service.*` — no FastAPI imports, orchestrates storage calls
- `storage.*` — only SQLAlchemy queries, no business rules
- `models/*` — ORM definitions only, no logic

---

## 3. Request Flow

```
HTTP request
  -> FastAPI router (routes.py)
      -> deps.get_current_user() [if protected endpoint]
          -> storage.find_session(token)
          -> storage.find_user_by_id(user_id)
      -> service.*()
          -> storage.*() [DB queries]
          -> otp_service.*() [if OTP involved]
          -> email_service.*() [if email needed]
      -> audit.log_auth_event() [for auth events]
  -> HTTP response
```

---

## 4. Auth Flow

**Registration:**
```
POST /api/auth/register/init
  service.register_init(name, email, password)
    otp_service.create_or_update_otp  ->  stores SHA-256(code) in otp_verifications
    email_service.send_registration_otp  ->  sends plaintext code by email
  <- 200 OK

POST /api/auth/register/confirm
  service.register_confirm(email, code)
    otp_service.verify_otp  ->  SHA-256 comparison, deletes record on success
    storage.save_user OR storage.reactivate_user
    storage.save_consent_record x2  (privacy_policy + data_processing)
  <- 201 Created
```

**Login / Session:**
```
POST /api/auth/login
  service.authenticate_user  ->  bcrypt verify
  service.create_session  ->  token stored in user_sessions
  <- 200 {session_token, expires_at, role}

Authorization: Bearer <session_token>  [on all protected requests]
  deps.get_current_user()
    storage.find_session(token)  ->  checks not revoked, not expired
    storage.touch_session(token)  ->  updates last_active
    storage.find_user_by_id(user_id)

POST /api/auth/logout
  service.terminate_session(token)  ->  sets is_revoked=True
```

**Password Reset:**
```
POST /api/auth/password/reset/init  [silent if email not found]
  otp_service.create_or_update_otp  ->  new OTP hash
  email_service.send_password_reset_otp

POST /api/auth/password/reset/confirm
  otp_service.verify_otp
  storage.update_user_password  ->  new bcrypt hash
  storage.revoke_all_user_sessions  ->  invalidates ALL sessions
```

---

## 5. DB Startup Flow

```
uvicorn app.main:app
  -> lifespan() startup
      -> init_db()
          -> ensure_database()
             tries to connect; if DB missing, creates it via postgres admin connection
          -> check_migrations()
             reads alembic_version via MigrationContext
             raises RuntimeError if current != head  <-- app refuses to start
             message: "Run: cd mindcare_api && alembic upgrade head"
          -> seed.run_seed()
             idempotent: creates roles, permissions, role_permissions, consents
      -> otp_service.cleanup_expired()
         removes expired OTP rows from previous runs
  -> "Application startup complete."
```

---

## 6. Migration Workflow

```bash
# REQUIRED before first uvicorn start (and after any ORM change)
cd mindcare_api/
alembic upgrade head

# After ORM model change: generate new migration
alembic revision --autogenerate -m "describe_change"
# Review generated file in alembic/versions/, then:
alembic upgrade head

# Verify no schema drift (use in CI)
alembic check          # exit 0 = clean, exit 1 = drift

# Inspect
alembic current        # current DB revision
alembic history        # full migration chain

# Rollback
alembic downgrade -1
```

**`env.py` design decisions:**
- `NullPool` in online mode — no pool competition with main app connections
- No `fileConfig()` call — no logging side-effects when running alembic CLI
- `include_object()` — filters partition child tables (`auth_log_2026_01` etc.)
- `compare_type=True` only in offline mode (SQL dump generation)

---

## 7. ORM Models (41 tables, 10 modules)

| Module | Tables | Notes |
|--------|--------|-------|
| `auth.py` | users, roles, user_roles, permissions, role_permissions, user_sessions | Core auth |
| `auth.py` | refresh_tokens, user_mfa_methods | NOT IMPLEMENTED — tables reserved for future |
| `profiles.py` | student_profiles, psychologist_profiles, emergency_contacts | 1:1 with users |
| `consents.py` | consents, consent_records | Required for registration (ФЗ-152) |
| `media.py` | media_files, media_versions | File attachments |
| `content.py` | categories, articles, article_categories, news, help_resources, questions_answers | CMS |
| `diagnostics.py` | tests, test_categories, questions, options, question_media, option_media, test_results, test_result_scales, student_answers | Psychodiagnostics |
| `consultations.py` | therapy_engagements, schedule_rules, schedule_exceptions, appointments, session_notes | Scheduling |
| `notifications.py` | notification_templates, notifications | In-app alerts |
| `audit.py` | auth_log, audit_log, data_change_log | Audit trail (ФЗ-152) |
| `otp.py` | otp_verifications | SHA-256 hashed OTP codes, TTL 10 min |

**Known security debt** *(snapshot status — see BACKLOG.md for current status)*:
- ~~`session_notes.content` — stored plaintext~~ ✅ Closed: Fernet encryption implemented in `app/core/encryption.py`
- ~~Audit table partitions expire 2026-12-31~~ ✅ Closed: `scripts/ensure_audit_partitions.py` manages future partitions

---

## 8. Dependency Boundaries

```
main.py
  imports: auth.routes, users.routes_admin

auth.routes
  imports: auth.schemas, auth.service, auth.audit, auth.deps

auth.service
  imports: auth.storage, auth.otp_service, services.email_service

auth.storage
  imports: db.session, db.models.*, auth.security, core.config

users.routes_admin
  imports: auth.deps, users.service, users.schemas

users.service
  imports: users.storage, users.schemas, services.email_service
  imports: auth.service.AuthError  [exception type only]
  imports: auth.service._hash      [lazy import to avoid circular]

services.email_service
  imports: services._smtp

All db.*:
  imports: db.base (Base)

All models/*:
  imports: db.base (Base only)
```

No circular imports. Import graph is acyclic.

---

## 9. Local Dev Setup

```bash
cd mindcare_api/

# Windows: activate venv
.venv\Scripts\Activate.ps1
# If blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

pip install -r requirements.txt

# .env must contain at minimum:
# DATABASE_URL=postgresql://MindcareUser:password@localhost/mindcare
# EMAIL_MODE=dev  (prints to stdout, no real SMTP needed)

alembic upgrade head
uvicorn app.main:app --reload
# -> http://localhost:8000
# -> http://localhost:8000/docs  (Swagger UI)

# Create first admin (interactive):
python scripts/create_admin.py
```

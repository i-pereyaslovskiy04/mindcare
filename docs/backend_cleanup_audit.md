# Backend Cleanup Audit — MindCare API
> Generated: 2026-05-21 | Branch: dev_integration_backend_frontend  
> Scope: `mindcare_api/app/` + supporting files  
> Method: full file read + import graph traversal + runtime usage analysis

---

## 1. Active Runtime Files

Files that are imported and executed during normal application operation.

| File | Role | Imported By |
|------|------|-------------|
| `app/main.py` | Entry point, lifespan, routers | uvicorn |
| `app/core/config.py` | Settings (pydantic-settings, .env) | session, email_sender, auth/storage |
| `app/db/base.py` | `Base = declarative_base()` | all models, env.py |
| `app/db/session.py` | `engine`, `SessionLocal`, `get_db` | all storage modules, init_db, main |
| `app/db/init_db.py` | Startup: ensure_database + check_migrations + seed | main.py |
| `app/db/seed.py` | Idempotent seed: roles, permissions, consents | init_db.py |
| `app/db/models/__init__.py` | Re-export all 41 ORM models | storage modules, audit.py, otp_service.py |
| `app/db/models/auth.py` | User, Role, UserRole, UserSession, RefreshToken, UserMfaMethod | models/__init__ |
| `app/db/models/profiles.py` | StudentProfile, PsychologistProfile, EmergencyContact | models/__init__ |
| `app/db/models/consents.py` | Consent, ConsentRecord | models/__init__, seed |
| `app/db/models/media.py` | MediaFile, MediaVersion | models/__init__ |
| `app/db/models/content.py` | Category, Article, News, HelpResource, QuestionsAnswers | models/__init__ |
| `app/db/models/diagnostics.py` | Test, Question, Option, TestResult, … | models/__init__ |
| `app/db/models/consultations.py` | TherapyEngagement, Appointment, SessionNote, … | models/__init__ |
| `app/db/models/notifications.py` | NotificationTemplate, Notification | models/__init__ |
| `app/db/models/audit.py` | AuditLog, AuthLog, DataChangeLog | models/__init__, audit.py |
| `app/db/models/otp.py` | OtpVerification | models/__init__, otp_service |
| `app/auth/routes.py` | HTTP endpoints /auth/* | main.py |
| `app/auth/schemas.py` | Pydantic request/response models | routes.py |
| `app/auth/service.py` | Business logic: register, login, session, password reset | routes.py |
| `app/auth/storage.py` | DB access: users, sessions, consents | service.py, deps.py |
| `app/auth/security.py` | `generate_session_token()` | storage.py |
| `app/auth/deps.py` | FastAPI deps: `get_current_user`, `require_role` | routes.py, users/routes_admin |
| `app/auth/audit.py` | `log_auth_event()` → auth_log table | routes.py |
| `app/auth/otp_service.py` | OTP create/verify/cleanup (SHA-256 hash) | service.py, main.py |
| `app/users/routes_admin.py` | HTTP endpoints /admin/users/* | main.py |
| `app/users/schemas.py` | Pydantic schemas for admin user management | routes_admin.py, service.py |
| `app/users/service.py` | Business logic: user CRUD, password generation | routes_admin.py |
| `app/users/storage.py` | DB access: find/create/update/delete users | service.py |
| `app/services/email_service.py` | High-level email API (per-event functions) | auth/service.py, users/service.py |
| `app/services/email_sender.py` | SMTP transport (send_email, dev mode) | email_service.py |
| `scripts/create_admin.py` | CLI: create first admin interactively | manual run |
| `scripts/test_smtp.py` | CLI: SMTP diagnostic | manual run |
| `alembic/env.py` | Alembic runtime config | alembic CLI |
| `alembic/versions/*.py` | 5 migrations (af13→e9a3) | alembic CLI |

---

## 2. Dead Files

Files that exist but are **never imported or executed** at runtime.

| File | Status | Reason | Action |
|------|--------|--------|--------|
| `app/auth/otp_store.py` | **DEAD** | 3 lines — raises `ImportError` with deprecation message. Zero imports in project. | **DELETE** |
| `app/users/routes.py` | **DEAD** | Empty file (0 bytes). Not imported in `main.py` or anywhere else. | **DELETE** |
| `app/db/models.py` | **DEAD** | Supposed compatibility shim, but Python resolves `app.db.models` to the **package** (`models/__init__.py`), not this file. Confirmed: `app.db.models.__file__` → `models/__init__.py`. Shim is unreachable. | **DELETE** |
| `test_raw_smtp.py` | **DEAD** | Standalone SMTP diagnostic script at repo root. Not part of `scripts/`. Untracked by git. | **DELETE** |
| `db/sql/create_audit_tables.sql` | **REDUNDANT** | All three audit tables now managed by Alembic migration `3a7c5e2b8f1d`. SQL file is untracked and would conflict if applied manually. | **DELETE** |

---

## 3. Dead Code Within Active Files

Dead functions, classes, and blocks inside otherwise active files.

| File | Symbol | Type | Reason | Action |
|------|--------|------|--------|--------|
| `app/auth/service.py` | `get_user_by_id()` | function | Defined, never called. `deps.py` calls `storage.find_user_by_id()` directly. | **REMOVE** |
| `app/auth/schemas.py` | `RegisterRequest` | class | Identical duplicate of `RegisterInitRequest`. Only referenced in a commented-out route. | **REMOVE** |
| `app/auth/routes.py` | Commented-out `/register` endpoint | dead code | 4 comment lines + dead `RegisterRequest` import. | **REMOVE** |
| `app/db/init_db.py` | `check_connection()` | function | Defined, never called externally. `ensure_database()` and `health_check()` each establish their own connections directly. | **REMOVE** |
| `app/db/session.py` | `Base` re-export | import | `from app.db.base import Base  # реэкспорт для обратной совместимости`. Nothing imports `Base` from `session.py` (verified by grep). | **REMOVE** |

---

## 4. Duplicate Abstractions

| Area | Issue | Severity |
|------|-------|----------|
| `auth/schemas.py` has `RegisterRequest` AND `RegisterInitRequest` | Identical classes. `RegisterRequest` is a leftover from a pre-OTP registration flow. | Medium |
| `auth/service.py` has `get_user_by_id()` wrapping `storage.find_user_by_id()` | Trivial proxy: one line, no logic. | Low |
| `db/session.py` re-exports `Base` | Already exported from `db/base.py`. Nobody uses the session.py path. | Low |

---

## 5. Dangerous Compatibility Shims

| File | Risk | Notes |
|------|------|-------|
| `app/db/models.py` | **Low** (but confusing) | Unreachable — Python resolves `app.db.models` to the package. File creates confusion about where models live. Safe to delete. |
| `app/auth/otp_store.py` | **Low** | Contains `raise ImportError` — would crash immediately if someone imports it by mistake. Delete removes the trap. |

---

## 6. Suggested Deletions

```
app/auth/otp_store.py            — dead, raises ImportError
app/users/routes.py              — empty (0 bytes)
app/db/models.py                 — shadowed by package, unreachable
test_raw_smtp.py                 — diagnostic script, not project code
db/sql/create_audit_tables.sql   — redundant, managed by Alembic
```

**Within files:**
```
auth/service.py:            remove get_user_by_id()
auth/schemas.py:            remove RegisterRequest class
auth/routes.py:             remove commented-out /register endpoint + dead import
db/init_db.py:              remove check_connection() function
db/session.py:              remove Base re-export
```

---

## 7. Suggested Renames

| Current | Proposed | Reason |
|---------|----------|--------|
| `app/services/email_sender.py` | `app/services/_smtp.py` | Signals internal transport layer; `email_service.py` is the public API |

---

## 8. Import Graph Issues

**Circular dependency candidates:** None found. Import graph is acyclic.

**Cross-module dependency:**
- `users/service.py` imports `AuthError` from `auth/service.py`.  
  This creates a cross-module coupling. Acceptable for the current project size — `AuthError` is a shared exception type. Alternative: move to `app/core/exceptions.py`. Not critical, not doing now.

**Print-based logging (inconsistent with log.* pattern):**

| File | Line | Issue |
|------|------|-------|
| `auth/service.py:54` | `print(f"[register_init] sending OTP to {email}")` | Should be `log.info()` |
| `auth/service.py:59` | `traceback.print_exc()` | Should be `log.exception()` |
| `auth/service.py:156` | `traceback.print_exc()` | Should be `log.exception()` |
| `users/service.py:100` | `print(f"[WARN] ...")` | Should be `log.warning()` |

`auth/audit.py:45` uses `print()` in an exception handler but also `import sys` for stderr — acceptable as a deliberate "last resort" logging path when DB is unavailable.

**Module-level constant export:**
- `app/core/config.py` exports `SESSION_EXPIRE_DAYS = settings.SESSION_EXPIRE_DAYS` as a module-level constant. `auth/storage.py` imports it directly. Minor inconsistency — everywhere else uses `settings.X`. Not harmful but slightly unexpected.

---

## 9. Naming Inconsistencies

| Item | Issue | Severity |
|------|-------|----------|
| `email_sender.py` vs `email_service.py` | Both end in service-like words; unclear which is "the" service | Low — rename sender to `_smtp.py` |
| `routes_admin.py` vs `routes.py` (users) | `routes.py` is empty; only admin routes exist | Resolved by deleting `routes.py` |
| `otp_store.py` vs `otp_service.py` | Former is dead; latter is live | Resolved by deleting `otp_store.py` |

---

## 10. Files That Should Be Internal/Private

| File | Recommendation |
|------|----------------|
| `app/services/email_sender.py` | Rename to `_smtp.py` — it's the transport implementation, not the public API |

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Active runtime files | 37 |
| Dead files (delete) | 5 |
| Dead code symbols (remove) | 5 |
| Files needing minor fixes | 5 |
| Import graph cycles | 0 |
| Rename suggestions | 1 |

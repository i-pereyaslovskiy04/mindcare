# Handoff — Impersonation администратором «Зайти под именем» (ADR-025)

**Дата:** 2026-09-01. **Ветка:** `mindcare_vb`. **Решение:** `docs/DECISIONS.md`
ADR-025.

## Что сделано

Кнопка «Зайти под именем» в `/admin/users`: администратор входит в кабинет
пользователя; в кабинете (и на любой странице) видна плашка с возвратом в
профиль администратора.

### Backend

- **Миграция `a1c2e3f4b5d6`** — `user_sessions.impersonator_user_id` (nullable
  FK → `users.id`, `ON DELETE SET NULL`). Применена к dev-БД. Новый alembic head.
- **Модель** `UserSession.impersonator_user_id`; у `User.sessions` и
  `UserSession.user` проставлен `foreign_keys` (два FK на `users.id`).
- **`auth/storage.create_session`** — параметр `impersonator_user_id`;
  `find_session` возвращает его.
- **`auth/deps.get_current_user`** — единая точка «сессия → user dict»:
  подмешивает `impersonator_user_id` + `impersonator_name` (lookup админа).
- **`/api/auth/me`** (`UserResponse`) — новые поля `impersonating: bool`,
  `impersonator_name`.
- **`users/service.impersonate_target(uuid, actor_id)`** — guard-набор:
  self → 400; admin-цель → 403; заблокирован → 403; без ролей → 403; нет → 404.
- **`POST /api/admin/users/{uuid}/impersonate`** (`routes_admin.py`,
  `ImpersonateResponse`) — создаёт сессию цели с `impersonator_user_id`, пишет
  `admin_user_impersonated` (session_id_hash новой сессии в context).
- **Registry** `admin_user_impersonated` (AUDIT_LOG, {admin}, target user,
  INDEPENDENT + **RAISE** fail-closed, как `audit_logs_viewed`). Сбой аудита →
  route отзывает созданную сессию + 503. REGISTRY 109 → 110 (AUDIT 102 → 103).

### Frontend

- **`api/users.api.impersonateUser(uuid)`**.
- **`AuthContext`** — `impersonate(uuid)` (сохраняет админский токен в
  `localStorage['mindcare_impersonator']`, подменяет сессию, `/me`),
  `stopImpersonation()` (отзыв impersonation-сессии → возврат админского токена
  → `/me`; фолбэк на полный выход, если админская сессия истекла). Экспорт
  `isImpersonating`/`impersonatorName` (серверная правда из `/me`). `_clearSession`
  чистит impersonator-ключ.
- **`ImpersonationBanner`** (`features/auth/ui/`) — плашка возврата, в `App.jsx`
  над `AppRouter` (видна и на публичных страницах).
- **`UsersTable`** — кнопка «Зайти» (icon `arrow-right`); гейт: активный,
  не удалён, не admin, не сам. **`UsersPage`** — `handleImpersonate` → navigate
  `/dashboard`.

## Тесты

- Backend unit: `tests/test_impersonation_unit.py` (guard-набор; happy-path
  route: сессия с impersonator_user_id + audit; fail-closed: сбой аудита →
  отзыв сессии + 503). Счётчики REGISTRY обновлены в 8 файлах + alembic head в
  `test_audit_created_index_model.py`.
- Backend integration (реальная запись аудита):
  `tests/integration/test_admin_impersonation_api.py` — сессия помечена
  impersonator_user_id, `last_login` цели не изменён, ровно одна
  `admin_user_impersonated` с заполненным `session_id`, `/me` по новому токену
  отдаёт `impersonating`/`impersonator_name`; guard self→400, admin-цель→403.
  Также обновлён счётчик в `test_admin_audit_api.py::test_options_reflect_the_live_registry`
  (audit_events 102 → 103).
- Прогоны: полный `./test.sh` (isolated) — 2864 passed / 70 skipped при одном
  падении count-теста viewer'а, исправлено и перепроверено отдельным isolated
  прогоном (4 passed). Целевой isolated прогон impersonation — 11 passed
  (7 unit + 4 integration). Frontend: `npm run build` ок, `test:contrast`
  254/0, затронутые jest-сьюты зелёные, lint чист.
- Frontend: `npm run build` ок; затронутые сьюты (router/AuthContext/users.api/
  UserEditModal) зелёные; lint чист.

## Что НЕ трогалось / pending-риски

- **Атрибуция действий во время impersonation:** отдельные события кабинета
  пишутся под actor = целевой пользователь (`session_id_hash` для не-auth событий
  не проставляется). Прослеживается только сам факт входа. — отдельный этап.
- `logout` при возврате пишется под actor = цель (мелкая неточность следа).
- Impersonation-сессия живёт до natural expiry, если возврат не нажали (raw-токен
  цели клиент отбрасывает при подмене). Короткоживущая сессия / серверный
  revoke-эндпоинт — не делались.
- Integration-тест `POST /impersonate` (реальная БД) — pending.
- Отклонение от границ BACKLOG (staff-доступ к кабинету) — оценка ФЗ-152 за DPO.

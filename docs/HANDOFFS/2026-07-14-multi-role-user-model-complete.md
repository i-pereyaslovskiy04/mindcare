# Handoff: multi-role user model complete

**Дата:** 2026-07-14

**Статус:** backend и frontend реализованы; документация синхронизирована.

**Решение:** `docs/DECISIONS.md`, ADR-018.

## Что завершено

Один пользователь может одновременно иметь несколько активных ролей, например
`admin`, `supervisor` и `psychologist`. Membership-роли определяют права, а
активный кабинет определяет текущий UI-контекст и, только после backend-валидации,
ветку audit/content policy.

Схема БД не менялась: M:N `roles` + `user_roles` уже существовала. Alembic-миграция
для этого этапа не потребовалась.

## Backend

### Role helpers и auth contract

- `mindcare_api/app/auth/roles.py` содержит pure helpers:
  `ROLE_PRIORITY`, `primary_role()` и `effective_role()`.
- Источник прав — все непросроченные записи `user_roles`.
- Auth/session/profile responses возвращают:
  - `roles: Role[]` — источник истины;
  - `role: Role | null` — deterministic primary для backward compatibility.
- Пустой набор ролей не маскируется как `student`: `role=null`, role guards
  отклоняют доступ.
- `require_role(...)` проверяет пересечение allowed roles с membership-набором.
- `resolve_role_or_403(...)` валидирует role context и не допускает тихий fallback
  на роль, которой нет у пользователя.

### Effective role и sensitive policy

- Chat policy выбирает scoped actor role внутри разрешённого student/psychologist
  контекста; admin/supervisor не получили доступ к therapeutic chat content.
- Supervisor audit context валидируется внутри `admin`/`supervisor` membership.
- Session notes поддерживают валидируемый `X-Active-Role`; неизвестная или
  отсутствующая membership-роль даёт 403.
- Create/update session notes остаются psychologist-scoped.
- Клиентский active role не является источником доверия и не расширяет доступ.

### Admin set-based role management

- Admin PATCH добавляет/удаляет конкретные staff-роли и не выполняет destructive
  replace-all всего `user_roles`.
- Просроченная роль при повторном добавлении реактивируется через `expires_at=None`,
  без нарушения unique constraint.
- Добавление каждой новой staff-роли требует отдельной
  `user_legal_basis_records` в той же транзакции.
- Удаление staff-роли не создаёт новое основание, но фиксируется в audit trail.
- В PATCH отсутствие `roles` означает «не менять роли»; явный `roles: []` снимает
  все staff-роли только если после операции остаётся другая активная роль
  (например, `student`), иначе backend возвращает 422. В create пустой `roles[]`
  всегда недопустим.
- `POST /api/admin/users` принимает ровно одно из legacy `role` или staff-only
  `roles[]`, дедуплицирует роли и атомарно создаёт User/UserRole/legal basis.
- `basis_reference` обязателен, trim-ится и проверяется также в storage.
- Admin list/read/create/PATCH responses возвращают активные `roles[]` и primary
  `role`; list загружает роли агрегированно, без N+1.
- Welcome email для staff role-neutral и не перечисляет выданные права.

### Ограничение promotion flow

Текущий admin PATCH разрешает добавлять staff-роли только пользователю, у которого
уже есть хотя бы одна активная staff-роль. Student-only/roleless пользователь не
может получить первую staff-роль этим endpoint. Это сознательная policy-граница;
student-to-staff promotion требует отдельного compliance-решения.

Роль `student` не назначается через admin role control. Она появляется через
self-registration или `POST /api/supervisor/students` и не должна удаляться
случайно при изменении staff-набора.

## Frontend

### Нормализация и auth state

- `shared/lib/roles.js` — единый источник frontend role priority, labels, badge
  tones, `normalizeRoles()` и `primaryRole()`.
- Явный `roles: []` является источником истины; legacy fallback `[role]`
  применяется только если поле `roles` отсутствует.
- `AuthContext` нормализует user во всех точках записи состояния.
- `activeRole` хранится в localStorage только как UI preference, сверяется с
  membership и очищается при logout/session-expired/failed restore/no session.
- Runtime-решения больше не читают legacy `user.role`.

### Выбор и переключение кабинетов

- Все авторизованные точки входа ведут на `/dashboard`.
- `DashboardRedirect`:
  - 0 ролей -> `/profile`;
  - 1 роль -> соответствующий кабинет;
  - несколько ролей + валидный `activeRole` -> выбранный кабинет;
  - несколько ролей без валидного выбора -> `RoleChooser`.
- `RoleRoute` проверяет membership в `user.roles`.
- `CabinetSwitcher` доступен в кабинетах и профиле; прямой URL кабинета
  синхронизирует `activeRole` после membership-check.
- Switcher использует disclosure buttons, поддерживает Escape/outside click,
  закрывается при scroll, пересчитывает fixed-position panel при resize/orientation
  и учитывает правый/нижний край viewport.
- В `CabinetLayout` и `AdminLayout` sidebar-версия используется на desktop,
  topbar-версия — на узких viewport.

### Admin users UI

- List/read/create/edit используют `roles[]`; таблица показывает несколько badges.
- Create/edit формы используют `StaffRolesCheckboxes` для
  psychologist/supervisor/admin.
- Существующая `student` показывается read-only badge.
- Legal basis появляется только при добавлении новой staff-роли.
- Student-only/roleless role controls disabled в соответствии с backend policy,
  но scalar-only edit остаётся доступным.

## Проверки

По финальным отчётам Claude Code:

- backend: `pytest tests/` — **890 passed**;
- frontend: `npm test -- --watchAll=false` — **57 suites / 702 passed**;
- frontend production build — success;
- `git diff --check` — clean;
- полный `npm run lint` — **0 errors / 0 warnings**.

Codex независимо подтвердил 2026-07-14:

- targeted backend (`test_roles.py`, `test_role_deps.py`, `test_normalization.py`) —
  **33 passed**;
- frontend **57 suites / 702 passed**;
- полный `npm run lint` — **0 errors / 0 warnings**;
- `npm run build` — compiled successfully;
- `git diff --check` — clean.

Integration backend tests требуют dev PostgreSQL на Alembic head. Реальный browser
smoke на 1280/800/390 px не выполнялся и остаётся ручной проверкой перед merge/demo.
В полном frontend test output есть предсуществующие React `act(...)` warnings вне
multi-role изменений.

Необязательное усиление покрытия: добавить отдельный backend integration-тест
успешного `student + staff` → `PATCH {"roles": []}` с сохранением `student` и
`admin_role_remove` audit. Текущий контракт уже реализован и закреплён frontend-тестом;
этот пункт не является release blocker.

## Что не менялось

- Alembic/схема БД;
- auth transport: DB sessions, не JWT;
- supervisor не наследует admin access;
- admin/supervisor не получили доступ к chat therapeutic content;
- student-to-staff promotion flow не добавлен;
- git commit не выполнялся.

## Основные файлы

Backend:

- `mindcare_api/app/auth/roles.py`
- `mindcare_api/app/auth/storage.py`
- `mindcare_api/app/auth/deps.py`
- `mindcare_api/app/users/storage.py`
- `mindcare_api/app/users/schemas.py`
- `mindcare_api/app/session_notes/service.py`
- `mindcare_api/app/chat/service.py`

Frontend:

- `mindcare_web/src/shared/lib/roles.js`
- `mindcare_web/src/features/auth/AuthContext.jsx`
- `mindcare_web/src/app/guards.jsx`
- `mindcare_web/src/features/auth/RoleChooser.jsx`
- `mindcare_web/src/features/auth/CabinetSwitcher.jsx`
- `mindcare_web/src/components/CabinetLayout/CabinetLayout.jsx`
- `mindcare_web/src/features/admin/AdminLayout.jsx`
- `mindcare_web/src/features/admin/users/hooks/useUserForm.js`
- `mindcare_web/src/features/admin/users/components/StaffRolesCheckboxes.jsx`

## Правила для следующих задач

1. Не использовать legacy `role` как источник разрешений.
2. Не расширять membership через `activeRole`, header или frontend state.
3. Новые кабинеты и guards строить по `roles[]`.
4. Sensitive policy выбирает validated effective role внутри уже разрешённого
   membership-набора.
5. Staff role add всегда требует legal basis и атомарной записи.
6. Не добавлять student-to-staff promotion без отдельного compliance design.
7. Не делать migration/create_all/startup DDL для текущей multi-role модели.

## Рекомендуемые модели для новых чатов

- Codex: **GPT-5.6 Sol + High** для архитектуры, документации и diff review;
  Terra + Medium допустим для обычного анализа.
- Claude Code: **Sonnet 5 + High** для основной реализации и corrective passes.
- Claude Opus 5 + High использовать для сложной архитектуры, security/compliance,
  рискованных миграций или действительно неоднозначных cross-module решений.
- При появлении новой версии модели использовать актуальную модель того же класса
  и явно указывать модель/усилие в начале задачи.

Полная постоянная матрица выбора для Codex находится в `AGENTS.md`, краткий baseline
для Claude Code — в `CLAUDE.md`.

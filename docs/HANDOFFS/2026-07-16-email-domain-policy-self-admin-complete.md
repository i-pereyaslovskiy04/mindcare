# Handoff: email-domain policy, self-admin guard and admin navigation complete

**Дата:** 2026-07-16

**Статус:** backend и frontend реализованы, миграция применена, тесты/lint/build
пройдены; документация синхронизирована.

**Решения:** `docs/DECISIONS.md`, ADR-019 и ADR-020. Multi-role foundation остаётся
зафиксирован в ADR-018 и handoff от 2026-07-14.

## Что завершено

MindCare использует управляемый DB-backed allowlist email-доменов для всех HTTP/API
путей создания новых аккаунтов. Существующие аккаунты не блокируются при изменении списка.
Одновременно закрыта случайная потеря admin-доступа при редактировании собственных
ролей, а домены регистрации вынесены из персональных настроек в отдельный системный
раздел сгруппированной admin-навигации.

Кодовые изменения опубликованы в ветке `mindcare_alex`:

- `3b02dd5` — backend allowlist, миграция и self-admin guard;
- `86b8b5e` — frontend self-admin lock;
- `af0be82` — отдельная страница доменов и группы admin-меню.

## Backend

### Модель и миграция

- Alembic head: `c7f1a9e4d2b8`, `down_revision=db0b2e177da5`.
- Таблица `allowed_email_domains`: unique `domain`, `is_active`, optional `comment`,
  `created_by_user_id`, timestamps.
- Seed содержит 11 активных доменов: `donnu.ru`, `yandex.ru`, `ya.ru`, `mail.ru`,
  `inbox.ru`, `list.ru`, `bk.ru`, `vk.com`, `rambler.ru`, `lenta.ru`, `ro.ru`.
- `Base.metadata` содержит 58 таблиц. Схема по-прежнему управляется только Alembic;
  startup DDL и `create_all()` не добавлялись.

### Creation policy

Активный точный нормализованный домен обязателен для:

- self-registration (`register/init` + `register/confirm`);
- создания staff через `POST /api/admin/users`;
- создания student через `POST /api/supervisor/students`.

Registration init делает раннюю проверку до создания/отправки OTP. Confirm повторяет
authoritative проверку в той же транзакции, что создание/реактивация пользователя,
до consume OTP. Если домен отключён между init и confirm, запрос получает 422, а OTP
не теряется.

Существующие пользователи с отсутствующим или отключённым доменом сохраняют login и
password reset. Реактивация soft-deleted пользователя требует активного домена.
Allowlist является организационной конфигурацией MindCare, а не официальным или
исчерпывающим государственным перечнем почтовых сервисов.

Локальный `scripts/create_admin.py` — отдельный privileged bootstrap/ops path и
сейчас не проверяет allowlist. Его использовать только при первичном развёртывании
или восстановлении доступа, вручную выбирая разрешённый организацией домен.

### Admin API и конкурентность

- `GET /api/admin/email-domains` — активные и отключённые строки;
- `POST /api/admin/email-domains` — добавить активный домен;
- `PATCH /api/admin/email-domains/{id}` — disable/reactivate/comment;
- DELETE отсутствует.

Повторный POST существующего или отключённого домена возвращает 409; реактивация
выполняется только PATCH `is_active=true`. Последний активный домен отключить нельзя.

Creation transaction удерживает `FOR SHARE` на разрешённой строке. Изменения списка
используют transaction-scoped advisory lock `(-2100000000, 1)` и `FOR UPDATE`, чтобы
конкурентные запросы не оставили систему без активного домена. Add/disable/reactivate/
update пишутся в `audit_log`; сырой comment в audit metadata не копируется.

### Self-admin guard

Set-based role PATCH сравнивает actor id с target user id. Администратор не может
удалить у собственного аккаунта активную membership-роль `admin`: backend возвращает
422. Другой администратор может выполнить такое изменение. Guard не запрещает
самодеактивацию или самоудаление; это отдельное продуктовое решение.

## Frontend

### Собственная роль admin

`UserEditModal` получает текущего пользователя из `AuthContext`. Для собственного
аккаунта `StaffRolesCheckboxes` блокирует только роль `admin` и показывает пояснение;
`supervisor`/`psychologist` остаются доступны по общей policy. Backend guard остаётся
авторитетным.

### Домены регистрации и admin navigation

Allowlist находится на отдельной странице `/admin/email-domains`. Страница
поддерживает list/add/disable с confirm/reactivate, loading/error/empty states и
отображает backend 409 одним alert. `/admin/settings` теперь содержит только
«Безопасность» и «Смена пароля».

Admin sidebar сгруппирован:

- **Управление:** Пользователи;
- **Контент:** Материалы, Новости, Тесты;
- **Система:** Типы материалов, Темы, Типы встреч, Домены регистрации;
- **Аккаунт:** Безопасность.

`ADMIN_NAV_GROUPS` является единым источником ссылок и breadcrumb labels. Все routes
остаются под admin membership guard; чистый `supervisor` не получает доступ.

## Проверки

По финальным фактическим прогонам Claude Code:

- backend `pytest tests/` — **961 passed** на dev PostgreSQL на Alembic head;
- frontend `npm test -- --watchAll=false` — **60 suites / 720 passed**;
- frontend `npm run lint` — **0 errors / 0 warnings**;
- frontend `npm run build` — success;
- `git diff --check` — clean.

Отдельно покрыты domain normalization/policy/admin CRUD/concurrency, сохранение OTP,
existing login/reset, self-admin backend guard, self-admin UI lock, отдельная domain
page, `/admin/settings` и grouped navigation.

## Pending перед merge/demo

Ручной browser smoke не выполнялся и остаётся обязательным:

1. 1280/800/390 px: группы sidebar, active state, breadcrumbs, отсутствие overlap.
2. `/admin/email-domains`: direct route + reload, add, disable confirm, reactivate,
   backend 409 для последнего активного домена.
3. `/admin/settings`: только security/password content.
4. Собственный user edit: `admin` locked, остальные роли не заблокированы ошибочно.
5. CabinetSwitcher у правого/нижнего края viewport из предыдущего multi-role этапа.

## Правила для следующих задач

1. Не заменять allowlist hardcoded denylist или проверкой только `gmail.com`.
2. Любой новый account-creation flow обязан использовать authoritative in-transaction
   domain check; login/reset существующих пользователей не подключать к этой policy.
3. Не потреблять registration OTP до authoritative domain check.
4. Не добавлять DELETE домена без отдельного решения по audit/history.
5. Не писать raw comment, email или другие ПДн в audit metadata.
6. Self-admin frontend lock не заменяет backend guard.
7. Не расширять self-admin guard на deactivate/delete без явного product decision.
8. Сохранять admin navigation groups и отдельность system policy от account settings.
9. Если allowlist распространяется на `scripts/create_admin.py`, отдельно спроектировать
   bootstrap/recovery поведение, чтобы не заблокировать создание первого admin.

## Рекомендуемые модели для новых чатов

- Codex: **GPT-5.6 Sol + High** для документации, security/compliance анализа и diff
  review; Terra + Medium допустим для точечного поиска и обычных объяснений.
- Claude Code: **Sonnet 5 + High** для локальной реализации, тестов и corrective pass.
- Claude Opus 5 + High использовать для изменений domain policy, auth/permissions,
  сложной миграции или неоднозначного cross-module security design.
- При появлении новой версии использовать актуальную модель того же класса и явно
  указывать модель/усилие в начале задачи.

Постоянная матрица выбора для Codex находится в `AGENTS.md`, baseline Claude Code —
в `CLAUDE.md`.

# Handoff (2026-10-06): единый обратимый lifecycle отключения и восстановления аккаунтов

Решение и обоснование — **ADR-028** (`docs/DECISIONS.md`). Правила для
backend — `mindcare_api/CLAUDE.md` («Правила бэка», блок «Lifecycle аккаунта»).

## Главное

- В админке вместо «Удалить» и чекбокса «Активен» — одно действие
  **«Отключить аккаунт»** с обязательной причиной и действие **«Восстановить»**.
- **Отключение сохраняет аккаунт, email и все связанные данные**: роли,
  профиль, OAuth identity, консультации, психологические данные. Ничего не
  удаляется, статусы консультаций не меняются, `deleted_at` не ставится.
  Отзываются все сессии.
- **Восстановление доступно только администратору** — по обращению
  пользователя. Работает и для ранее (исторически) soft-deleted аккаунтов:
  прежние id/uuid, роли, профиль и связи сохраняются. Старые сессии не
  оживают, пользователь входит заново.
- Администратор не может отключить или «удалить» себя.
- Обычный пользователь (чистый student) может отключить свой аккаунт в
  настройках. Вернуть доступ может только администратор.
- Повторная регистрация (по паролю и через Яндекс ID) отключение не обходит.

## API

| Метод | Путь | Кто | Результат |
|---|---|---|---|
| POST | `/api/admin/users/{uuid}/deactivate` `{reason}` | admin | 200 `AdminUserRead`; 422 — нет/пустая/>500 причина, лишние поля, **собственный аккаунт** (`self_admin_protected`); 404; 409 `account_already_disabled` |
| POST | `/api/admin/users/{uuid}/restore` | admin | 200 `AdminUserRead`; 404; 409 `account_already_active` |
| DELETE | `/api/admin/users/{uuid}` | admin | **больше не удаляет**: 404 / 422 (себя) / 410 `lifecycle_endpoint_required`, БД не меняется |
| PATCH | `/api/admin/users/{uuid}` | admin | реальная смена `is_active` → 422 `lifecycle_endpoint_required` (себя → `self_admin_protected`); то же значение — no-op; ФИО/телефон/роли отключённого (не удалённого) аккаунта редактируются как раньше |
| POST | `/api/auth/account/deactivate` `{confirm: true}` | любой авторизованный | 200 только для чистого student; staff (вкл. admin+student) → 403 `self_deactivation_not_allowed`; impersonation → 403; лишние поля (`user_id`/`uuid`/…) → 422 |
| GET | `/api/admin/users/?is_active=false` | admin | «Отключён» включает исторически удалённых без `include_deleted` |

`AdminUserListItem`/`AdminUserRead` дополнены полями `deactivation_source`
(`admin`/`self`/`null`), `deactivated_at` (а `AdminUserRead` — ещё
`deleted_at`). `is_active` всегда `bool`: историческое NULL = активен. Текст
причины в ответах отсутствует.

## Миграция

`d7e2a9c4f1b6_add_user_deactivation_fields` (down: `b8d2f6a3c9e4`, **новый
head**). Колонки `users.deactivated_at`, `deactivation_source`,
`deactivation_reason_enc` и 3 CHECK: допустимый источник, префикс `enc:v1:`,
все три поля заданы или все три NULL. Backfill нет. Downgrade fail-closed,
пока есть текущие отключения. ORM (`app/db/models/auth.py`) описывает те же
колонки и CHECK; `alembic check` чистый.

⚠ **К рабочей БД миграция не применялась.** Порядок деплоя обычный:
`alembic upgrade head` → перезапуск API. Окна совместимости нет: старый код
новые колонки не читает.

## Транзакции и блокировки

Все операции, которые выдают сессию, меняют lifecycle или membership
существующего пользователя, сначала блокируют его строку `users`:

- password login — `auth.storage.start_session_atomic`, `FOR UPDATE`.
  Под блокировкой повторно проверяются допуск и `password_hash` (тот ли хеш,
  для которого прошёл bcrypt). Bcrypt выполняется вне блокировки;
- impersonation — admin и target `FOR SHARE` одним запросом в порядке id;
  `last_login` цели не меняется;
- OAuth complete — identity → user, оба `FOR UPDATE`. Раньше было
  `FOR SHARE` + UPDATE, и два параллельных OAuth-входа одного пользователя
  могли взаимно заблокироваться;
- смена и сброс пароля, deactivate/restore/self, admin PATCH ролей,
  `grant_admin_role_to_existing_in_tx` (используется
  `scripts/create_admin.py`) — `FOR UPDATE`.

Отключение (причина + отзыв всех сессий + success-аудит) и восстановление
(очистка полей + отзыв оставшихся сессий + аудит) — каждое в одной
транзакции. **Restore отзывает и собственные сессии пользователя, и
impersonation-сессии, созданные им как администратором**
(`_revoke_sessions_impersonated_by`, `impersonator_user_id == user.id`):
для исторически отключённого/удалённого админа (до ADR-028 такие сессии не
отзывались) они иначе ожили бы сразу после возврата ему роли admin —
dependency проверяет инициатора и пропустила бы их. Оба отзыва, очистка
полей и `admin_user_activated` — одна транзакция; сбой аудита откатывает всё. `get_current_user` отзывает impersonation-сессию, если её
инициатор удалён, отключён или потерял admin.

## Аудит

- Success: `admin_user_deactivated` / `admin_user_activated` (actor admin,
  target user, metadata `{}`, ATOMIC/RAISE) и новое `user_self_deactivated`
  (actor = target = student).
- Failure (INDEPENDENT/SOFT, через `record_secondary_failure`):
  - новые `admin_user_deactivate_failed`, `admin_user_restore_failed`,
    `user_self_deactivate_failed`;
  - расширены коды `admin_user_delete_failed` и `admin_user_update_failed`.
- Отказ самоотключения в impersonation-сессии пишется от администратора-
  инициатора, а не от целевого пользователя. Полной атрибуции всех
  impersonation-действий не заявляется — ограничения ADR-025 остаются.
- REGISTRY 111 → 115 (AUDIT_LOG 104 → 108). `admin_user_deleted` и
  `user_reactivated` оставлены как исторические.
- DCL не пишется. Причина, email, ФИО и токены в журналы не попадают.
- Frontend `auditLabels.js`: 4 события, 5 failure-кодов, обновлены подписи
  lifecycle.

## Frontend

- `/admin/users`:
  - `UserLifecycleDialog` (заменил `DeleteConfirmDialog`): обязательная
    причина, счётчик 500 символов, пояснение «данные и email сохранятся,
    восстановление — администратор»;
  - в таблице статусы «Активен» / «Отключён» (+ «по запросу пользователя») /
    «Отключён (удалён ранее)» и действия «Отключить аккаунт» (у своего
    аккаунта не показывается) и «Восстановить»;
  - фильтр «Отключён»;
  - в edit-модалке вместо чекбокса «Активен» — статус только для чтения.
- `/student/settings`: карточка «Отключение аккаунта» — только для чистого
  студента и не в impersonation. Модалка подтверждения; после успеха —
  переход на `/` и очистка клиентской авторизации без `logout()` (сессия уже
  отозвана).
- API: `deactivateUser`, `restoreUser`, `deactivateOwnAccount`; `deleteUser`
  удалён; `is_active` исключён из PATCH allowlist.

## Проверки

- Backend, полный прогон на изолированной БД
  (`ENV=test scripts/isolated_test_db.py`): **3621 passed, 78 skipped, 0
  failed**, включая `test_models_match_migrations` (`alembic check`).
- Новые тесты:
  - `tests/test_user_lifecycle_unit.py`;
  - `tests/integration/test_user_lifecycle_api.py`: собственный аккаунт,
    причина, сессии до и после restore, исторически soft-deleted,
    редактирование отключённого, `is_active` NULL, самоотключение, staff,
    impersonation, регистрация/OAuth, failure-injection audit/commit,
    утечки;
  - `tests/integration/test_user_lifecycle_concurrency.py`: login ∥
    deactivate в обоих порядках, impersonation ∥ deactivate, self ∥ grant
    admin в обоих порядках, PATCH ∥ self, deactivate ∥ deactivate,
    deactivate ∥ restore;
  - `tests/integration/test_session_issuance_concurrency.py`: два password-
    и два OAuth-входа одного пользователя; вход со старым паролем после
    reset/change; reset/change отзывает сессию входа, завершившегося первым.
  - Ожидание — по `pg_stat_activity`, `pg_stat_database.deadlocks` не растёт.
- Исправление restore исторического администратора (impersonation-сессии):
  - `test_restore_historical_admin_revokes_own_and_impersonation_sessions`
    ×3 (отключён без `deleted_at`; soft-deleted; soft-deleted с
    `is_active=true`): токены не трогаются до restore (иначе dependency сама
    отзовёт их и скроет дефект), другой администратор восстанавливает →
    собственный и impersonation-токены 401, обычная сессия цели и сама цель
    не затронуты, `admin_user_activated` от восстановившего admin, metadata
    `{}`;
  - `test_restore_audit_failure_rolls_back_both_revocations`: сбой аудита →
    аккаунт остаётся удалённым, обе группы сессий не отозваны (проверка по БД);
  - unit: `restore_user` вызывает оба отзыва;
  - мутационная проверка: без нового вызова три регрессионных теста падают.
  - Полный backend-прогон после исправления: **3625 passed, 78 skipped, 0
    failed**; unit — 2265 passed. Новых EventSpec, DCL, схемы и миграций нет.
- Обновлены под новый контракт тесты registry, CRUD/DCL/регистрации/allowlist,
  входа и impersonation.
- Frontend: `npm test -- --watchAll=false` — **1306 passed**; `npm run lint` —
  0 замечаний; `npm run build` — успешно.
- Ручной smoke в браузере **не выполнялся**. Перед релизом пройти
  `/admin/users` (отключение с причиной, «Восстановить», у себя кнопки нет) и
  `/student/settings` (самоотключение → публичная страница с сообщением).

## Не трогалось

Статусы консультаций, engagements, психологические данные, DCL/CHANGE_REGISTRY,
OAuth auto-link (по-прежнему нет), UNIQUE email, миграции рабочей БД,
`backfill_student_role.py`.

## Остаточные риски

- Можно отключить последнего другого администратора: политики «последнего
  админа» нет.
- Физическое удаление админа (FK `ON DELETE SET NULL`) превратило бы
  impersonation-сессию в обычную. В приложении физического удаления нет.
- Текст причины после восстановления не хранится. Если понадобится история
  отключений — отдельная таблица и решение DPO о retention.
- Frontend-снимок `auditLabels` и раньше отставал от backend registry
  (события после Stage 8 без подписей) — вне этой задачи.
- Сообщение 409 «Email уже зарегистрирован» на init теперь отвечает и для
  отключённых/удалённых email (раньше — только для активных). Это то же
  раскрытие, что уже было у OAuth-регистрации.

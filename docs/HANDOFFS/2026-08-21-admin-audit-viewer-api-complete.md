# Handoff: read-only admin API просмотра трёх журналов (Stage 8)

**Дата:** 2026-08-21

**Статус:** backend реализован, unit и gated integration проходили. Production/dev
БД не изменялись, commit/push не выполнялись. Рабочее дерево содержит
накопленный diff Stages 1–7 плюс изменения этой задачи — ничего не откатывать
без отдельного решения.

**Alembic head:** `e6c3a9f1d574` (`add_audit_chronological_indexes`),
predecessor — `c8e2b5f7a3d1`.

**Решение:** ADR-023 в `docs/DECISIONS.md`.

## Зачем

Stages 1–7 закрыли **запись** трёх журналов, но не чтение. Единственным способом
увидеть, кто менял роли, кто читал заметки сессий и какие были неудачные входы,
оставался прямой SQL по базе — то есть обращение мимо приложения, само по себе
не оставляющее следа. Построенный audit-контур был неоперабелен.

## Что добавлено

`GET /api/admin/audit/…` — четыре эндпоинта, только роль `admin`:

| Endpoint | Назначение | Пишет `audit_logs_viewed` |
|---|---|---|
| `/events` | `audit_log` — семантические действия | да, `journal=audit_log` |
| `/auth-events` | `auth_log` — аутентификация и сессии | да, `journal=auth_log` |
| `/data-changes` | `data_change_log` — имена изменённых полей | да, `journal=data_change_log` |
| `/options` | справочник фильтров из живых registry | **нет** |

Общие параметры: `page` (≥1), `size` (1..100, по умолчанию 20), `date_from` /
`date_to` (`YYYY-MM-DD`), `order` (`asc|desc`). Произвольный `sort` не
принимается — сортировка всегда `created_at`, затем `id`.

### Модули

| Файл | Роль |
|---|---|
| `app/audit/admin_policy.py` | производные от registry множества + `classify_actor`. Импортируется И storage (SQL-предикаты), И service (проекция) — структурная гарантия одинаковой классификации |
| `app/audit/admin_storage.py` | весь SQLAlchemy: явные колонки, alias-join'ы, предикаты классов актора, семантический target |
| `app/audit/admin_service.py` | валидация запроса, проекция DTO, DTO-политика metadata, запись access-события |
| `app/audit/admin_schemas.py` | Pydantic DTO — закрытый набор полей |
| `app/audit/routes_admin.py` | HTTP, router-level `require_role("admin")`, маппинг 422/503 |

Writer-facade `record_event()` остался отдельной публичной точкой записи;
циклических импортов нет (admin-модули импортируют `app.audit.service` напрямую,
а не через `app.audit.__init__`).

## Ключевые инварианты

1. **Гарантия структурная, а не фильтрующая.** `description`, сырая `metadata`,
   `ip_address`, `user_agent`, `session_id`, `mfa_method`, `request_url`,
   `request_method`, `old_values`, `new_values` не выбираются из БД и
   отсутствуют в схемах DTO физически.
2. **Внутренний `users.id` не выходит наружу ни в ответе, ни в query.**
   Цель-человек адресуется только `target_user_uuid`; `entity_ref` и
   `record_id` для пользователя равны `null`. Целочисленный идентификатор цели
   допускается **только с явным не-пользовательским типом**: `entity_id`
   требует `entity_type`, `record_id` требует `table_name`. Без типа integer
   неоднозначен и сопоставляется в том числе с пользовательскими строками, то
   есть перебором давал бы отображение `users.id → UUID`. Все четыре
   нарушения — отсутствие типа и пользовательский тип — дают 422 до обращения
   к журналам и до записи access-события.
3. **`user_id IS NULL` не равно `anonymous`.** FK объявлен `ON DELETE SET NULL`,
   поэтому после физического удаления аккаунта `login` / `logout` /
   `password_change` тоже теряют actor id. Класс выводится из `ActorPolicy`
   спеки; для `audit_log` и `data_change_log` дополнительно проверяется роль по
   `allowed_actor_roles`.
4. **Фильтр и проекция классифицируют строку одинаково по построению.**
   `unavailable` в SQL — отрицание объединения трёх остальных предикатов, и
   каждый положительный предикат обёрнут в `coalesce(expr, false)`: без этого
   трёхзначная логика (`role = 'system'` при NULL) давала бы `NULL`, `NOT(NULL)`
   — снова `NULL`, и строка молча выпадала бы из `unavailable`.
5. **`validate_metadata()` — не финальная DTO-проекция.** Поверх неё закрытый
   `_METADATA_DTO_POLICY`: `linked_user_id` → `linked_user_uuid` (батч-резолв
   одним запросом на страницу), неклассифицированный ключ отбрасывается.
   Полнота проверяется на импорте модуля.
6. **Всё несогласованное редактируется.** Неизвестное событие → `event_code =
   "legacy_unknown_event"`, `outcome=null`, `failure_code=null`, `target=null`,
   `details={}`, `details_redacted=true`; к `spec` в этой ветке не обращаются.
   `actor.kind = unavailable` всегда даёт `details_redacted=true` — это класс
   «актора установить не удалось» (обнулённый `ON DELETE SET NULL`
   идентификатор, отсутствующая строка `users`, роль вне allowlist), и потеря
   сведений не должна выглядеть как штатное «действие совершил никто».
   `anonymous` и `system` признака редактирования не получают.
7. **`/options` вычисляется, а не хардкодится.** `operations` — union реальных
   `allowed_operations` (сегодня ровно `["UPDATE"]`), `actor_kinds` —
   per-journal producible-набор (для `data_change_log` — `["user",
   "unavailable"]`, без `system`).
8. **Просмотр аудируется fail-closed.** `audit_logs_viewed` пишется ПОСЛЕ
   выборки и ДО ответа, поэтому не попадает в собственный результат; сбой
   записи даёт 503 без единой строки журнала.

## Corrective pass (после первичной реализации)

Найден и закрыт дефект: `entity_id` без `entity_type` попадал в полную
дизъюнкцию `SEMANTIC_TARGET`, включая ветку `user`. Это делало внутренний
`users.id` рабочим ключом поиска — запрос `?entity_id=<users.id>` возвращал
событие над этим человеком вместе с безопасной сводкой цели (UUID и текущее
ФИО), то есть перебором восстанавливалось отображение `users.id → UUID`.
Симметричная дыра была у `record_id` без `table_name`.

Исправление — в `admin_service._reject_internal_id_for_user_target`:
целочисленный идентификатор требует явного не-пользовательского типа цели.
Проверка выполняется до storage и до `record_event`. Схема, миграция и
EventSpec не менялись.

Тем же проходом уточнено правило `details_redacted`: `actor.kind = unavailable`
теперь всегда помечает строку отредактированной. Раньше условие было
`actor_id is not None and kind != user`, поэтому строка известного
USER_REQUIRED-события с обнулённым `actor_id` выглядела штатной.

## Registry

Новое событие `audit_logs_viewed`: `Destination.AUDIT_LOG`,
`ActorPolicy.USER_REQUIRED` {admin}, `TargetPolicy.FORBIDDEN`, `entity_type=None`,
только `Outcome.SUCCESS`, без failure codes, `TxMode.INDEPENDENT` +
`FailurePolicy.RAISE`, `DescriptionPolicy.NONE`, `user_email_allowed=False`.

metadata — два закрытых enum'а: `journal` и `filter_keys` (13 стабильных ИМЁН
фильтров, без единого значения). Правила сбора: `date_range` присутствует всегда
(окно применяется и по умолчанию); применённость определяется через
`is not None`, а не по истинности значения — иначе `success=false` (просмотр
неудачных входов) не попал бы в журнал; `access_events` добавляется только при
`include_access_events=true`.

**Счётчики: `AUTH_LOG=7`, `AUDIT_LOG=87`, всего `94`** (было 7/86/93).
Обновлены 15 assertions в 8 тестовых файлах плюс два закрытых множества:
`_EXPECTED_AUDIT_LOG_EVENTS` и `_EXISTING_METADATA_KEYS`.

## Миграция и индексы

`e6c3a9f1d574` создаёт `idx_audit_created`, `idx_auth_created`,
`idx_dcl_created` — по одному `(created_at, id)` на partitioned parent каждого
журнала. Причина: составной PK партиционированных журналов — `(id, created_at)`
(требование PostgreSQL), поэтому хронологическое окно им не обслуживается.

Стиль повторяет `f2a9c4e7b1d8`: raw `op.execute` на parent, downgrade STRICT
(без `IF EXISTS`, без `CASCADE`), снимаются только эти три индекса. Индексы
зеркалированы в ORM (`app/db/models/audit.py`).

> **Деплой.** `CONCURRENTLY` для partitioned table PostgreSQL не поддерживает:
> миграция берёт короткое, но блокирующее запись окно и строит индексы по всем
> партициям. На заполненной базе окно планировать заранее. Данные не меняются ни
> в одну сторону, downgrade безопасен.

**Дополнительные индексы НЕ добавлялись** — по результатам замера, а не «на
всякий случай». `EXPLAIN` на 40 000 строк в каждом журнале:

| Запрос | План |
|---|---|
| Лента по умолчанию (все три) | `Index Only Scan Backward` по дочернему `*_created_at_id_idx`, pruning до одной партиции, без `Sort`, cost ≈ 2 |
| `audit_log` + `event_type` | существующий `idx_audit_event` + `Incremental Sort`, cost 4.5 |
| `audit_log` + `outcome` | существующий `idx_audit_outcome`, cost 29.8 |
| `auth_log` + `success` | новый хронологический индекс с фильтром, cost 6.2 |
| `data_change_log` + `table_name` | новый хронологический индекс, cost 4.5 |

## Тесты

Новые unit (`mindcare_api/tests/`): `test_audit_admin_query_unit.py`,
`test_audit_admin_actor_kind_unit.py`, `test_audit_admin_options_unit.py`,
`test_audit_admin_projection_unit.py`, `test_audit_admin_metadata_dto_unit.py`,
`test_audit_admin_leak_unit.py`, `test_audit_logs_viewed_event_unit.py`,
`test_audit_created_index_model.py`, `test_alembic_single_head.py`.
Вспомогательные модули (не собираются pytest): `tests/audit_admin_rows.py`,
`tests/alembic_script.py`.

Новые gated integration: `tests/integration/test_admin_audit_api.py`,
`test_audit_created_indexes_migration.py` (`MINDCARE_MIGRATION_ROUNDTRIP=1`),
`test_audit_admin_index_explain.py` (`MINDCARE_AUDIT_EXPLAIN=1`).

Теста «ровно один Alembic head» в проекте раньше не было — добавлен вместе с
проверками достижимости всех ревизий из head и единственности базы.

> **Важно для следующего исполнителя.** `test_admin_audit_api.py` содержит
> autouse-фикстуру `purge_journal_rows`, которая удаляет строки журналов,
> созданные тестом. Append-only — свойство продакшена, а не одноразовой тестовой
> БД: соседние тесты проверяют СКВОЗНЫЕ инварианты по всем строкам
> (`test_no_dcl_row_for_pii_tables_ever_carries_values`, счётчики
> `anonymize_old_ips`), и оставленные синтетические строки их ломают. Это
> обнаружилось на первом полном прогоне.

## Проверки

| Что | Результат |
|---|---|
| `compileall app tests alembic/versions` | ok |
| unit-only (`pytest tests/ --ignore=tests/integration`) | **1664 passed** |
| полный gated прогон на disposable PostgreSQL | см. ниже |
| targeted gated (`-k "admin_audit or ip_anonymization_function or no_dcl_row_for_pii"`) | **98 passed** |
| migration round-trip (`MINDCARE_MIGRATION_ROUNDTRIP=1`) | **10 passed** |
| EXPLAIN-замер (`MINDCARE_AUDIT_EXPLAIN=1`) | **7 passed** |
| `alembic heads` | ровно один — `e6c3a9f1d574` |

Live-проверки выполнялись только через `scripts/isolated_test_db.py` на
одноразовых `mindcare_test_*`. Dev/prod PostgreSQL не использовался.

```powershell
cd mindcare_api
.\.venv\Scripts\python.exe -m compileall app tests alembic/versions -q
..\test.ps1 -UnitOnly
.\.venv\Scripts\python.exe -m alembic heads

$env:ENV = "test"
.\.venv\Scripts\python.exe scripts/isolated_test_db.py -q
$env:MINDCARE_MIGRATION_ROUNDTRIP = "1"
$env:MINDCARE_AUDIT_EXPLAIN = "1"
.\.venv\Scripts\python.exe scripts/isolated_test_db.py -q -s `
    -k "audit_created_indexes_migration or audit_admin_index_explain"
```

## Что намеренно НЕ делалось

- **Frontend** — вне объёма задачи. Маршрут, таблица, фильтры и
  loading/error/empty states — отдельный этап.
- **Единая UNION-лента** трёх журналов: разные контракты, разные безопасные DTO,
  нет надёжного `correlation_id` между `audit_log` и `data_change_log`.
- **Export CSV/Excel/PDF**, detail-эндпоинт одной строки, свободный `ILIKE` по
  metadata, поиск по email/IP/User-Agent, произвольная колонка сортировки.
- **`audit_logs_access_denied`**: generic audit отказов авторизации —
  cross-cutting security-дизайн, а не частный случай одного модуля.
- **Seed / RBAC** не менялись. Permissions `admin:audit` и `auth:view_logs`
  остаются неиспользуемыми: application-level permission enforcement в проекте
  отсутствует, и опираться на них было бы имитацией защиты.
- **Дубликат `idx_auth_ip` / `idx_auth_failures`** не трогался — отдельная
  cleanup-задача.
- Исторический handoff Stages 1–7 не переписывался.

## Открытые решения

Полный список — `docs/BACKLOG.md`, раздел «Открытые решения по просмотру
журналов администратором». Кратко:

1. Допустимо ли, что **все** admin-members видят чувствительную service-use
   metadata; нужна ли отдельная роль compliance/аудитора.
2. Retention / архив / DROP и erasure строк журналов. Ограничение периода 90
   днями в API — граница производительности, **не** политика хранения.
3. Нужен ли привилегированный режим раскрытия raw IP и полного email для
   расследования инцидента и под каким основанием.
4. Экспорт: выгрузка выводит журнал за периметр приложения и вне охвата
   access-аудита.
5. Cursor pagination при росте объёма (сейчас offset с потолком 100 000).
6. Аудит отказов доступа к журналам.

## Правила для следующего исполнителя

1. Сначала прочитать `AGENTS.md`, `CLAUDE.md` (разделы «Три журнала аудита» и
   «Read-only просмотр журналов администратором»), ADR-021 / ADR-022 / ADR-023 и
   актуальные файлы `app/audit/`.
2. Не дублировать множества `admin_policy.py`: любое расхождение SQL и проекции
   означает, что фильтр вернёт строки, которые отображение считает другими.
3. Не расширять DTO «по пути»: отсутствие поля в схеме — это и есть гарантия.
4. Integration — только через Stage 1 runner; dev/prod PostgreSQL не трогать.
5. Не выполнять commit/push без явной команды пользователя.
6. Все ответы и планы для пользователя писать на русском языке.

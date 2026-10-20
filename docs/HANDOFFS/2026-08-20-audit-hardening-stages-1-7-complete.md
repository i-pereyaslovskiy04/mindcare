# Handoff: audit hardening Stages 1–7 complete

**Дата:** 2026-08-20

**Статус:** техническая реализация журналов завершена; unit- и gated integration-
проверки проходили. Production/dev БД не изменялись, commit/push не выполнялись.
Рабочее дерево содержит большой накопленный diff Stages 1–7 — ничего не
откатывать и не перезаписывать без отдельного решения.

**Текущий Alembic head:** `c8e2b5f7a3d1` (`adopt_ip_anonymization`).

## Итог

В MindCare сформирован единый audit-контур из трёх журналов:

| Журнал | Назначение |
|---|---|
| `auth_log` | Семь канонических событий аутентификации и жизненного цикла сессии |
| `audit_log` | Семантические success/failure-события с раздельными actor/target и outcome |
| `data_change_log` | Минимизированный перечень изменённых allowlisted полей для четырёх generic UPDATE-потоков |

Публичные точки входа:

- `app.audit.record_event()` — `auth_log` / `audit_log`;
- `app.audit.failsafe.record_secondary_failure()` — independently committed
  best-effort failure-события;
- `app.audit.record_data_change()` — только ATOMIC/fail-closed
  `data_change_log`.

Прямые production-вызовы `AuditLog(...)`, `AuthLog(...)`, `DataChangeLog(...)`,
динамические имена событий и legacy `app.auth.audit.log_auth_event` запрещены.
Legacy-модули `app/auth/audit.py`, `app/chat/audit.py` и
`app/session_notes/audit.py` удалены.

## Что выполнено по стадиям

### Stage 1 — изолированная тестовая БД

- Добавлен `scripts/isolated_test_db.py` с fail-closed safety gates.
- Integration выполняется только при `ENV=test` и только в одноразовой БД
  `mindcare_test_<random>`.
- Unit-only режим не подключается к PostgreSQL.
- Dev/prod URL и неподходящее имя БД должны приводить к отказу, а не к skip.
- `test.ps1` / `test.sh`, test fixtures и документация приведены к этому контуру.

### Stage 2 — outcome и failure reason

- Миграция `f2a9c4e7b1d8_add_audit_outcome.py`:
  `audit_log.outcome`, `failure_reason_code`, CHECK и индекс.
- Success/failure являются бизнес-исходом; storage failure не маскируется как
  business failure.
- Round-trip проверяет parent, все существующие партиции и новую будущую партицию.

### Stage 3 — actor/target semantics

- `audit_log.user_id` / `user_role` всегда обозначают actor.
- `entity_type` / `entity_id` обозначают target.
- Admin role changes исправлены с target user на действующего администратора.
- Отсутствующий actor context для привилегированной мутации обрабатывается
  fail closed.

### Stage 4 — facade, registry и перенос writer'ов

- Stage 4A: immutable event registry, строгая validation, единый facade,
  ATOMIC/INDEPENDENT и RAISE/SOFT как свойства `EventSpec`, а не caller override.
- Stage 4B-1: auth-события и стабильные typed failure codes.
- Stage 4B-2: roles, supervisor и email domains.
- Stage 4B-3: chat, attachments и system conversation.
- Stage 4B-4: admin user CRUD и self-profile.
- Stage 4B-5: content, tests, consent.
- Stage 4B-6: session notes, включая independently committed sensitive content read.
- Request context проходит санитизацию: невалидные IP/User-Agent отбрасываются,
  а строгая facade validation не ослабляется.

### Stage 5 — покрытие lifecycle и appointment-доменов

- Stage 5A: user activation/deactivation/reactivation, durable typed failure
  events, безопасная self-reactivation только для pure student.
- Stage 5B: appointments и unregistered student cards, включая success/failure
  audit и per-card linking.
- Stage 5C: schedules, meeting types, group sessions и maintenance jobs.
- Добавлена identity-таблица `schedule_series` и migrations
  `a1c4e8b2f7d3` → `b5d7f0a3c9e1` с backfill, ownership preflight и FK.
- Group registration использует `SELECT ... FOR UPDATE` по UUID с
  `populate_existing()`; status, booking, meeting type, registration, capacity
  и свежий lead-time cutoff перепроверяются после lock.
- Lazy mutation из GET/list удалена; completion/extension выполняются внешними
  maintenance jobs.

### Stage 6 — минимизированный data_change_log

- Закрытый `CHANGE_REGISTRY`: 4 таблицы, 25 полей, из них 15 name-only,
  10 value-enabled, плюс 1 derived-поле.
- Production call sites ровно четыре:
  - `users::_apply_role_and_scalar_changes`;
  - `appointments::update_unregistered_student_card`;
  - `appointments::update_meeting_type`;
  - `appointments::update_group_session`.
- Значения ПДн штатными writer'ами не сохраняются. Value opt-in разрешён только
  для заранее объявленных нечувствительных enum/bool/int.
- Миграция `d4a7b2c9f6e1_harden_data_change_log.py` добавляет NOT NULL/CHECK,
  fail-closed preflight и удаляет legacy PostgreSQL-функцию
  `log_data_change(...)`.
- Парность `audit_log` ↔ `data_change_log` — caller-инвариант одной транзакции,
  а не DB-correlation guarantee.

### Stage 7 — IP-анонимизация и эксплуатация

- Миграция `c8e2b5f7a3d1_adopt_ip_anonymization.py` создаёт:
  - `public.anonymize_old_ips(integer) RETURNS bigint`;
  - `public.count_old_ips(integer) RETURNS bigint`.
- Охват ровно три журнала: `audit_log`, `auth_log`, `data_change_log`.
  `user_sessions`, `consent_records`, `user_legal_basis_records` не затрагиваются.
- CLI: `scripts/anonymize_old_ips.py`, одна `engine.begin()`-граница и три
  preflight-фазы.
- Добавлены systemd units для IP-анонимизации и создания будущих audit-партиций.
- `mindcare-ensure-audit-partitions.timer` активируется автоматически.
- `mindcare-anonymize-ips.timer` устанавливается, но по умолчанию НЕ активируется:
  первый live-прогон необратим.
- Runbook: `deploy/STAGE_7_DEPLOYMENT.md`; решение: ADR-022.

## Текущие registry-инварианты

- Event registry: `AUTH_LOG=7`, `AUDIT_LOG=86`, всего `93` события.
- Все имена — стабильный snake_case.
- Actor policies и allowed roles закрыты registry.
- `AUDIT_LOG` требует роль user-актора; system и anonymous разрешаются только
  согласно конкретному `EventSpec`.
- Target policy, metadata schema, outcome allowlist, transaction mode и failure
  policy задаются registry.
- ATOMIC writer делает только `db.add` в caller session; commit/rollback/close
  принадлежат владельцу бизнес-транзакции.
- Expected precommit failures классифицируются по типу и стабильному code, без
  string matching и без `str(exc)`.
- Пароли, OTP, session tokens, ciphertext, plaintext content, SQL, traceback,
  email/ФИО/телефон и произвольный свободный текст в audit запрещены.

## Обязательное правило для нового функционала

После завершения Stages 1–7 документация усилена: каждый новый backend-сценарий
обязан пройти **audit-impact review** до реализации. Это закреплено в:

- `CLAUDE.md` — правила реализации;
- `AGENTS.md` — правила анализа и формирования промптов Codex;
- `docs/QUALITY_CHECKLIST.md` — Definition of Done и diff review;
- `README.md` / `docs/COMPLIANCE.md` — актуальная публичная архитектура.

Наличие нового события не автоматически обязательно: обычное чтение, validation
до бизнес-операции и истинный no-op могут не логироваться. Но решение
«событие требуется / не требуется» должно быть явным, с обоснованием и тестами.

Для нового backend-функционала обязательно определить:

1. событие из registry либо новый `EventSpec`;
2. actor / target / outcome / минимальную metadata;
3. ATOMIC или INDEPENDENT границу;
4. typed failure code и необходимость failure-event;
5. необходимость `data_change_log` для generic UPDATE;
6. success/failure/no-op и rollback/commit тесты;
7. отсутствие ПДн, secrets и plaintext content.

## Проверки

Последние зафиксированные результаты до создания этого handoff:

- полный backend-прогон через disposable PostgreSQL: `2345 passed, 44 skipped`;
- `test.ps1 -UnitOnly`: `1423 passed, 1 skipped`;
- после documentation audit-impact pass: `160 passed, 1 skipped` targeted;
- `git diff --check`: без ошибок; остаются предупреждения о CRLF для ранее
  изменённых `CLAUDE.md` и `app/appointments/service.py`;
- Alembic: ровно один head — `c8e2b5f7a3d1`.

Live integration выполнялся только через `scripts/isolated_test_db.py` на
одноразовых `mindcare_test_*`. Dev/prod PostgreSQL не использовался.

Базовые команды:

```powershell
cd mindcare_api
.\.venv\Scripts\python.exe -m compileall app scripts tests alembic/versions -q
..\test.ps1 -UnitOnly
.\.venv\Scripts\python.exe -m alembic heads
```

Gated PostgreSQL-проверки запускать только при безопасном admin URL:

```powershell
$env:ENV = "test"
$env:MINDCARE_MIGRATION_ROUNDTRIP = "1"
$env:TEST_DATABASE_URL = "<safe disposable-test admin URL>"
.\.venv\Scripts\python.exe scripts/isolated_test_db.py -v
```

## Эксплуатационное состояние

Код механизма логов готов, но production-активация не завершена:

1. Нужен итоговый pre-commit audit большого dirty worktree.
2. Нужен checkpoint commit/push по отдельной команде пользователя.
3. На целевой среде нужно применить Alembic до `c8e2b5f7a3d1` по runbook.
4. Нужно установить systemd units.
5. Перед IP-анонимизацией выполнить dry-run, оценить объём и получить решение
   DPO/ответственного лица о сроке.
6. Первый live-прогон выполняется вручную; только после него включается timer.

Пока timer не активирован, IP в трёх журналах хранятся бессрочно. Это осознанное
безопасное состояние: лишний день хранения обратим, ошибочно стёртый IP — нет.

## Открытые решения и известные ограничения

- Retention строк журналов и DROP/архив старых партиций — решение DPO/ops.
- Политика IP для `user_sessions`, `consent_records`,
  `user_legal_basis_records` — вне Stage 7.
- Trusted proxy extraction не реализован: authoritative source остаётся
  `request.client.host`; за reverse proxy это адрес proxy.
- Split-role deployment для maintenance functions не поддержан.
- Erasure для append-only журналов и отсутствие `correlation_id` остаются
  открытыми решениями.
- В `docs/BACKLOG.md` устарел пункт о создании дубля при admin-create с email
  soft-deleted пользователя: текущий `users.storage.create_user` проверяет всех
  User, включая deleted, и возвращает typed `EmailAlreadyExistsError` / HTTP 409.
- Self-removal активной admin-роли уже запрещён, но self-delete/self-deactivate и
  конкурентная защита последнего активного администратора требуют отдельного
  security-hardening этапа.

## Следующая задача: страница журналов для администратора

Следующую задачу начинать в новом чате с READ-ONLY анализа. До реализации нужно
определить:

- отдельные вкладки или единое представление `audit_log` / `auth_log` /
  `data_change_log`;
- admin-only backend API, server-side pagination/sorting/filtering;
- безопасную DTO-проекцию metadata, IP, email и технических идентификаторов;
- запросы к partitioned parent tables и достаточность индексов;
- frontend route, таблицу, фильтры, loading/error/empty states;
- audit impact самого просмотра журналов и защиту от рекурсивного/шумного аудита;
- unit, gated integration и frontend tests.

Экспорт CSV/Excel/PDF не добавлять без отдельного product/security/DPO решения.
Нельзя отдавать frontend произвольную metadata, plaintext content, credentials,
tokens или внутренние exception details.

## Правила для следующего исполнителя

1. Сначала прочитать `AGENTS.md`, `CLAUDE.md`, этот handoff, ADR-021/ADR-022 и
   актуальные файлы `app/audit/`.
2. Не считать historical snapshots и старые handoff источником текущей audit-
   архитектуры.
3. Не откатывать существующий dirty worktree и не форматировать несвязанные файлы.
4. Не подключаться к dev/prod БД; integration — только через Stage 1 runner.
5. Не выполнять commit/push без явной команды пользователя.
6. Все ответы и планы для пользователя писать на русском языке.


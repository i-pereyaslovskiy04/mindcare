# MindCare Quality Checklist

Практический чек-лист перед каждым PR. Не подменяет CLAUDE.md — дополняет его
конкретными командами и запретами.

---

## 1. Scope discipline

- Один PR — одна логическая задача.
- Не смешивать backend migrations и frontend UI cleanup в одном PR.
- Не смешивать auth/session changes и cosmetic UI changes.
- Не смешивать Alembic/DB changes и React component migration.
- Не смешивать role policy changes и unrelated bug fixes.

Если задача — read-only аудит, обязательно указывать в промпте:

```text
Режим READ-ONLY.
Не менять код.
Не создавать файлы.
Не редактировать JSX/CSS/Python/MD/JSON.
Только анализ и финальный отчёт.
```

---

## 2. Required checks before PR

### Frontend

```bash
cd mindcare_web
npm run build
npm run lint
```

`npm run build` — обязателен всегда.
`npm run lint` — обязателен при любых изменениях `.js`/`.jsx`.
`--max-warnings 0` — новые warnings не допускаются.

### Backend

Если менялся Python-код:

```bash
cd mindcare_api
python -m compileall app scripts -q
pytest tests/ -v
```

Или из корня проекта: `.\test.ps1` (compileall + все backend-тесты).
Текущий ожидаемый статус: **282 passed**.

### Alembic

Запускать только когда задача касается БД-моделей или миграций:

```bash
cd mindcare_api
alembic upgrade head
alembic current
```

Не запускать Alembic в рамках read-only аудита или frontend-только PR.

---

## 3. UI governance

Перед созданием любого нового локального UI-контрола проверить:

```text
mindcare_web/src/components/UI
```

### Обязательные shared-компоненты

| Компонент | Использовать для |
|-----------|-----------------|
| `Button` | Все action-кнопки: сохранить, отменить, удалить, загрузить ещё, применить |
| `ButtonLink` | React Router навигационные ссылки в виде кнопки (`<Link>` со стилями Button). Не делать `Button + navigate()` для обычной навигации |
| `Checkbox` | Настоящие form-checkbox: согласие, active/inactive, published/unpublished |
| `Toggle` | On/off переключатели: уведомления, настройки |
| `FilterChip` | Интерактивные фильтры с active/inactive состоянием |
| `Badge` | Display-only статусы, роли и состояния: опубликовано, черновик, активен, заблокирован |
| `Tag` | Display-only теги контента: тема материала, тег новости, категория статьи |
| `Select` / `MultiSelect` | Выбор одного или нескольких значений |
| `DateInput` | Выбор **только даты** (value `YYYY-MM-DD`, кастомный popover). Не использовать нативный `datetime-local`/`date` в новых формах без причины |

### Date-only поля (`DateInput`)

- Новые date-only поля — через `DateInput`, не через нативный `datetime-local`/`date`.
- `published_at` (news/articles): UI хранит `YYYY-MM-DD`, в API уходит ISO datetime (полдень UTC) — конверсия только через `dateHelpers` (`isoToDateOnly` / `dateOnlyToPublishedAtIso`). **Future date не откладывает публикацию** (нет scheduling).
- Проверять popover: flip вниз/вверх и clamp в пределах viewport (bottom/top/right/left), Escape закрывает только календарь, клик вне закрывает popover.
- Проверять mobile / low-height viewport (popover не выходит за экран, внутренний scroll).
- Для записи на приём / слотов `DateInput` не использовать — нужен будущий `SlotPicker`.

### Запрещено без явного обоснования

- Создавать локальные `.btn*`, `.checkbox*`, `.toggle*`, `.chip*`, `.badge*`, `.tag*` если подходит shared-компонент.
- Использовать `button` для display-only элементов — использовать `span`.
- Использовать `span/div` для интерактивных элементов — использовать `button/input`.

### Допустимые feature-specific исключения

Следующие элементы намеренно остаются feature-specific:

- Calendar time slots / time picker
- Calendar format chips
- `CabinetLayout` nav badges / `navBadgeSoon`
- `CabinetLayout` notification dot
- `SearchBar` count overlay / removable chips
- `TaskItem` badges
- Chat controls (feature-specific для реализованного Chat MVP)
- `DiaryEntryForm` emotion chips
- `FeaturedNews` newsTagOverlay
- `ContentPreview` category/tag
- `StudentHome` period chips / dark-card buttons
- `MultiSelect` selected tags внутри shared `MultiSelect`

Если элемент числится как feature-specific в `docs/UI_TECH_DEBT.md` — не мигрировать без отдельного решения.

---

## 4. Role policy

Актуальная модель доступа (зафиксирована в ADR-015):

| Роль | Кабинет | Область |
|------|---------|---------|
| `admin` | `/admin/*` | Пользователи, контент, новости, материалы, категории, теги |
| `supervisor` | `/supervisor/*` | Назначения студент ↔ психолог |
| `psychologist` | `/psychologist/*` | Свои студенты и сессии |
| `student` | `/student/*` | Личный кабинет |

**Supervisor не является content manager.**
Supervisor не должен роутиться в `/admin/*`.
Расширение прав supervisor требует отдельного ADR и изменения backend `require_role`.

**Legal basis для staff-ролей.** Назначение роли `psychologist`/`supervisor`/`admin`
— и при создании (`POST /api/admin/users`), и при смене роли (`PATCH …/{uuid}`) —
требует документированного основания (`legal_basis_confirmed` + `basis_type` +
`basis_reference`), которое пишется в `user_legal_basis_records`. PATCH без основания
backend обязан отклонять (роль не меняется). `consent_records` для staff не использовать.

---

## 5. Backend / Alembic rules

- Изменения SQLAlchemy-моделей должны сопровождаться Alembic-миграцией.
- Ручной SQL без Alembic запрещён, кроме явно согласованных emergency-операций.
- Перед создание миграции убедиться, что модели соответствуют желаемой схеме.
- Partial unique index `ux_therapy_engagements_active_client` должен учитываться в Alembic.
- `Base.metadata.create_all()` — не использовать (удалён; схема только через `alembic upgrade head`).
- Не вызывать `alembic.command.upgrade()` из FastAPI lifespan — deadlock.

---

## 6. Config / env rules

- Production/staging настройки — в `.env`, не захардкожены в коде.
- `.env.example` содержит все обязательные переменные.
- `.env` не коммитится (покрыт `.gitignore`).
- `ALLOWED_ORIGINS` — список frontend origins через запятую.
- `DATABASE_URL` не захардкожен в коде.

---

## 7. Logout / auth rules

- Использовать общий `useLogout` из `AuthContext`.
- Не создавать локальные logout flows.
- Logout UI внутри кабинетов — только в topbar layout (`CabinetLayout`, `AdminLayout`).
- Не дублировать logout-кнопки на settings pages.
- Изменения auth/session/token cleanup — отдельным PR.

**Атомарность auth-операций (Stage 31m-fix-b2/b3 — инварианты, не ломать):**

- Auth бизнес-операции атомарны: одна `SessionLocal()` + один финальный `commit`
  (registration confirm, password reset confirm, change password).
- Обновление пароля и отзыв сессий — в одной транзакции (не два независимых commit).
- OTP потребляется (delete) только после успешных core DB-изменений, тем же commit;
  validate OTP без удаления, чтобы при сбое core-шага код не терялся.
- SMTP/email не выполнять внутри DB-транзакции; system/auth_log уведомления —
  soft-fail после commit, их сбой не откатывает core-операцию.
- Изменения этих UoW требуют **failure-injection тестов на реальном состоянии БД**
  (`test_register_confirm_atomic`, `test_password_uow_atomic`) — недостаточно мокать service.

---

## 8. Tables / pagination rules

- Table action buttons — shared `Button`.
- Статусы в таблицах — shared `Badge`.
- Теги в таблицах — shared `Tag`.
- Pagination: текущие реализации в admin news/articles/categories используют `Button variant="secondary" size="sm"`.
- Новые pagination-блоки — через те же shared `Button`, не через bare `<button>`.
- Выделенный shared `Pagination` — отдельный будущий этап, не в рамках inline-правок.

---

## 9. Documentation / ADR rules

- Архитектурные решения — в `docs/DECISIONS.md` в формате `ADR-NNN`.
- Изменение role policy требует ADR.
- Изменение модели доступа — отдельный этап с ADR.
- Не менять политику доступа молча внутри UI/backend PR.

---

## 10. Do not do in one PR

- Не начинать Chat MVP вместе с logout/roles cleanup.
- Не смешивать Alembic и UI cleanup.
- Не делать массовый CSS cleanup без предварительного visual check.
- Не запускать `eslint --fix` без отдельного разрешения.
- Не мигрировать все UI-компоненты за один PR.
- Не менять startup/seed и auth/session в одном PR.
- Не добавлять supervisor в admin routes без ADR.
- Не удалять `.env` без отдельного подтверждения.

---

## 11. Testing strategy / Стратегия тестирования

Проект не имеет полного покрытия тестами — это MVP, покрытие добавляется поэтапно.

### Правила добавления тестов

- Новые **auth/security/backend-critical** изменения должны сопровождаться минимум unit-тестами.
- Для **endpoint/session/permissions/encryption** flows — желательно API/integration tests.
- **Legacy-код** покрывается тестами при изменении, не раньше.
- Если тесты не добавлены — в финальном отчёте **явно объяснить причину**.
- Тесты не заменяют manual smoke для пользовательских сценариев.
- "Тесты прошли" ≠ "всё работает" — только покрытые зоны гарантированы.

### Уровни тестов

| Уровень | Что тестирует | Текущий статус |
|---------|---------------|----------------|
| **Unit** | Service/helper business logic, без реальной БД | 119 тестов: change_password (13), encryption (26), normalization (16), smtp_transport (21), email_error_sanitization (11), rate_limit (18), session_security (8), auth_hardening_b1 (6) |
| **API/Integration** | Route → deps → service → storage → DB (нужен dev PostgreSQL на alembic head) | 163 теста: email_normalization_api (11), rate_limit_api (10), session_token_hashing (9), legal_basis_api (11), admin_role_patch_legal_basis (12), register_confirm_atomic (8), register_consent_context (1), password_uow_atomic (11), session_notes_api (15), touch_session (9), chat_models (6), chat_api (20), system_conversation (17), engagement_system_messages (11), chat_presence (12) |
| **Manual smoke** | Пользовательские сценарии | Обязателен при UI/UX-sensitive изменениях |
| **E2E** | Полный browser flow | Позже, когда UI стабилизируется |

Итого backend: **282 passed** (`.\test.ps1`).

Frontend (CRA jest, `npm test -- --watchAll=false`): **12 suites / 61 tests** (после Stage 31m-fix-a) —
chat (LinkifiedText, messageShape, Chat smoke), admin users (phone, useUserForm, users.api),
publishLabels, DateInput (dateHelpers, popoverPosition, DateInput) и client.js error-parsing
(FastAPI/Pydantic 422 detail array). DOM-тесты модалок не ведутся (хрупкий setup
Tiptap/ImageUpload/MultiSelect) — покрытие через pure helpers.

### Обязательные проверки перед PR

**Backend (вручную):**

```bash
cd mindcare_api
.venv\Scripts\python.exe -m compileall app -q
.venv\Scripts\python.exe -m pytest tests/ -v
```

**Frontend (при изменениях .js/.jsx):**

```bash
cd mindcare_web
npm run lint
npm run build
```

**Через скрипты в корне проекта:**

```powershell
.\test.ps1    # compileall + все backend-тесты (без запуска проекта)
.\start.ps1   # backend-тесты, затем запуск проекта
```

`start.ps1` всегда запускает `test.ps1` перед стартом серверов — проект не стартует если тесты упали.
`test.ps1` используется для ручной проверки в любой момент без запуска серверов.

### Manual smoke — пример для смены пароля

1. Войти в кабинет (студент / психолог / супервизор).
2. Перейти в Settings → Безопасность → сменить пароль.
3. Убедиться, что произошёл автоматический выход и открылась AuthModal с сообщением «Пароль изменён. Войдите снова.»
4. Ввести **старый** пароль → получить «Неверный email или пароль».
5. Ввести **новый** пароль → успешный вход.

---

## 12. Messenger MVP checklist

Применять при любых изменениях раздела «Сообщения» / chat-модуля.

**Поведение (инварианты — не ломать):**

- one-to-one chat student↔psychologist поверх `therapy_engagements`;
- system conversation read-only, без composer, всегда видна и **последняя** в списке;
- messages encrypted-at-rest (`enc:v1:`); **plaintext content не логируется** (logs/audit);
- при входе в раздел диалог НЕ открывается автоматически (VK-like);
- **mark-read только после явного клика** по диалогу (не на входе, не на hover);
- unread: глобальный nav badge (по числу диалогов) + per-dialog badge/dot/bold/фон;
- read receipts ✓/✓✓ по `read_at`; live refresh — snapshot `limit=50` + `mergeMessages`;
- linkify только http/https, **без `dangerouslySetInnerHTML`**, `rel="noopener noreferrer"`;
- approximate presence (`peer_is_online`) — точка online/offline, без last-seen-текста;
- mobile `≤900px` — list/thread, back-кнопка в шапке открытого чата.

**Тесты (backend — на alembic head + dev PostgreSQL):**

- `tests/integration/test_chat_api.py` — chat MVP end-to-end (20);
- `tests/integration/test_system_conversation.py` — system conversation backend (17);
- `tests/integration/test_engagement_system_messages.py` — system messages событий (11);
- `tests/integration/test_chat_presence.py` — approximate presence (12);
- `tests/integration/test_chat_models.py` — constraints (6).

**Frontend:**

- `mindcare_web/src/pages/student/Chat/ChatPage.smoke.test.jsx` — render list/thread.

**Manual smoke (обязателен перед demo — машинно не проверяется):**

- ширины: desktop `>900px`, tablet `~800px`, mobile `<600px`;
- роли: student, psychologist;
- supervisor engagement events (assign / transfer / close) → system-уведомление студенту;
- mobile drawer: открытие/закрытие (backdrop/✕/Escape/клик по пункту), навигация;
- mobile topbar `≤600px`: hamburger + breadcrumb + logout видны, bell/mail скрыты;
- read receipts ✓→✓✓; unread badge гаснет только после явного открытия;
- linkify: ссылка кликабельна, текст с `<script>` отображается как текст (не исполняется).

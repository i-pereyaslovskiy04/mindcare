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
Текущий ожидаемый статус после email-domain/self-admin corrective pass:
**961 passed** (`pytest tests/`; включая multi-role, email-domain
policy/admin CRUD/concurrency, self-admin guard, appointments, chat и diary).

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
| `TimePicker` | Выбор времени `HH:MM` через shared popover/input, без native `type=time`; минуты по умолчанию `00..59` |
| `DateTimeInput` | Выбор даты+времени через `DateInput + TimePicker`, без native `datetime-local` |

### Date-only поля (`DateInput`)

- Новые date-only поля — через `DateInput`, не через нативный `datetime-local`/`date`.
- `published_at` (news/articles): UI хранит `YYYY-MM-DD`, в API уходит ISO datetime (полдень UTC) — конверсия только через `dateHelpers` (`isoToDateOnly` / `dateOnlyToPublishedAtIso`). **Future date не откладывает публикацию** (нет scheduling).
- Проверять popover: flip вниз/вверх и clamp в пределах viewport (bottom/top/right/left), Escape закрывает только календарь, клик вне закрывает popover.
- Проверять mobile / low-height viewport (popover не выходит за экран, внутренний scroll).
- Для записи на приём / выбора свободных слотов `DateInput`/`TimePicker` не использовать
  как замену backend-расчёту доступности. Сетка доступных слотов остаётся feature-specific.

### Запрещено без явного обоснования

- Создавать локальные `.btn*`, `.checkbox*`, `.toggle*`, `.chip*`, `.badge*`, `.tag*` если подходит shared-компонент.
- Использовать `button` для display-only элементов — использовать `span`.
- Использовать `span/div` для интерактивных элементов — использовать `button/input`.

### Допустимые feature-specific исключения

Следующие элементы намеренно остаются feature-specific:

- Calendar time slots / slot picker
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

Актуальная модель доступа зафиксирована в ADR-015/ADR-016, multi-role модель
пользователя — в ADR-018:

| Роль | Кабинет | Область |
|------|---------|---------|
| `admin` | `/admin/*` | Пользователи, платформенный контент, новости, материалы, категории, теги |
| `supervisor` | `/supervisor/*` | Назначения, записи, расписания, группы, отчёты, test-results по policy, модерация контента |
| `psychologist` | `/psychologist/*` | Свои студенты, сессии, чаты, черновики материалов/тестов |
| `student` | `/student/*` | Личный кабинет |

**Supervisor не является пользователем admin panel.**
Чистая роль `supervisor` не должна роутиться в `/admin/*`; его операционные и
moderation-функции реализуются в `/supervisor/*` и должны быть явно защищены
backend `require_role` / scope-checks. Если один и тот же пользователь имеет роли
`admin` + `supervisor`, доступ в `/admin/*` разрешён только по membership-роли `admin`,
а не через наследование supervisor.

**Multi-role users (ADR-018).**
- Источник прав — `user_roles`; пользователь может иметь несколько активных ролей.
- Auth/profile/session payload должен содержать `roles: Role[]`. Legacy `role`
  допустим только как primary/default/effective convenience для совместимости.
- Backend `require_role` проверяет пересечение allowed roles с `current_user.roles`.
  Frontend `RoleRoute` проверяет `user.roles`, а не `user.role`.
- Для route-specific audit и sensitive content policy использовать validated
  `effective_role`/active cabinet. Клиентский active role не является источником
  доверия без backend membership-проверки.
- Явный `roles: []` является источником истины и не должен восстанавливаться из
  legacy `role`; fallback `[role]` допустим только если поле `roles` отсутствует.
- Выход, истечение сессии и неуспешный restore должны очищать сохранённый
  `activeRole`; прямой вход в кабинет синхронизирует его только после membership-check.
- При нескольких ролях и отсутствии валидного `activeRole` показывать `RoleChooser`;
  при одной роли сразу открывать соответствующий кабинет.

**Legal basis для staff-ролей.** Назначение роли `psychologist`/`supervisor`/`admin`
— и при создании (`POST /api/admin/users`), и при добавлении новой staff-роли —
требует документированного основания (`legal_basis_confirmed` + `basis_type` +
`basis_reference`), которое пишется в `user_legal_basis_records`. PATCH/role endpoint
без основания backend обязан отклонять (роль не добавляется). `consent_records` для
staff не использовать.

**Admin create/list multi-role.**
- `POST /api/admin/users` принимает ровно одно из legacy `role` или `roles[]`;
  оба поля, ни одного, пустой `roles[]` и `student` должны давать 422;
- create дедуплицирует staff-роли, требует непустой `basis_reference`
  и атомарно пишет одну `UserRole` + одну legal-basis запись на
  каждую уникальную роль; partial create при сбое недопустим;
- `GET /api/admin/users`, `GET /api/admin/users/{uuid}` и create response возвращают
  детерминированный набор активных `roles[]` и legacy primary `role`;
  просроченные роли не входят в оба поля, а отсутствие ролей не маскируется
  как `student`;
- admin list подтягивает роли одним агрегированным запросом на страницу,
  без N+1;
- welcome email для admin-created staff не упоминает конкретную роль
  или перечень прав.

**Admin edit ролей пользователя.** Роли в edit-модалке должны быть multi-role
control / set-based API, а не single-role replace:
- при добавлении `psychologist`/`supervisor`/`admin` UI обязан показать блок legal basis
  и отправить добавляемые роли + `legal_basis_confirmed`/`basis_type`/
  `basis_reference` (+опц. `legal_basis_comment`); без основания submit не проходит;
- удаление staff-роли не требует legal basis, но требует audit trail;
- отсутствие `roles` в PATCH означает «не менять роли»; явный `roles: []` означает
  снять все staff-роли и допустим только если после операции остаётся другая активная
  роль (например, `student`), иначе ожидается 422;
- backend не должен удалять весь набор `user_roles` при PATCH; добавлять/удалять только
  явно выбранные роли и не оставлять пользователя без активных ролей;
- `student` **не selectable** в admin role control. Студенты появляются через
  self-registration или staff-created student flow (`POST /api/supervisor/students`);
  существующая роль `student` отображается как read-only badge и не удаляется случайно;
- если набор staff-ролей не менялся — legal basis не требуется и role changes в PATCH
  не отправляются;
- формулировка подтверждения — «документированное основание для назначения роли
  и обработки ПДн», НИКОГДА не «согласие пользователя»;
- backend PATCH guard остаётся обязательным defense-in-depth (не полагаться только на UI).
- student-only и roleless пользователи не могут получить первую staff-роль через
  текущий PATCH policy; checkbox-контролы должны быть disabled, но scalar-only edit
  обязан оставаться доступным.
- собственный checkbox `admin` должен быть заблокирован по стабильному user id, а
  backend обязан отклонять попытку actor удалить у себя membership-роль `admin`;
  другой администратор может выполнить такое изменение.
- `CabinetSwitcher` должен оставаться доступным на desktop/tablet/mobile, не
  обрезаться sidebar overflow, закрываться по Escape/outside click/scroll и не
  выходить за границы viewport. После responsive-изменений нужен browser smoke.

**Email-domain policy (ADR-019).**
- self-registration, admin-created staff и supervisor/admin-created student
  проверяют один DB-backed allowlist точных нормализованных доменов;
- register init отклоняет запрещённый домен до отправки OTP, а confirm повторяет
  authoritative проверку в creation transaction до consume OTP;
- существующие login/password reset не должны блокироваться после отключения домена;
- soft-deleted reactivation требует активного домена;
- admin CRUD доступен только по membership-роли `admin`; DELETE отсутствует;
- duplicate/inactive domain через POST даёт 409, реактивация выполняется PATCH;
- отключение последнего активного домена даёт 409 и остаётся безопасным при
  конкурентных запросах;
- audit фиксирует add/disable/reactivate/update без сырого comment;
- состав allowlist не описывать как официальный государственный перечень.

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
- Не давать роли `supervisor` доступ в admin routes. В `/admin/*` пускает только
  membership-роль `admin`; multi-role пользователь `admin` + `supervisor` проходит
  именно по `admin`.
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
| **Unit** | Service/helper business logic, без реальной БД | change_password, encryption, normalization, email-domain normalize/validate/extract (35), smtp_transport, rate_limit, session security, pure multi-role helpers и role deps |
| **API/Integration** | Route → deps → service → storage → DB (нужен dev PostgreSQL на alembic head) | auth/security, multi-role roles, legal basis, email-domain creation policy/admin CRUD/concurrency, self-admin guard, session notes, chat, appointments/schedules/group sessions/unregistered cards/staff-created students/profile, diary |
| **Manual smoke** | Пользовательские сценарии | Обязателен при UI/UX-sensitive изменениях |
| **E2E** | Полный browser flow | Позже, когда UI стабилизируется |

Итого backend: **961 passed** по финальному прогону Claude Code (`pytest tests/`;
включает multi-role, email-domain allowlist, self-admin guard,
appointment/profile/unregistered-cards, chat attachments и diary).

Frontend (CRA jest, `npm test -- --watchAll=false`): **60 suites / 720 passed** —
multi-role normalization/auth/guards, RoleChooser, CabinetSwitcher, layout sync,
admin set-based role forms/list badges, self-admin lock, отдельная страница доменов,
группированная admin-навигация, chat role branching, appointments и diary.
Production build: success.
Полный `npm run lint` прошёл с **0 errors / 0 warnings**. Ручной browser smoke
1280/800/390 px, panel positioning у правого/нижнего края, `/admin/email-domains`
(add/disable/reactivate/409) и direct route/reload остаётся pending перед merge/demo.
Дополнительно —
chat (LinkifiedText, messageShape, Chat smoke), admin users (phone, useUserForm, users.api),
publishLabels, DateInput (dateHelpers, popoverPosition, DateInput) и client.js error-parsing
(FastAPI/Pydantic 422 detail array). DOM-тесты модалок с Tiptap/ImageUpload/MultiSelect
не ведутся (хрупкий setup) — покрытие через pure helpers; лёгкий render-smoke допустим
там, где модалка не тянет тяжёлые редакторы (например `UserEditModal.smoke.test.jsx`).

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

### Manual smoke — admin domains и self-admin

1. На 1280/800/390 px проверить четыре группы sidebar: «Управление», «Контент»,
   «Система», «Аккаунт»; ссылки и active state не должны перекрываться.
2. Открыть `/admin/email-domains` напрямую и после reload. Проверить список,
   добавление, отключение с confirm, реактивацию и отображение backend 409 при
   попытке отключить последний активный домен.
3. Проверить, что `/admin/settings` содержит только «Безопасность» / «Смена пароля».
4. В edit собственного пользователя убедиться, что checkbox `admin` заблокирован,
   а другие staff-роли доступны согласно общей policy.
5. Прямой PATCH, снимающий собственную роль `admin`, должен получить 422; тот же
   target может быть изменён другим администратором.

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
- read receipts ✓/✓✓ по `read_at`; live refresh — snapshot polling (limit=50) +
  `reconcileMessagesSnapshot` (`pollNew`): удалённые сообщения исчезают у собеседника
  после следующего tick (≤ 8 сек), без переоткрытия диалога; `mergeMessages` (add/update)
  сохранён;
- linkify только http/https, **без `dangerouslySetInnerHTML`**, `rel="noopener noreferrer"`;
- approximate presence (`peer_is_online`) — точка online/offline, без last-seen-текста;
- mobile `≤900px` — list/thread, back-кнопка в шапке открытого чата;
- действия со своим сообщением — только через кебаб-меню «…» (`MessageActionsMenu`),
  не отдельная кнопка-карандаш; недоступны для system-сообщений и в закрытой/архивной беседе;
- удаление — только после confirm (`DeleteMessageDialog`); soft delete на backend; удалённое
  сообщение пропадает из ленты **без плейсхолдера** «Сообщение удалено»;
- `MessageBubble` — meta (время/«изменено»/✓/✓✓) внутри bubble; receipts только у исходящих
  пользовательских сообщений; system-сообщения — без меню действий, без «изменено», без receipts.

**Attachments checklist (backend — проверить при любых изменениях chat attachments):**

- upload valid PDF/JPEG — 200, metadata в БД, физический файл в `CHAT_FILE_STORAGE_DIR`;
- upload valid WEBP / Excel / PowerPoint — 200;
- reject SVG — 400;
- reject пустой файл — 400;
- reject заблокированное расширение (.exe/.sh/.vbs/.scr/...) — 400;
- archives (.zip/.rar/.7z) пока не считать разрешёнными форматами;
- reject недопустимый MIME — 400;
- reject слишком большой файл — 413;
- скачивание участником — 200 с правильным Content-Disposition;
- скачивание не-участником — 403 или 404;
- upload в closed engagement — 409;
- скачивание из closed/archive чата участником — 200 (разрешено);
- upload в system conversation — запрещён;
- attachment-only message (без текста) — 200;
- text+attachment message — 200;
- edit remove one attachment — 200, оставшиеся attachments в ответе;
- edit cannot save empty (текст пустой + все вложения удалены) — 400;
- download soft-deleted attachment — 404;
- orphan cleanup helper `scripts/cleanup_orphan_attachments.py` существует для записей
  `message_id IS NULL`: перед использованием проверить dry-run;
- `--apply` запускать только после ручной проверки кандидатов;
- full retention для физических файлов soft-deleted attachments — pending;
- scheduler/autostart через cron/systemd timer не подключён.

**Attachments checklist (frontend — manual smoke):**

- attachment card в incoming bubble — читаемый контраст текста и имени файла;
- attachment card в outgoing dark bubble — читаемый контраст;
- attachment-only message видно в ленте;
- text+attachments message видно в ленте;
- text+attachments layout: сначала файлы, затем тонкий divider, затем текст как caption, затем meta;
- attachment-only message отображается без divider;
- кнопка «Скачать» в карточке работает (download trigger);
- Office/WebP скачиваются без перехода приложения на `blob:` URL; чат остаётся открытым;
- Chromium safe-save может сохранять через системный save dialog и не обязан выглядеть как обычная запись в browser downloads list;
- Firefox/Safari/старые браузеры используют anchor download fallback;
- preview button показывается только для `image/jpeg`, `image/png`, `image/webp`, `application/pdf`;
- DOCX/XLSX/PPTX/TXT/SVG/unknown MIME не показывают preview button и остаются download-only;
- student открывает jpg/png/webp preview;
- psychologist открывает jpg/png/webp preview;
- student открывает PDF preview;
- psychologist открывает PDF preview;
- preview использует authenticated blob flow (`URL.createObjectURL`), без public static URL и без токенов в URL;
- object URL очищается через `URL.revokeObjectURL` при cleanup;
- lightbox закрывается через X, overlay и Esc;
- click внутри image/PDF content не закрывает lightbox;
- download image/PDF работает как раньше;
- URL страницы не меняется, чат остаётся открытым;
- mobile `≤900px` usable, повторное открытие preview работает;
- скрепка открывает file picker;
- выбранный файл появляется в `SelectedAttachmentList`;
- удаление из `SelectedAttachmentList` убирает файл до отправки;
- drag & drop в активный чат — файл добавляется;
- drag & drop отклоняется в system/closed/archive чате;
- drop >5 файлов — ошибка, существующие файлы сохраняются;
- drop пустого файла — ошибка;
- edit сообщения — текст и вложения подтягиваются в composer;
- edit — крестик у вложения убирает его из `EditableAttachmentList`;
- edit — нельзя сохранить, если текст пустой и все вложения убраны;
- скрепка и drag & drop заблокированы в edit-mode;
- mobile — file picker через скрепку работает.

**Manual smoke result после Stage 32 hotfixes:**

- manual browser smoke attachments выполнен пользователем после Stage 32 hotfixes;
- проверены student-side и psychologist-side attachment flows: upload/download, attachment cards,
  picker/drag-drop/edit attachments;
- критичных проблем не выявлено.

**Тесты (backend — на alembic head + dev PostgreSQL):**

- `tests/integration/test_chat_api.py` — chat MVP end-to-end (20);
- `tests/integration/test_system_conversation.py` — system conversation backend (17);
- `tests/integration/test_engagement_system_messages.py` — system messages событий (11);
- `tests/integration/test_chat_presence.py` — approximate presence (12);
- `tests/integration/test_chat_models.py` — constraints (6);
- `tests/integration/test_chat_message_edit.py` — edit сообщений (10);
- `tests/integration/test_chat_message_delete.py` — delete сообщений (10);
- `tests/integration/test_chat_bootstrap_on_assignment.py` — беседа при назначении (4);
- `tests/integration/test_chat_lifecycle.py` — lifecycle engagement-беседы (8);
- `tests/integration/test_chat_attachment_models.py` — constraints attachments (20);
- `tests/integration/test_chat_attachment_api.py` — upload/download/send/list (37);
- `tests/integration/test_chat_attachment_edit.py` — edit/remove attachments (18).

**Frontend:**

- `mindcare_web/src/pages/student/Chat/useStudentChat.test.js` — hook-level: loadList, select/load messages, stale guard (быстрое переключение), active-only polling, inactive/archive no polling, send 409 fallback (silent list reload через `getConversation: null`);
- `mindcare_web/src/pages/psychologist/Chat/usePsychologistChat.test.js` — hook-level: select/load messages, stale guard, active-only polling, inactive/archive no polling, send 409 targeted refresh (`getPsychologistConversation`), delete 409 targeted refresh;
- `mindcare_web/src/pages/student/Chat/ChatPage.smoke.test.jsx` — render list/thread (student);
- `mindcare_web/src/pages/psychologist/Chat/PsychologistChatPage.smoke.test.jsx` — то же (psychologist);
- `mindcare_web/src/features/chat/components/ChatWindow.test.jsx`;
- `mindcare_web/src/features/chat/components/ChatSidebar.test.jsx`;
- `mindcare_web/src/features/chat/components/MessageList.test.jsx` — фильтрация deleted, bubble/meta, kebab-меню;
- `mindcare_web/src/features/chat/components/MessageInput.test.jsx`;
- `mindcare_web/src/features/chat/lib/LinkifiedText.test.jsx`.

**useChatCore invariants (проверяются hook-level тестами выше):**

- stale guard: `selectedRef` блокирует применение ответов от переключённой беседы;
- `pollBusyRef` mutex: параллельных poll-запросов нет;
- active-only polling: `isActive` (engagement_status === 'active') — условие запуска интервала;
- archive/closed → polling не запускается;
- student 409 → `getConversation: null` → `loadList({ silent: true })`;
- psychologist 409 → `getConversation(uuid)` → точечный update `engagement_status`/`last_message_at`;
- system conversation не обслуживается `useChatCore` (отдельный `useSystemConversation`).

**Manual smoke (обязателен перед demo — машинно не проверяется):**

- ширины: desktop `>900px`, tablet `~800px`, mobile `<600px`;
- роли: student, psychologist;
- supervisor engagement events (assign / transfer / close) → system-уведомление студенту;
- mobile drawer: открытие/закрытие (backdrop/✕/Escape/клик по пункту), навигация;
- mobile topbar `≤600px`: hamburger + breadcrumb + logout видны, bell/mail скрыты;
- read receipts ✓→✓✓; unread badge гаснет только после явного открытия;
- linkify: ссылка кликабельна, текст с `<script>` отображается как текст (не исполняется);
- своё короткое сообщение → bubble компактный, meta (время/✓✓) в одну строку с текстом;
- своё длинное сообщение → текст оборачивается, meta переносится вниз-направо;
- входящее сообщение → время внутри bubble, без read receipts;
- system-сообщение → header «MindCare», текст слева, время внутри bubble, без меню действий;
- редактирование через кебаб-меню → текст и пометка «изменено» обновляются на месте;
- удаление через кебаб-меню + confirm (пользователь A) → у A сообщение пропадает немедленно;
  у B сообщение пропадает после следующего polling tick (≤ 8 сек) без переоткрытия диалога;
  placeholder «Сообщение удалено» не появляется ни у A, ни у B;
- закрытая/архивная беседа → кебаб-меню действий не отображается;
- mobile/узкий viewport → bubble + кебаб-меню не разваливают layout (нет overflow/обрезки).

---

## 13. Student Diary checklist

Применять при любых изменениях `/student/diary`, `app/diary/` или `diary_entries`/`diary_emotions`.

**Backend (automated — `tests/integration/test_diary_api.py`):**

- Alembic migration `b2e4d7f1a9c3` применена — `diary_emotions` и `diary_entries` существуют;
- seed эмоций: `calm`, `joyful`, `anxious`, `sad`, `tired`, `angry`, `inspired`,
  `confused`, `light`, `focused`;
- `GET /api/diary/emotions` возвращает список `{key, label, sort_order}`;
- `GET /api/diary/today` — 200 для student; если записи нет — структура с `mood_score: null`;
- `PUT /api/diary/today` — создаёт или обновляет запись; идемпотентно;
- `GET /api/diary/entries?limit&offset` — пагинация, формат `{items, total, limit, offset}`;
- `PATCH /api/diary/entries/{entry_uuid}` — partial update; empty `{}` = no-op без изменения `updated_at`;
- `DELETE /api/diary/entries/{entry_uuid}` — soft-delete через `deleted_at`;
- `GET /api/diary/summary?period=14d|month|year` — fixed daily frames для 14d/month
  и monthly aggregation для year;
- Все `/api/diary/*` — **403 для psychologist, supervisor, admin** (student-only);
- чужая, удалённая или несуществующая запись при PATCH/DELETE → 404;
- malformed UUID при PATCH/DELETE → 422;
- `diary_entries.mood_score_enc`, `entry_text_enc`, `emotions_enc` — хранятся с prefix `enc:v1:`;
- Decrypt-on-read — возвращает plaintext; encrypt-on-write — принимает plaintext;
- Partial unique index: не более одной активной записи на `student_id + entry_date`;
  после soft-delete разрешено создать новую запись на ту же дату.

**Security rules (НЕ нарушать):**

- entry_text, mood_score, selected emotions — **не логировать** (ни в stdout, ни в audit);
- diary content — **только student** — 403 для всех остальных ролей;
- не смешивать с `session_notes` и `chat_messages`;
- selected emotions — только encrypted JSON в `emotions_enc`, не FK-таблица;
- audit trail diary edit/delete пока pending; не считать его реализованным.

**Frontend (automated):**

- `StudentHome.smoke.test.jsx`: next-step states, action cards, observationCard,
  отсутствие fake metrics и графика на главной;
- `DiaryPage.test.jsx` + smoke: load/save, history pagination, edit/delete sync,
  reload offset=0 после delete, observation summary, period switching, recent marks,
  null filtering, refresh summary после save/edit/delete и inline errors;
- `DiaryEntryForm`, `DiaryEntryItem`, `DiaryHistoryList`: optional details,
  edit/delete confirmation и load more.

**Manual smoke (/student/diary — обязателен перед demo):**

- No today entry: StudentHome показывает «Ваш следующий шаг», CTA «Отметить состояние»
  и «Открыть материалы»;
- создать mood-only запись; затем добавить emotions/text;
- проверить collapsible details и inline ошибки;
- edit today entry; delete today entry; создать запись повторно после delete;
- history load more; edit old entry; delete old entry; после delete нет пропуска записей;
- today entry: StudentHome показывает «Сегодняшняя отметка сохранена», score X/10,
  «Дополнить запись» и «Написать психологу»;
- `observationCard` скрыт при 0 entries и видим при `entriesCount > 0`;
- psychologist/supervisor/admin получают 403;
- в БД `mood_score_enc`, `entry_text_enc`, `emotions_enc` имеют `enc:v1:`;
- malformed UUID для PATCH/DELETE → 422;
- empty PATCH `{}` не меняет `updated_at`;
- `/student/diary`, 0 entries → empty-state сводки самонаблюдения;
- 1 entry → нейтральный текст о первой отметке;
- 2–3 entries → нейтральный текст о небольшом количестве данных;
- 4+ entries → нейтральный текст об отметках выбранного периода;
- chips периодов `14 дней` / `Месяц` / `Год` переключают summary API;
- tiles корректно показывают `Отметок`, `Последняя отметка`/`Последний период`, `Диапазон`;
- recent marks показывают только non-null points (`DD.MM · X/10`, для year — `Янв · X/10`);
- в observation block нет SVG, линии и осей; нет медицинских/диагностических выводов;
- save/edit/delete обновляют сводку активного периода;
- StudentHome не изменился и не содержит график;
- mobile/a11y пройти вручную: textarea labels, focus delete confirm, error/status announcements;
- будущие observation insights возможны только после отдельной UX-validation.

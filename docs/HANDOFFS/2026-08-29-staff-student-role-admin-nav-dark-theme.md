# Роль student для staff, навигация «На главную», предпросмотр тестов, тёмная тема

**Дата:** 2026-08-29
**Область:** backend (`mindcare_api/`) + frontend (`mindcare_web/`)
**Связанное решение:** `docs/DECISIONS.md` **ADR-024** (роль student для staff —
функциональный доступ к кабинету, отклонение от документированной role-policy).
**Опирается на:** multi-role модель ADR-018; заметку о цветовых токенах тёмной
темы `2026-08-28-decorative-overlay-dark-theme-color-tokens-note.md`.

---

## 1. Зачем

Пакет из пяти пользовательских правок + доводка тёмной темы:

1. **Роль «Студент» — всем staff.** Admin/supervisor/psychologist должны иметь
   возможность зайти в кабинет студента (посмотреть/использовать студенческий
   опыт). Кабинет закрыт `require_role("student")`, поэтому нужна **реальная**
   роль, а не UI-хак.
2. **Скрыть student при логине** для таких пользователей (не предлагать выбор
   «Студент» на экране выбора кабинета).
3. **Скрыть student в перечне ролей** в `/admin/users`.
4. **Иконка предпросмотра теста** в админском списке `/admin/tests`.
5. **Ссылка «На главную»** из всех кабинетов и панели администратора.
6. **Тёмная тема:** нечитаемый тёмный текст в переключателе/выборе кабинетов и
   инверсия Hero-баннера в тёмных палитрах.

---

## 2. Роль student для staff (ADR-024)

### Ключевое: student — реальная роль с реальными последствиями
`student_profiles` в коде **не создаётся нигде** — студент определяется только по
роли. Поэтому выдача student staff требует **изоляции**, иначе staff попал бы в
списки реальных студентов супервизора и в admin-фильтр `?role=student`.

### Backend
- `app/users/storage.py::create_user` — каждому новому staff в **той же
  транзакции** выдаётся роль student (подтягивается тем же `Role.name.in_(...)`
  запросом, отдельного legal basis для student НЕ пишется; ответ и primary `role`
  остаются staff-ролью — student ниже по приоритету).
- `app/users/storage.py::find_users` — при `role='student'` добавлен предикат
  «нет активной не-student роли»: staff не проходят фильтр.
- `app/supervisor/storage.py::get_students` — тот же `~has_other_active_role`
  предикат (и в count, и в основном запросе): staff не попадают в список
  студентов супервизора.
- `scripts/backfill_student_role.py` (новый) — разовая выдача student
  существующим staff: `--dry-run`/`--apply`, идемпотентно (реактивирует
  просроченную, учитывает `UniqueConstraint(user_id, role_id)`), логи без ПДн.
- `scripts/create_admin.py` — bootstrap-админ (новый и добавление admin
  существующему) тоже получает student идемпотентно (`ensure_student_role`);
  иначе созданный **после** backfill админ остался бы без роли (backfill
  одноразовый).

### Frontend
- `shared/lib/roles.js::selectableRoles` — у staff роль student скрыта, у чистого
  студента остаётся.
- `app/guards.jsx::DashboardRedirect` — ветвление по `selectableRoles`
  (`[admin, student]` → сразу `/admin`, без одно-кнопочного экрана); `activeRole`
  по-прежнему валидируется по **полному** набору (переход в кабинет студента
  переживает reload).
- `features/auth/RoleChooser.jsx` — список строится из `selectableRoles`.
- `features/auth/CabinetSwitcher.jsx` — **не тронут**: student остаётся пунктом
  «Перейти в кабинет». Это точка входа staff в кабинет студента.
- `features/admin/users/components/UsersTable.jsx` — бэдж student скрыт
  (переиспользован `selectableRoles`).
- `hooks/useUserForm.js` + `UserEditModal.jsx` — read-only индикатор student в
  edit-модалке показывается только чистому студенту (`isPureStudent`); для staff
  (у всех теперь есть student) он был бы ложным.

### Осознанные следствия
- **Отклонение от role-policy (ADR-024):** student выдаётся staff **без**
  `consent_records`/`user_legal_basis_records`, вопреки прежней формулировке
  `mindcare_api/CLAUDE.md` (student — только self-registration / staff-created с
  личным согласием). Роль здесь функциональная (доступ к кабинету).
- **Демотация staff:** т.к. у staff всегда есть student, админ в `/admin/users`
  может снять все служебные роли — аккаунт станет «чистым студентом» (раньше
  блокировалось валидацией «должна остаться хотя бы одна роль»). Согласуется с
  multi-role policy (`roles:[]` допустим, если остаётся активная роль). Защиту
  **решено не добавлять**.
- Остаточный риск: `supervisor/service.py:319` `_get_user_with_role(..., "student")`
  — точечная выборка по id, вне изоляции списков.

---

## 3. Предпросмотр теста в `/admin/tests`

- `TestsTable.jsx` — третья icon-кнопка `Icon name="eye"` (проп `onPreview`,
  `type="button"` + `aria-label`).
- `AdminTestsPage.jsx` — по клику подгружает полный тест (`getAdminTest`),
  преобразует в form-shape (`toPreviewShape` — переиспользует экспортированный
  `fromBackendQuestion` из `lib/testShape.js`, интерпретации маппит инлайном) и
  открывает существующий `TestPreviewModal` (глазами студента + пробный подсчёт).
- `TestFormPage.jsx` **не тронут** (его dirty-tracking завязан на load-путь —
  рефактор не тянули).

---

## 4. Ссылка «На главную»

- `features/admin/AdminLayout.jsx` — `Link to="/"` (иконка `home`) в топбаре
  `styles.actions` (не пунктом меню: `NavLink to="/"` без `end` подсвечивался бы
  активным везде и попал бы в `CRUMB_LABELS`).
- `components/CabinetLayout/CabinetLayout.jsx` — та же ссылка тем же стилем
  `.homeLink`, что в admin (по требованию — единый вид). Появляется во всех
  кабинетах (student/psychologist/supervisor).

---

## 5. Тёмная тема

### 5a. Переключатель/выбор кабинетов — нечитаемый текст
`CabinetSwitcher.module.css` и `RoleChooser.module.css` использовали
**несуществующие** токены (`--text`, `--border`, `--surface-2/3`, `--accent`) →
откат на хардкод `#1c1c1c` = тёмный текст на тёмной подложке в dark-темах.
Заменены на theme-aware токены как в рабочем Select-дропдауне: `--text-main`,
`--warm-white`, `--nav-border`, `rgba(var(--espresso-rgb) …)`, `--coffee`,
`rgba(var(--shadow-rgb) …)`.

> **Паттерн-урок:** цвета только через существующие ролевые/легаси токены
> (`src/styles/tokens/`). Несуществующий `var(--x, fallback)` в dark-темах даёт
> хардкод-fallback и «тёмное на тёмном». Проверять имена токенов перед
> использованием.

### 5b. Hero-баннер инвертировался в тёмных палитрах
`--hero-*` выведены (в базовом `:root` = `coffee-light.css`) из
`--espresso/--mocha/--coffee/--text-on-dark/…`, которые в тёмных палитрах
переворачиваются (тёмное↔светлое) → баннер становился светлым с тёмным текстом.
- Градиент Hero вынесен в токены `--hero-grad-1/2/3` (`Hero.module.css` + дефолт
  в `coffee-light.css :root`).
- В 4 тёмных палитрах (`dongu/coffee/nature/classic-dark`) весь набор `--hero-*`
  зафиксирован на **светлых брендовых литералах своей палитры** — баннер в тёмной
  теме выглядит как в светлой (тёмный брендовый градиент + светлый текст),
  включая слайды с картинкой (`--hero-bg-rgb` тоже фиксирован).
- `hc-dark` (высококонтрастный) и `a11y` (ч/б для слабовидящих) **не тронуты** —
  там осознанные accessibility-режимы.
- `npm run test:contrast` — 254 проверки, 0 нарушений (hero-пары 17.4/13.8/13.0).

---

## 6. Тесты

**Backend:** новый `tests/integration/test_staff_student_role.py` (create_user
выдаёт student; изоляция в get_students и find_users). Обновлены моки create_user
(`test_admin_user_audit_unit.py`, `test_users_failure_audit_unit.py`,
`test_normalization.py` — student в `.all()`); `test_update_role_policy...`
снимает student, чтобы проверять guard на 0-ролей. Полный suite зелёный
(integration + 1710 unit).

**Frontend:** новые кейсы `selectableRoles` (roles.test.js) и ссылки «На главную»
(AdminLayout.test.jsx); в router-моки AdminLayout/CabinetLayout добавлен `Link`.
Полный suite: 81 suites / 1081 тест, 0 падений. `lint`, `build`, `test:contrast`
чистые.

---

## 7. Эксплуатация / деплой

- **Backfill на проде:** запустить `scripts/backfill_student_role.py --dry-run`
  → оценить → `--apply`. Новые staff и bootstrap-админы получают student
  автоматически. На dev-БД backfill уже применён (3 staff).
- Схема БД **не менялась** — роль выдаётся данными, миграций нет.

---

## 8. Что НЕ трогалось
`TestFormPage` (переиспользованы только хелперы); `CabinetSwitcher` логика ролей
(student там нужен); admin role API/схемы (student по-прежнему не selectable в
чекбоксах создания/редактирования); `hc`/`a11y` темы.

# Handoff: Appointments, schedule v3, group sessions and booking flows — 2026-06-27

## Состояние проекта

**Проект:** MindCare — платформа психологической службы ДонГУ<br>
**Этап:** MVP (Этап 1)<br>
**Стек:** FastAPI + SQLAlchemy (sync, psycopg2) + PostgreSQL 15+ / React 19 + CRA + CSS Modules

---

## Что полностью готово в этом блоке работ

### 1. Модель записи и типов встреч

Реализован полноценный appointment-модуль:

- `meeting_types` — справочник типов встреч:
  - название;
  - описание;
  - длительность `duration_minutes`;
  - технический буфер `buffer_minutes`;
  - форматы `online` / `offline`;
  - признаки `is_group`, `is_active`, `is_bookable`.
- Индивидуальная запись создаётся только к назначенному психологу.
- Студент выбирает тип встречи, формат и дату; backend рассчитывает доступные слоты по рабочим окнам психолога и длительности/буферу выбранного типа.
- Индивидуальная запись создаётся в статусе `pending_confirmation`.
- Психолог подтверждает или отклоняет свою запись.
- `pending_confirmation` и `confirmed` занимают слот.
- Отмена студентом:
  - `pending_confirmation` soft-delete и исчезает из списков;
  - `confirmed` становится `cancelled`, психолог получает system-уведомление.

Правила времени:
- timezone для правил записи и отмены — `Europe/Moscow`;
- запись на тот же день разрешена только в будущий слот минимум за 1 час;
- отмена студентом — только до дня встречи.

### 2. Расписание v3

Расписание психолога теперь описывает **рабочие окна**, а не конкретные слоты и не конкретный тип встречи.

Основные сущности:

- `schedule_rules` — рабочие окна психолога:
  - `psychologist_id`;
  - день недели;
  - `start_time` / `end_time`;
  - `effective_from` / `effective_until`;
  - `series_id`;
  - `auto_extend`;
  - `created_by`;
  - `meeting_type_id` nullable legacy, для новых окон не используется.
- `schedule_breaks` — повторяющиеся перерывы внутри рабочих окон:
  - например обед 13:00–14:00;
  - разделяют `series_id` с правилами расписания;
  - имеют собственный период действия.
- `schedule_exceptions` — разовые изменения:
  - `day_off`;
  - `unavailable`;
  - `extra_availability`;
  - на одну дату допускается несколько исключений.

Supervisor управляет расписанием сериями:

| Действие | Endpoint |
|---|---|
| Создать серию rules+breaks | `POST /api/supervisor/schedules` |
| Редактировать серию | `PATCH /api/supervisor/schedules/{series_id}` |
| Проверить impact | `GET /api/supervisor/schedules/{series_id}/impact` |
| Деактивировать серию | `DELETE /api/supervisor/schedules/{series_id}` |
| Восстановить серию | `POST /api/supervisor/schedules/{series_id}/restore` |
| Продлить на месяц | `POST /api/supervisor/schedules/{series_id}/extend?months=1` |

Редактирование серии пересоздаёт rules+breaks с тем же `series_id`.
Существующие `appointments` не трогаются: если новая версия расписания больше не покрывает старую запись, запись всё равно остаётся и продолжает занимать своё время.

Auto-extend:
- работает только через maintenance script `scripts/extend_schedules.py`;
- не запускается из FastAPI lifespan;
- `auto_extend=true` требует `effective_until`;
- после автопродления supervisor, создавший серию, получает system-уведомление.

### 3. Ручная запись supervisor'ом

Ручная запись вынесена в отдельную страницу `/supervisor/booking`.

Supervisor может записать:

1. **Зарегистрированного студента**
   - выбирается из активных назначений `student ↔ psychologist`;
   - запись идёт по `student_id`;
   - требуется активный `TherapyEngagement`.

2. **Незарегистрированного walk-in клиента**
   - создаётся карточка `unregistered_student_cards`;
   - запись идёт по `unregistered_student_card_id`;
   - карточка хранит минимальные ПДн и факт очного согласия;
   - engagement не требуется, потому что аккаунта ещё нет.

3. **Новый полноценный аккаунт студента**
   - создаётся через `POST /api/supervisor/students`;
   - генерируется временный пароль;
   - в одной транзакции создаются `User`, `UserRole(student)`, `ConsentRecord[]`, optional active `TherapyEngagement`, `AuditLog`;
   - если указан `psychologist_id`, студент сразу доступен для записи к этому психологу;
   - временный пароль возвращается авторизованному caller и отправляется письмом; пароль и ПДн не логируются.

Карточки незарегистрированных студентов:

- таблица `unregistered_student_cards`;
- `appointments.client_id` теперь nullable;
- `appointments.unregistered_student_card_id` указывает на карточку;
- CHECK constraint гарантирует ровно один субъект записи: `client_id` или `unregistered_student_card_id`;
- при регистрации/создании аккаунта карточки могут привязаться к пользователю по `normalized_email`;
- уже привязанные к другому user карточки не перепривязываются;
- archived карточки не используются для новых ручных записей, но могут быть исторически привязаны.

### 4. Групповые занятия

Групповое занятие — отдельная сущность `group_sessions`, не group chat.

Реализовано:

- supervisor создаёт/редактирует групповое занятие;
- указывает тип встречи, ведущего психолога, дату/время, формат, capacity, description;
- включает/выключает запись через `booking_enabled`;
- студент записывается сам, если:
  - занятие `scheduled`;
  - `booking_enabled=true`;
  - есть свободные места;
  - студент активен и имеет нужные согласия;
- подтверждение психолога для групповых занятий не требуется;
- waitlist не реализован;
- group chat не реализован.

Статусы групп:

- `scheduled` — доступно/запланировано;
- `completed` — началось или прошло;
- `cancelled` — отменено.

Lazy-completion:
- при чтении списков и при попытке записи backend переводит начавшиеся/прошедшие `scheduled` в `completed`;
- одновременно выставляет `booking_enabled=false`;
- уже `cancelled` и `completed` не трогает;
- student видит только `scheduled`;
- supervisor и psychologist видят `scheduled`, `completed`, `cancelled`;
- supervisor список сортируется по `created_at DESC`, новые сверху.

### 5. Кабинет студента

`/student/calendar` больше не является pure mock:

- получает bookable individual meeting types через API;
- студент выбирает тип встречи;
- формат выбирается автоматически, если у типа только один формат;
- доступные слоты приходят с backend с учётом расписания, перерывов, исключений, занятых индивидуальных записей и групповых занятий психолога;
- запись создаётся как `pending_confirmation`;
- upcoming/history показывают реальные записи и `meeting_type_name`.

`/student/group-sessions`:
- показывает открытые групповые занятия;
- позволяет записаться и отменить участие по правилам backend.

`/student/settings`:
- работает через `GET/PATCH /api/auth/profile`;
- редактируются только `full_name` и `phone`;
- email и role read-only;
- телефон форматируется общей маской.

### 6. Кабинет психолога

Реализованы:

- список студентов психолога;
- карточка студента;
- чат;
- список индивидуальных записей;
- подтверждение/отклонение индивидуальной записи;
- групповые занятия психолога;
- календарный обзор записей;
- ближайшие встречи на главной;
- вкладка «Моё расписание».

Список индивидуальных записей психолога:
- сортируется по `created_at DESC`, новые заявки сверху;
- поддерживает пагинацию;
- для walk-in записи показывает ФИО из `unregistered_student_card`;
- показывает тип встречи, формат, дату, время и статус.

Календарь психолога:
- грузит индивидуальные записи отдельным диапазонным запросом, не из пагинированного списка;
- включает групповые занятия;
- показывает точки/маркеры по статусам;
- имеет легенду под календарём;
- компактный layout: сетка слева, выбранный день справа на desktop; одна колонка на mobile.

«Моё расписание»:
- группирует рабочие окна и перерывы по дням недели;
- дедуплицирует одинаковые окна/перерывы только на уровне отображения;
- показывает read-only разовые изменения психолога через `GET /api/psychologist/schedule-exceptions`.

### 7. Кабинет супервизора

Реализованы разделы:

- `/supervisor/engagements` — назначения студент ↔ психолог;
- `/supervisor/meeting-types` — типы встреч;
- `/supervisor/schedule` — рабочие окна, перерывы, разовые изменения, edit/restore/extend серий;
- `/supervisor/booking` — ручная запись registered / walk-in / new account;
- `/supervisor/group-sessions` — групповые занятия.

Важные UI-решения:

- в расписании supervisor больше нет поля «Период»;
- расписание не привязано к типу встречи;
- время выбирается через shared `TimePicker`;
- DateTime для групповых занятий выбирается через shared `DateTimeInput`;
- телефоны в формах используют общую маску как в профиле/админке.

---

## Основные backend endpoints

### Student appointments

| Метод | URL | Описание |
|---|---|---|
| GET | `/api/appointments/meeting-types` | Bookable individual meeting types |
| GET | `/api/appointments/slots` | Доступные слоты назначенного психолога |
| GET | `/api/appointments/my` | Свои записи |
| POST | `/api/appointments` | Создать индивидуальную запись |
| PATCH | `/api/appointments/{uuid}/cancel` | Отменить свою запись |
| GET | `/api/group-sessions` | Открытые групповые занятия |
| POST | `/api/group-sessions/{uuid}/register` | Записаться на групповое занятие |
| DELETE | `/api/group-sessions/{uuid}/register` | Отменить участие |

### Psychologist

| Метод | URL | Описание |
|---|---|---|
| GET | `/api/psychologist/appointments` | Индивидуальные записи психолога |
| PATCH | `/api/psychologist/appointments/{uuid}/confirm` | Подтвердить запись |
| PATCH | `/api/psychologist/appointments/{uuid}/decline` | Отклонить запись |
| GET | `/api/psychologist/schedule` | Read-only расписание |
| GET | `/api/psychologist/schedule-exceptions` | Read-only разовые изменения |
| GET | `/api/psychologist/group-sessions` | Групповые занятия психолога |

### Supervisor appointments and schedule

| Метод | URL | Описание |
|---|---|---|
| GET/POST/PATCH | `/api/supervisor/meeting-types` | Управление типами встреч |
| GET | `/api/supervisor/slots` | Слоты произвольного психолога для ручной записи |
| POST/PATCH | `/api/supervisor/schedules` / `/api/supervisor/schedules/{series_id}` | Создание/редактирование серии расписания |
| GET/POST | `/api/supervisor/schedule-exceptions` | Список/создание разовых изменений |
| POST | `/api/supervisor/appointments` | Ручная запись |
| GET/POST/PATCH/POST archive | `/api/supervisor/unregistered-student-cards` | Карточки walk-in клиентов |
| GET/POST/PATCH | `/api/supervisor/group-sessions` | Управление групповыми занятиями |
| PATCH | `/api/supervisor/group-sessions/{uuid}/booking` | Открыть/закрыть запись |

### Supervisor students

| Метод | URL | Описание |
|---|---|---|
| GET | `/api/supervisor/students` | Список студентов |
| POST | `/api/supervisor/students` | Создать полноценный аккаунт студента |
| GET | `/api/supervisor/psychologists` | Список психологов |
| GET/POST/PATCH | `/api/supervisor/engagements` | Назначения/переназначения/закрытия |

### Auth profile

| Метод | URL | Описание |
|---|---|---|
| GET | `/api/auth/profile` | Self-profile текущего пользователя |
| PATCH | `/api/auth/profile` | Обновить `full_name` и `phone` |

---

## Основные frontend файлы

### Shared UI

- `components/UI/TimePicker/TimePicker.jsx` — `HH:MM`, минуты `00..59`, без native `type=time`.
- `components/UI/DateTimeInput/DateTimeInput.jsx` — `DateInput + TimePicker`, value `YYYY-MM-DDTHH:MM`.
- `utils/datetime.js` — конвертация local UI value ↔ Moscow ISO для DateTimeInput-сценариев.

### Student

- `pages/student/Calendar/CalendarPage.jsx` — индивидуальная запись на реальные слоты.
- `features/appointments/hooks/useAvailableSlots.js` — слоты с `meeting_type_id` и `modality`.
- `features/appointments/hooks/useMyAppointments.js` — список своих записей.
- `pages/student/GroupSessions/GroupSessionsPage.jsx` — запись на групповые занятия.
- `pages/student/Settings/SettingsPage.jsx` — self-profile.

### Psychologist

- `pages/psychologist/Appointments/AppointmentsPage.jsx` — вкладки индивидуальные / групповые / расписание.
- `pages/psychologist/Appointments/PsychologistCalendar.jsx` — календарный обзор.
- `pages/psychologist/Appointments/ScheduleTab.jsx` — read-only расписание и разовые изменения.
- `features/psychologist/hooks/usePsychologistAppointments.js` — пагинированный список записей.
- `features/psychologist/hooks/usePsychologistCalendarRange.js` — диапазон календаря.
- `features/psychologist/calendar/calendarMappers.js` — группировка/форматирование событий.

### Supervisor

- `pages/supervisor/MeetingTypesPage.jsx` — типы встреч.
- `pages/supervisor/SchedulePage.jsx` — расписание v3, breaks, exceptions, edit/restore/extend.
- `pages/supervisor/BookingPage.jsx` — ручная запись.
- `pages/supervisor/booking/NewStudentModal.jsx` — создание аккаунта студента.
- `pages/supervisor/booking/UnregisteredCardModal.jsx` — карточка walk-in клиента.
- `pages/supervisor/booking/UnregisteredCardPicker.jsx` — поиск карточек.
- `pages/supervisor/GroupSessionsPage.jsx` — групповые занятия.

---

## Архитектурные решения

**Расписание ≠ слоты.**<br>
Расписание хранит рабочую доступность психолога. Слоты вычисляются на лету по выбранному `MeetingType.duration_minutes + buffer_minutes`.

**Тип встречи не привязан к рабочему окну.**<br>
Supervisor задаёт, когда психолог работает. Студент или supervisor выбирает тип встречи при записи.

**Перерывы — отдельная сущность.**<br>
Обед и похожие регулярные блокировки хранятся в `schedule_breaks`, а не как часть длительности приёма.

**Разовые изменения — отдельная логика.**<br>
`schedule_exceptions` покрывают выходной, блокировку части дня и дополнительное окно. Психолог видит их read-only.

**Групповые занятия не смешаны с group chat.**<br>
Групповое занятие — запись/событие. Чат группы намеренно не реализован.

**Walk-in карточка сохраняется.**<br>
Карточка нужна для человека без аккаунта, который пришёл лично. Если он потом зарегистрируется или staff создаст аккаунт с тем же email, карточка может привязаться к пользователю.

**Создание аккаунта студента staff'ом — не legal basis.**<br>
Для студента используется `consent_records`: staff фиксирует личное согласие, полученное очно. `user_legal_basis_records` остаётся только для staff-ролей.

**Supervisor booking создаёт pending confirmation.**<br>
Даже если запись создал supervisor, индивидуальная встреча всё равно требует подтверждения психолога.

**Групповые занятия закрываются лениво.**<br>
Нет фонового scheduler в FastAPI. При чтении списков и попытке регистрации backend переводит прошедшие `scheduled` в `completed`.

---

## Проверки, которые запускались в ходе блока

По отчётам Claude Code в ходе этапов:

- backend compileall проходил после backend-этапов;
- `pytest tests/` проходил после крупных backend-этапов;
- `tests/integration/test_appointments.py` расширен до 100+ сценариев;
- добавлены тесты для `unregistered_student_cards`, staff-created students, auth profile;
- frontend `npm run lint -- --max-warnings 0` проходил после UI-этапов;
- frontend `CI=true npm run build` проходил после UI-этапов;
- frontend Jest вырос до 100+ тестов, включая TimePicker, booking helpers, calendar mappers.

Точные актуальные числа нужно проверять свежим запуском:

```powershell
cd mindcare_api
.venv\Scripts\python.exe -m compileall app scripts -q
.venv\Scripts\python.exe -m pytest tests/ -q

cd ..\mindcare_web
npm run lint -- --max-warnings 0
$env:CI="true"; npm run build
npm test -- --watchAll=false
```

---

## Известные ограничения и бэклог

- `docs/DEVELOPER_GUIDE.md` и `docs/APPOINTMENTS_SLOTS_PLAN.md` специально удалены и не должны восстанавливаться автоматически.
- Waitlist для групповых занятий не реализован.
- Group chat не реализован.
- Видеоконсультации и внешние календарные интеграции не реализованы.
- Отдельного shared `SlotPicker` пока нет; сетки свободных appointment slots остаются feature-specific.
- `TimeSelect` оставлен deprecated для обратной совместимости; новые формы должны использовать `TimePicker`.
- Lazy-completion групп не является background job; статус обновляется при чтении/регистрации.
- Существующие `appointments` не переносятся автоматически при редактировании расписания.
- Дедупликация одинаковых окон в расписании психолога сделана на уровне отображения, а не как cleanup БД.
- Карточки walk-in не объединяются автоматически; несколько карточек с одним email могут привязаться к одному user.
- Post-commit привязка карточек и welcome/system notifications soft-fail: сбой не откатывает уже созданный аккаунт/запись.
- Полный browser E2E ещё не автоматизирован; важные сценарии требуют ручного smoke.

---

## Ручной smoke после изменений в этом модуле

Минимальный набор:

1. Supervisor:
   - создать тип встречи с duration/buffer;
   - создать расписание на несколько дней с перерывом;
   - добавить разовое изменение;
   - отредактировать серию расписания;
   - продлить/деактивировать/восстановить серию.

2. Student:
   - выбрать тип встречи, формат, дату;
   - записаться на свободный слот;
   - увидеть `pending_confirmation`;
   - отменить pending запись и убедиться, что она исчезла из списков.

3. Psychologist:
   - увидеть новую запись;
   - подтвердить/отклонить;
   - увидеть календарь с легендой;
   - увидеть read-only расписание и разовые изменения.

4. Supervisor booking:
   - записать зарегистрированного студента;
   - создать walk-in карточку и записать её;
   - создать новый аккаунт студента и записать его;
   - убедиться, что занятый слот исчезает.

5. Group sessions:
   - создать групповое занятие с description;
   - открыть запись;
   - записать студента;
   - проверить capacity/double booking;
   - проверить, что начавшееся/прошедшее занятие становится `completed` и больше не бронируется.

---

## Что НЕ трогать без отдельной задачи

- Не добавлять group chat внутри текущего group session flow.
- Не запускать миграции из FastAPI lifespan.
- Не использовать `Base.metadata.create_all()`.
- Не переводить backend на async.
- Не делать физическое удаление appointments/schedule entities без отдельного решения.
- Не логировать ПДн, temporary password, chat/session content.
- Не исправлять старые handoff-файлы как будто они актуальная документация — это исторические snapshots.

---

## Промпты для следующих чатов

### Стратегический / аналитический чат

```text
Прочитай:
- CLAUDE.md
- docs/HANDOFFS/2026-06-27-appointments-scheduling-complete.md
- docs/COMPLIANCE.md
- docs/QUALITY_CHECKLIST.md
- mindcare_web/ARCHITECTURE.md

Проект: MindCare — платформа психологической службы ДонГУ.
Большой блок Appointments/Schedule v3/Group sessions/Supervisor booking реализован.

Ключевая текущая модель:
- расписание психолога = рабочие окна + перерывы + разовые изменения;
- тип встречи выбирается при записи и задаёт duration/buffer;
- индивидуальная запись требует подтверждения психолога;
- групповые занятия не требуют подтверждения и закрываются lazy в completed;
- supervisor может записать registered student, walk-in карточку или создать новый student account;
- карточки walk-in могут привязаться к аккаунту по normalized_email.

Нужно предложить следующий приоритет развития проекта: стабилизация appointments, UX-polish, E2E/smoke automation, tests/admin tests, reports или другой модуль.
Код не меняй без явного согласия.
```

### Чат для работы с кодом (Claude Code)

```text
Это implementation-чат проекта MindCare.

Прочитай:
- CLAUDE.md
- docs/HANDOFFS/2026-06-27-appointments-scheduling-complete.md
- docs/COMPLIANCE.md
- docs/QUALITY_CHECKLIST.md
- mindcare_web/ARCHITECTURE.md

Соблюдай правила:
- backend слои routes -> service -> storage -> models;
- sync FastAPI + sync SQLAlchemy;
- миграции только Alembic;
- не запускать миграции из lifespan;
- не использовать Base.metadata.create_all();
- роли и доступ проверять на backend;
- ПДн, temporary passwords, chat/session content не логировать;
- сначала тесты для backend-логики, затем реализация;
- не делать git commit.

Актуальная следующая архитектурная задача: multi-role user model (см.
`docs/DECISIONS.md` ADR-018). Пользователь может иметь несколько активных ролей
в `user_roles`; auth/frontend должны использовать `roles[]`, а `role` остаётся
только legacy/default/effective convenience. Не заменять весь набор ролей одним
значением и не давать `supervisor` доступ в `/admin/*` без membership-роли `admin`.

Текущий appointment/schedule блок уже реализован:
- schedule v3: рабочие окна без привязки к типу встречи;
- TimePicker/DateTimeInput shared UI;
- supervisor booking: registered / walk-in card / new student account;
- group sessions: scheduled/completed/cancelled, lazy-completion;
- psychologist calendar/schedule/exceptions;
- student calendar and group sessions on real API.

Жди конкретную задачу. Перед изменениями кратко объясняй:
- какие файлы будешь менять;
- почему именно их;
- какие проверки запустишь после реализации.

Не исправляй backlog-задачи по пути.
Не восстанавливай docs/DEVELOPER_GUIDE.md и docs/APPOINTMENTS_SLOTS_PLAN.md.
```

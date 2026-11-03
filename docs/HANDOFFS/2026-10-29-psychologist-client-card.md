# Handoff — карточка клиента у психолога: тесты с ответами, встречи с итогами, заметки

**Дата:** 2026-10-29 (проверки — 2026-11-02). **Ветка:** `mindcare_alex`.
**Решения:** ADR-016 «Дополнение 2026-10-29», ADR-035 (`docs/DECISIONS.md`).
**Миграций нет** (статусы встреч — VARCHAR без CHECK; у заметок уже есть
`version`/`updated_at`). REGISTRY 135 → **141** (AUDIT_LOG 128 → 134).
Коммит не выполнялся.

## 1. Что сделано

Карточка `/psychologist/students/:id` в прежнем стиле и сетке:

- **Результаты психодиагностики:** все прохождения с «Показать ещё», раскрытие
  результата и «Показать ответы» с медиа; «Назначение тестов» убрано (решение —
  не реализовывать).
- **Встречи с клиентом:** предстоящие и история (keyset), ручной итог
  «Состоялась»/«Неявка» прошедшей подтверждённой встречи. Та же отметка — в
  «Записях» (`/psychologist/appointments`). В списке клиентов «Расписание» →
  ссылка «Встречи с клиентом» (`#client-meetings`).
- **Заметки:** существующий `session_notes`; создание (в т.ч. «Заметка» у
  конкретной встречи любой страницы), список, правка на месте с версией.
- Быстрые действия «Встречи с клиентом» / «Заметки» прокручивают к разделу и
  переводят фокус на заголовок; в «Что появится позже» — только «Запрос
  супервизии».

## 2. API-контракты

Все новые и изменённые эндпоинты карточки: `require_role("psychologist")`
(результаты — `supervisor`/`psychologist`), impersonation → 403 без события,
`Cache-Control: no-store, private` на любом ответе (`app/core/no_store_route.py`,
422 без эха значений). «Строгая область» = `status='active' AND ended_at IS NULL`
+ клиент `deleted_at IS NULL AND is_active IS TRUE`, роли клиента не проверяются
(`app/psychologist/client_scope.lock_client_scope`, `FOR SHARE OF
therapy_engagements, users` на всё чтение).

### Результаты (`app/tests/routes_staff.py`)

| Метод и путь | Кто | Ответ |
|---|---|---|
| `GET /api/staff/test-results?student_uuid&page&size≤100` | psychologist (область) / supervisor («чистый» активный студент) | `{items:[{uuid, test_title, submitted_at}], total, page, size}`, `submitted_at DESC, id DESC` |
| `GET /api/staff/test-results/{uuid}` | те же | `ResultRead` (сохранённые баллы, `recommendations`, шкалы `ORDER BY id`) |
| `GET /api/staff/test-results/{uuid}/answers` | только psychologist | `{result_uuid, test_title, submitted_at, order:"test_order", items:[{position, question_text, question_type, answered, media[], options:[{option_text, media[]}], scale_value, scale_min, scale_max, free_text}]}` |

- Отказ психологу (нет результата / область) — **404** `{"detail":"Результаты клиента недоступны"}`
  + `test_result_read_failed` (было 403). Supervisor: не найден / не «чистый»
  студент — 404 без события; ответы — 403. Admin — 403.
- `test_title` — актуальное название (snapshot нет); баллы, интерпретации и
  ответы — сохранённые, без пересчёта; медиа — публичные `/media/...` те же, что
  при прохождении; медиа невыбранных вариантов не отдаются.

### Встречи (`app/appointments/routes_psychologist.py`)

| Метод и путь | Ответ |
|---|---|
| `PATCH /api/psychologist/appointments/{uuid}/outcome` `{outcome: "completed"\|"no_show"}` | 200 `{uuid, status, changed}`; 404 нет встречи; 403 чужая; 409 `outcome_conflict` / `invalid_status` / `not_ended`; 503 сбой аудита |
| `GET /api/psychologist/clients/{uuid}/appointments?view=upcoming\|history&before&size≤50` | `{items:[{uuid, starts_at, ends_at, status, meeting_type_name, modality, via_card, can_mark_outcome}], has_more, next_cursor}`; 404 нет области; 422 битый курсор |

- `upcoming` — pending/confirmed, ещё не закончившиеся (`starts_at ASC`);
  `history` — остальное (`DESC`). Выборка — психолог И клиент (прямые записи +
  карточка с `linked_user_id = клиент`), без групповых занятий.
- `AppointmentDetailRead` (общий список «Записи») получил `can_mark_outcome`.
- confirm / decline / student cancel / outcome — строка встречи `FOR NO KEY
  UPDATE`; decline confirmed-встречи после окончания → **409**.

### Заметки (`app/session_notes/routes_psych.py`, `routes.py`)

| Метод и путь | Тело | Ответ |
|---|---|---|
| `GET /api/psychologist/clients/{uuid}/notes?before&size≤50` | — | `{items:[{uuid, note_type, content, version, created_at, updated_at, appointment:{uuid, starts_at}\|null}], has_more, next_cursor}` |
| `POST /api/psychologist/clients/{uuid}/notes` | `{content 1..50000, note_type?, appointment_uuid?}` (extra=forbid) | 201 заметка; 404 нет области; 422 чужая/удалённая встреча |
| `PATCH /api/psychologist/clients/{uuid}/notes/{note_uuid}` | `{content?, note_type?, version}` | 200 заметка + `changed`; 404 нет области/заметки/противоречивая; 409 `note_version_conflict` |
| `POST /api/session-notes` (generic) | прежнее | + 422 «Недопустимая привязка заметки» при чужих/несогласованных связях |
| `PATCH /api/session-notes/{id}` (generic) | прежнее + `version?` | + 409 при устаревшем `version`; explicit `is_shared_with_client:null` → 422 |

- Видна/правится только своя заметка, у которой **каждая** заполненная связь —
  этого психолога и этого клиента (SQL до расшифровки); противоречивые старые
  записи не выдаются и не исправляются.
- Оба PATCH — один `storage._apply_note_update`: CAS при `version`, `version+1`
  при любом реальном изменении (в т.ч. только `note_type`), no-op — без версии,
  `updated_at` и события. **Generic без `version` — сохранённый last-write-wins:
  блокировка сериализует записи, но от потери изменений не защищает.**
- Supervisor (content поштучно под `session_note_content_read`) и admin
  (metadata-only) — без изменений. Удаления и публикации клиенту нет.

## 3. Audit impact

| Событие | Контракт | Когда |
|---|---|---|
| `test_result_content_read` | **INDEPENDENT/RAISE** (было SOFT), {supervisor, psychologist}, target `test_result`, metadata `{}` | деталь и ответы; сбой → 503 без содержимого |
| `test_result_read_failed` | новое, failure {psychologist}: `access_denied` | любой отказ области психолога |
| `appointment_completed` / `appointment_no_show` | новые, ATOMIC/RAISE {psychologist}, target `appointment` | реальный переход, тот же commit |
| `appointment_outcome_failed` | новое, failure: `access_denied`, `invalid_status`, `outcome_conflict`, `not_ended` | доказанный pre-commit отказ |
| `session_note_create_failed` | новое, failure: `access_denied`, `link_mismatch` | отказ привязки / области |
| `session_note_update_failed` | новое, failure: `access_denied`, `version_conflict` | отказ правки (generic — только `version_conflict`) |
| `session_note_created` / `_updated` | без изменений, ATOMIC; `_updated` — только при реальном изменении | |

- Список результатов, встречи клиента и чтение своих заметок событий не пишут.
- CHANGE_REGISTRY не расширялся (обоснование — ADR-035 п. 5).
- Ответы, баллы, текст заметок, URL медиа, ciphertext в журналы, логи и ответы
  об ошибках не попадают (проверено тестами).

## 4. Проверки

- **Backend:** `..\test.ps1` (изолированная БД) — **4768 passed, 80 skipped,
  0 failed**. Новые/расширенные:
  - `test_staff_test_results_api.py`, `test_staff_test_results_concurrency.py`,
    `test_staff_test_results_unit.py`;
  - `test_appointment_outcome_api.py`, `test_appointment_outcome_concurrency.py`;
  - `test_client_notes_api.py`, `test_session_notes_versioning.py`,
    `test_session_notes_audit_unit.py`;
  - `test_client_card_registry_unit.py`, закреплённые счётчики REGISTRY (11 файлов).
- **Frontend:** `npm test` — **2380 passed (162 suites)**; `npm run lint` чисто;
  `npm run build` успешно. Новые: `useStaffTestResults`, `useStaffResultView`,
  `StudentTestResults`, `useClientMeetings`, `ClientMeetings`,
  `AppointmentsPage`, `useClientNotes`, `ClientNotes`; обновлены тесты карточки,
  списка клиентов, `auditLabels`.
- Браузерный smoke **не выполнен** (нет демо-аккаунта психолога с клиентом в dev-БД).

## 5. Оставшиеся ограничения

См. `docs/BACKLOG.md` → «Карточка клиента у психолога — продолжение (после
ADR-035)»: групповые занятия и посещаемость, назначение тестов, snapshot
названия теста, противоречивые старые заметки, generic API заметок (int id,
last-write-wins без `version`), индексы, N+1 «Записей», дрейф подписей журнала.

## 6. Исправления после ревью (2026-11-02, только frontend заметок)

Backend, схема, EventSpec и CHANGE_REGISTRY не менялись; события
`session_note_created`/`session_note_updated` и их транзакционные границы прежние.

1. **Черновик при конфликте 409 на догруженной странице.** Раньше правка жила
   в строке списка, а `reload` после 409 заменял список первой страницей —
   редактор вместе с текстом исчезал. Теперь черновики правок — в
   `useClientNotes` (`drafts`, ключ — uuid заметки, не строка списка) и
   переживают перезагрузку списка. После 409 хук постранично ищет актуальную
   версию заметки (отдельного GET по uuid нет; предел 50 страниц) и кладёт её в
   `draft.current`, `baseVersion` обновляется. В `ClientNotes` черновик заметки,
   которой нет в загруженной части списка, показан в блоке «Несохранённые
   правки» с текстом пользователя и «Актуальной версией заметки»; повторное
   «Сохранить» осознанно заменяет актуальную версию правкой (отправляется новая
   `version`). Если актуальную версию загрузить не удалось — кнопка «Загрузить
   актуальную версию» (`refreshDraft`); если заметка недоступна — текст остаётся
   для копирования, «Отмена» убирает черновик.
2. **Завершение запроса после размонтирования / смены клиента.** Раньше хук
   сравнивал uuid клиента на момент ответа, поэтому после смены `key` карточки
   (размонтирование) старый успех `create` считался актуальным и вызывал
   `onClearLinkedMeeting`, снимая привязку встречи нового клиента. Теперь у
   хука «поколение контекста» (`ctx.gen`): оно растёт при смене `studentUuid` и
   при размонтировании; запрос запоминает его на старте, и ответ с иным
   поколением — `stale`: не меняет форму, ошибки и блокировки, не
   перечитывает список, компонент не вызывает callbacks. Это работает и для
   A → B → A (старый запрос A не относится к новому A). Дополнительно страница
   сбрасывает `noteMeeting` при смене клиента и снимает привязку только по
   `clientUuid` вызвавшей формы (`clearNoteMeeting`).

Проверки: Jest — `useClientNotes` (409 у заметки со второй страницы, повтор
сохранения поверх актуальной версии, сбой загрузки актуальной версии,
unmount, A → B → A: успех/ошибка старого запроса), `ClientNotes`
(409 на второй странице с восстановлением, черновик переживает reload),
`PsychologistStudentCardPage` (реальная смена клиента через `key`:
A → B успех и ошибка, A → B → A). Мутационная проверка: при отключённой
защите от устаревших ответов падают 5 новых тестов. Полный Jest — 2388 passed
(162 suites), `npm run lint` чисто, `npm run build` успешно. **Браузерный smoke
не выполнялся.**

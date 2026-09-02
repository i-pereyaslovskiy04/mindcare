# Медиа-изображения в вопросах и вариантах ответов тестов

**Дата:** 2026-08-30
**Область:** backend (`mindcare_api/`) + frontend (`mindcare_web/`)
**Опирается на:** психодиагностику Этапов A–D
(`docs/MODULES/psychodiagnostics-spec-draft.md`), предпросмотр теста
(`2026-08-29-staff-student-role-admin-nav-dark-theme.md`), общий загрузчик
изображений `components/UI/ImageUpload` + модуль `app/media`.
**Миграция:** не требуется (таблицы уже существуют).

---

## 1. Зачем

ТЗ психодиагностики (`psychodiagnostics-spec-draft.md`, стр. 32, 206)
предусматривало «картиночные тесты» как отложенный этап: таблицы-связки
`question_media` / `option_media` были заведены в baseline-миграции
`af13ad7a133c`, но ни API, ни сервис, ни хранилище, ни фронт их не использовали —
тесты были полностью текстовыми. Эта работа связывает все четыре слоя, чтобы автор
мог прикрепить **изображение** к вопросу и к каждому варианту ответа, а студент
видел его при прохождении и в предпросмотре.

**Только изображения.** Audio/video отложены: `app/media` принимает лишь
JPEG/PNG/WebP, для них потребуется расширение `ALLOWED_MIME` и отдельный
фронт-компонент.

---

## 2. Модель данных (без миграции)

Обе таблицы уже были в схеме и в ORM (`app/db/models/diagnostics.py`):

- `question_media`: `question_id`, `media_id → media_files.id`, `media_role`
  (`'main'`), `display_order`, `caption`. Relationship `Question.media`
  (`cascade all, delete-orphan`).
- `option_media`: `option_id`, `media_id → media_files.id`, `media_role`
  (`'icon'`), `display_order`. **Колонки `caption` нет** — варианты декоративны.
  Relationship `Option.media` (`cascade all, delete-orphan`).

**MVP:** одно изображение на вопрос и опционально одно на вариант. Таблицы
поддерживают несколько через `display_order` — задел на будущее, UI даёт один слот
(совпадает с контрактом `ImageUpload`, у которого одно `value`).

Файл хранится в public static `/media/uploads/...` (`media_files.file_path`).
Изображение методики — не ПДн студента: шифрование не применяется, аудит не
расширяется (медиа входит в существующую мутацию дерева, покрытую
`test_created` / `test_updated`).

---

## 3. Backend (`app/tests/`)

### `schemas.py`
- `MediaRef` — вход: `media_uuid` (обяз.) + `caption` (для вопроса; у варианта
  игнорируется).
- `MediaOut` — выход: `uuid`, `url` (= `file_path`), `caption`.
- Поля `media: list[MediaRef]` в `QuestionCreate` / `OptionCreate`; поля
  `media: list[MediaOut]` в `QuestionRead` / `OptionRead` / `TakeQuestionRead` /
  `TakeOptionRead`.

### `storage.py`
- `resolve_media(uuid, db)` / `media_exists(uuid)` — резолв `media_files.uuid →
  id` только для активных файлов (`is_active`).
- `_replace_questions` — после вставки вопроса/варианта создаёт `QuestionMedia`
  (`role='main'`) / `OptionMedia` (`role='icon'`); вариант с медиа получает
  `db.flush()` ради `option.id`. Полная замена дерева снимает старые связки через
  cascade.
- `_question_to_dict` + новый `_option_to_dict` — читают связки в `media`
  (сортировка по `display_order`, url = `file_path`; осиротевшая связка без файла
  пропускается).
- `duplicate_test` — **копирует** связки медиа (тот же `media_id` — файл общий),
  иначе ревизия опубликованного теста через duplicate теряла бы картинки.

### `service.py`
- `_validate_questions` — если явно прикреплённый `media_uuid` не резолвится →
  **`ValueError` → HTTP 422** («изображение не найдено или недоступно»). Это
  сознательное отличие от `_sync_categories`/`_sync_tags`, которые несуществующие
  ссылки пропускают молча: картинку, которую автор явно приложил, терять нельзя.
- `_strip_take` — пробрасывает `media` вопроса и вариантов в проекцию для
  студента. Изображение отдаётся, но `value_score` (ключ теста) по-прежнему
  вырезается.

---

## 4. Frontend (`mindcare_web/`)

### `features/admin/tests/lib/testShape.js`
Форма вопроса/варианта хранит медиа как `{ media_uuid, url, caption }` (`url` —
для превью в билдере).
- `fromBackendQuestion` / `toBackendQuestion` / `toPreviewQuestions` — переносят
  медиа. На бэк уходит `{ media_uuid, caption }` (вопрос) / `{ media_uuid }`
  (вариант).
- **`snapshotQuestions` включает медиа-поля** — иначе dirty-tracking не отправил
  бы правку одной картинки/подписи у теста с результатами, и автор не увидел бы
  корректный 409 (правка «молча сохранилась» бы).
- Предпросмотр берёт `url` напрямую (резолв не нужен); `preview_score` про медиа
  ничего не знает — медиа не участвует в подсчёте.

### `features/admin/tests/components/QuestionBuilder.jsx` (+ `.module.css`)
- `ImageUpload` под текстом вопроса (+ поле «Подпись / альтернативный текст» →
  `caption`) и в каждой строке варианта.
- Переиспользованы `components/UI/ImageUpload` + `api/media.api` — новых
  загрузчиков нет.

### `features/tests/ui/QuestionRenderer.jsx` (+ `.module.css`)
- Изображение вопроса: `alt` = `caption` (если задан) либо `question_text`
  (содержательная картинка).
- Изображение варианта: декоративное — `alt=""` + `aria-hidden`, доступное имя
  даёт текст варианта (ГОСТ Р 52872-2019; у `option_media` нет `caption`).
- Тот же компонент обслуживает и прохождение, и предпросмотр.

---

## 5. Иммутабельность (важно)

Медиа лежит **внутри** дерева `questions`, поэтому `update_test` с изменённым
медиа у теста, по которому уже есть результаты, → тот же **409 TestHasResults** —
и это корректно: снапшот `test_results` / `student_answers` не фиксирует
изображение вопроса, ретроактивная подмена стимула изменила бы смысл прошлых
результатов. Штатный путь правки — `POST /api/admin/tests/{uuid}/duplicate`.

---

## 6. Доступ

Конструктор тестов (`/admin/tests/*` в `router.jsx`) — под
`RoleRoute roles={['admin']}`; `POST /api/media/upload` — `require_role("admin")`.
Согласовано: картинки прикрепляет только admin. (API `routes_admin.py` пускает и
supervisor, но чистый supervisor до `/admin/*` не доходит.)

> **Предсуществующий разрыв, вне этой работы:** `BannerSlidesPage` /
> `ServiceCardsPage` смонтированы и под `/supervisor/*`, но их `ImageUpload`
> бьёт в admin-only `/api/media/upload` — чистый supervisor не загрузит обложку.
> Отдельный пункт бэклога, тестов медиа не касается.

---

## 7. Тесты

- **Unit** (`tests/test_diagnostics_admin.py`): валидный/несуществующий
  `media_uuid` у вопроса и варианта → 422; без картинок медиатека не трогается.
- **Integration** (`tests/integration/test_diagnostics_admin_api.py`): round-trip
  create→read; take-проекция содержит медиа без `value_score`; неизвестный uuid →
  422; `duplicate` копирует связки. Фикстура `media_file` создаёт/чистит один
  `MediaFile`.
- **Правка** `tests/test_diagnostics_scoring.py::test_strip_take_...` — набор
  ключей варианта теперь включает `media`.
- Полный isolated suite зелёный по этому модулю.

### Побочная правка (ADR-024)
`tests/integration/test_legal_basis_api.py` — helper `_role_names_for_email`
исключает авто-роль `student`. Эти тесты (`TestMultiRoleCreate`) сверяют staff-
роли, для которых пишется `user_legal_basis_records`; после ADR-024 staff
получает `student` автоматически без legal basis, и он засорял проверки набора
ролей. Это устаревание тестов от ADR-024, а не дефект API; обнаружено при полном
прогоне suite в рамках этой работы.

---

## 8. Отложено (осознанно)

Часть из этого закрыта следующим блоком (см. §9). Остаётся отложенным:
- Подпись (`caption`) для изображений вариантов (нет колонки в `option_media`;
  осознанно — варианты декоративны, `alt=""`).
- Длительность audio/video (`duration_seconds`) — NULL, чтобы не тянуть ffprobe/
  mutagen; плеер показывает её сам.
- PDF-экспорт результата (нужен reportlab + endpoint + audit); сделан только CSV.
- Серверная фиксация попытки для тайм-лимита (сделан клиентский таймер).
- `custom` scoring (нет спецификации); Этапы E/F (доступ к результатам, модерация).

---

# Блок 2 (2026-08-30): отложенные функции — медиа-мелочи + audio/video + функции тестов

Реализовано тремя фазами поверх Блока 1. Решения пользователя: тайм-лимит —
клиентский; scoring — только `weighted`; caption вариантов не добавляем; audio/
video без duration.

## 9.1. Несколько изображений на вопрос/вариант
Бэкенд уже принимал `list[MediaRef]` — правки только на фронте:
`QuestionBuilder.jsx` (`MediaList` — add/remove по массиву), `QuestionRenderer.jsx`
(`media.map`), `testShape.js` (уже списочный).

## 9.2. Upload-доступ supervisor + audit `media_uploaded`
- `app/media/routes.py` — `POST /api/media/upload` расширен до
  `require_role("admin","supervisor")` (закрыт разрыв на `/supervisor/*` CMS).
- Новый EventSpec **`media_uploaded`** (`app/audit/registry.py`): actor
  `{admin,supervisor}`, target `media_file`, metadata только
  `file_type`/`mime_type`/`file_size` (без имени файла). Пишется в
  `media.service.upload_image`/`upload_av` (INDEPENDENT/SOFT). `admin_service.py`
  `_METADATA_DTO_POLICY` расширен ключом `file_type`. Счётчик REGISTRY: 104 → 105
  (обновлены `test_audit_registry.py`, `test_audit_admin_options_unit.py`).

## 9.3. weighted scoring
- `scoring.py` — вес вопроса `config["weight"]` (int ≥ 1); `_apply_weight`
  масштабирует балл И границы (`score_bounds`) синхронно. `schemas.ScoringMethod`
  += `weighted` (колонка `tests.scoring` — свободный VARCHAR, миграции нет;
  прежний комментарий про «enum БД» был неверен, исправлен).
- `service._validate_questions` валидирует `weight`. Фронт: `TestFormPage`
  (опция scoring), `QuestionBuilder` (поле «Вес» при `weighted`).

## 9.4. CSV-экспорт результата (клиентский)
`ResultDetailPage.jsx` — кнопка «Экспорт CSV», сборка из `result` + `saveBlobToDisk`
(`api/client.js`). Без бэкенда/зависимостей. `free_text` не включается (его нет в
`result`).

## 9.5. Тайм-лимит — клиентский таймер
`TestTakePage.jsx` — countdown (`time_limit_min` уже в `TestTakeRead`) + авто-submit
по 0. Добавлен флаг `SubmitIn.timed_out` (без миграции): при таймауте
`_validate_answers` пропускает проверку обязательности (пропуски → 0), иначе
частичные ответы терялись бы на 422. Флаг клиентский, не защита от обмана.

## 9.6. Случайный порядок вопросов/вариантов (Фаза 2, миграция)
- Миграция `d9f2a1c7b3e4` — `tests.shuffle_questions` / `tests.shuffle_options`
  (BOOLEAN, default false). ORM + схемы + storage (create/update/duplicate).
- `service._strip_take` перемешивает порядок (флаги теста) — презентационно;
  submit/scoring адресуют по id, порядок не важен. Фронт: 2 чекбокса в
  `TestFormPage`.

## 9.7. Audio/video в вопросах (Фаза 3, без системных зависимостей)
- `app/media/service.py::upload_av` — whitelist MIME (mp3/m4a/aac/ogg/mp4/webm),
  без Pillow, сохранение как есть, `file_type` audio/video, `duration=None`.
  `POST /api/media/upload/av` (admin+supervisor). `create_media_record` получил
  параметр `file_type`. Лимит `MEDIA_AV_MAX_SIZE_MB` (50), отдан в
  `/api/public/config` как `mediaAvMaxSizeMb`. `MediaUploadResponse.file_type`,
  `MediaOut.kind` (по `media_files.file_type`).
- Фронт: `components/UI/MediaUpload` (новый, `<audio>/<video controls>`),
  `media.api.uploadMedia`, `QuestionBuilder` (av на уровне вопроса),
  `QuestionRenderer` (рендер по `kind`).

## 9.8. Тесты Блока 2 (медиа/функции)
- Unit: weighted scoring + `weight`-валидация; shuffle `_strip_take`
  (monkeypatch); audit registry/options счётчики.
- Integration: `test_media_upload_api.py` (supervisor/admin 201, student 403,
  av video/audio, image↔av взаимное 415, audit `media_uploaded` без имени файла);
  `timed_out` submit; weighted preview-score; shuffle round-trip (проверяет
  миграцию); MediaOut.kind в take-проекции.

---

# Блок 3 (2026-08-31): Этап E — staff-доступ к результатам (ADR-016)

Доступ supervisor/psychologist к результатам тестов студентов с scope-check и
аудитом. Реализовано по шаблону `session_notes`. Решения: admin доступа НЕ имеет
(ADR-016); Этап F (модерация) — отдельный будущий блок.

## Модель доступа
- Список результатов студента → **metadata-only** (uuid/test_title/submitted_at,
  БЕЗ баллов), без audit — как metadata-list заметок.
- Деталь результата → полный `ResultRead` + audit **`test_result_content_read`**
  (INDEPENDENT/SOFT, как `session_note_content_read`).
- `supervisor` — любой студент; `psychologist` — только при active/past
  `TherapyEngagement`; `admin` — вне ролей роутера (нет доступа).

## Backend
- `app/tests/routes_staff.py` (новый) — `GET /api/staff/test-results?student_uuid=`
  (список) и `GET /api/staff/test-results/{uuid}` (деталь);
  `require_role("supervisor","psychologist")`; заголовок `X-Active-Role` →
  `service._resolve_staff_result_role` (валидация по membership, консервативный
  default psychologist). Смонтирован в `app/main.py`.
- `app/tests/service.py` — `list_student_results`/`get_staff_result` (scope-check,
  запись audit в detail), исключения `ResultAccessError` (403) / `ResultNotFound`
  (404).
- `app/tests/storage.py` — `resolve_student_id` (только **чистый** student —
  предикат «нет активной не-student роли», как `supervisor.storage.get_students`,
  чтобы staff не читал самотесты другого staff), `psychologist_has_engagement`,
  `find_results_for_student` (metadata), `get_result_with_owner`.
- `app/audit/registry.py` — событие `test_result_content_read`
  ({supervisor,psychologist}, target test_result, INDEPENDENT/SOFT, metadata
  пустая). **REGISTRY 105 → 106** (audit 98→99) — обновлены счётчики в ~10 тестах
  аудита + ожидаемый set + options integration; DTO-policy не менялась (нет
  metadata-ключей).
- Схема `StaffResultListItem` (`app/tests/schemas.py`).

## Frontend
- `src/api/tests.api.js` — `getStudentTestResults(studentUuid, activeRole)` и
  `getStaffTestResult(resultUuid, activeRole)` (заголовок `X-Active-Role`).
- `src/features/tests/ui/StudentTestResults.jsx` (новый) — список metadata →
  раскрытие грузит деталь (баллы/шкалы/интерпретации). Переиспользуется обоими
  кабинетами.
- Психолог: секция «Результаты психодиагностики» в
  `PsychologistStudentCardPage.jsx` (`student.student_uuid`, activeRole=psychologist).
- Супервизор: кнопка «Результаты» в строке `EngagementsPage.jsx` → модалка
  (`student.uuid`, activeRole=supervisor).

## Тесты (Этап E)
- Unit: `_resolve_staff_result_role` (single/multi/invalid/no-holder).
- Integration `test_staff_test_results_api.py`: supervisor любой → 200+audit;
  psychologist свой (engagement) → 200+audit(psychologist); psychologist чужой →
  403 без audit; admin → 403; список metadata-only; staff-на-staff uuid → 404.

---

# Блок 4 (2026-09-01): Этап F1 — moderation workflow тестов (backend + модерация)

`draft → in_review → published`, плюс `needs_changes` (ADR-016). Решения: видимость
студенту = `published AND is_active`; admin/supervisor выбирают статус при создании
(default `published`); psychologist заперт в draft — авторство psychologist
(`/psychologist/tests` UI, список черновиков) вынесено в **Этап F2** (не начато).

## Машина состояний
- `draft/needs_changes → in_review` — **только автор** (`tests.created_by ==
  actor_id`). `created_by IS NULL` (автор удалён, `ON DELETE SET NULL`) → перевод
  автором невозможен НИКОМУ, но admin/supervisor всё равно публикуют напрямую —
  тупика нет.
- `→ published` (из draft/in_review/needs_changes) — только admin/supervisor.
- `in_review → needs_changes` — только admin/supervisor, опц. `reason` (в audit
  НЕ попадает — свободный текст).
- `published` не имеет исходящих переходов status: «снять с публикации» —
  существующий `is_active` toggle, отдельный от machine состояний.
- Два разных исключения → разные HTTP-коды: **`TestTransitionError`** (перехода
  не существует в машине состояний, напр. `published→draft`) → **409**;
  **`TestTransitionForbidden`** (переход существует, но нет прав — не автор / не
  staff) → **403**, как `NotesAccessError` в session_notes.

## Backend
- Миграция `e1b4c8f2a6d9` (head, от `d9f2a1c7b3e4`) — `tests.status VARCHAR(20)
  NOT NULL DEFAULT 'draft'` + data-миграция `UPDATE tests SET status='published'
  WHERE is_active=true` (сохраняет текущую видимость). Известный эффект: ранее
  деактивированный опубликованный тест становится `draft` (был скрыт — остаётся
  скрыт; вернуть можно только publish).
- Видимость studenту — `Test.status=='published'` добавлен рядом с `is_active`
  в **трёх** местах: `find_active_tests`, `get_active_test_full` И отдельный
  запрос внутри `save_result` (он не переиспользует `get_active_test_full` —
  легко упустить при будущих правках).
- `app/tests/service.py`: `_TRANSITIONS` (таблица переходов), `_validate_transition`,
  `submit_for_review`/`publish_test`/`return_for_changes` (все через общий
  `_apply_transition`, один fetch `storage.get_status_and_author`).
- `app/tests/storage.py`: `get_status_and_author`, `set_status` (мутация + audit
  атомарно, как `update_test`/`delete_test`).
- Роуты: `POST /api/admin/tests/{uuid}/publish`, `/return` (`routes_admin.py`,
  admin+supervisor); **новый `app/tests/routes_psych.py`**
  (`require_role("psychologist")`) — `POST /api/psychologist/tests/{uuid}/
  submit-for-review` (владение — только защита service, роутер не проверяет
  авторство). `GET /api/admin/tests` — опциональный `?status=`; **по умолчанию
  ВСЕ статусы** (иначе тесты, переведённые data-миграцией в draft, пропали бы из
  вида админа).
- `status` НЕ добавлен в `TestUpdate` (generic PATCH) — переходы только через
  выделенные эндпоинты с audit; создание допускает только `draft|published`
  (`TestCreateStatus`), `in_review`/`needs_changes` — только результат перехода.
- Audit: `test_submitted_for_review` ({psychologist}), `test_published` /
  `test_returned_for_changes` ({admin,supervisor}); target `test` (существующий
  entity_type), ATOMIC/RAISE (как `test_created`), metadata пустая. **REGISTRY
  106 → 109** (audit 99→102) — обновлены счётчики в ~10 файлах.

## Frontend
- `TestsTable.jsx` — колонка «Модерация» (бейдж статуса) отдельно от «Видимость»
  (is_active); кнопки «Опубликовать» (draft/in_review/needs_changes) и «Вернуть на
  доработку» (только in_review), видны при переданных `onPublish`/`onReturn`.
- `AdminTestsPage.jsx` — фильтр по статусу (отдельно от фильтра видимости), диалог
  возврата с опциональной причиной (`returnTest`).
- `TestFormPage.jsx` — селектор статуса (draft/published) только при СОЗДАНИИ;
  при редактировании — read-only бейдж статуса (правка — через publish/return в
  таблице, не PATCH).
- Новые примитивы: иконки `check`/`undo` (`components/Icon/Icon.jsx`), tone
  `success` для icon-кнопок (`Button.jsx`+`.module.css`, зеркалит существующий
  `iconDanger`).

## Тесты
- Unit `test_diagnostics_admin.py`: `_validate_transition` — все легальные пары
  × роль/автор (parametrize), плюс параметризованный список нелегальных переходов
  (включая `published→*`, `draft→needs_changes`, no-op).
- Integration `test_test_moderation_api.py`: видимость draft/in_review/
  needs_changes скрыта от студента (список+деталь); admin и supervisor публикуют
  draft → видим студенту + audit; return in_review→needs_changes + audit (reason
  не в metadata); psychologist-автор шлёт свой draft/needs_changes на review +
  audit; psychologist чужой draft → 403 без audit и без мутации статуса; student
  на psychologist-роуте → 403; publish уже published → 409; return не-in_review →
  409; admin-список по умолчанию показывает все статусы (регрессия на data-миграцию).

---

# Блок 5 (2026-09-01): Этап F2 — авторство psychologist

Психолог создаёт/редактирует/удаляет ТОЛЬКО свои тесты (`tests.created_by`),
только пока `status IN (draft, needs_changes)`. Решения пользователя: медиа-
загрузка расширена на psychologist; delete — да (draft/needs_changes); duplicate
— НЕТ в F2.

## Ownership-модель
Отдельные psychologist-scoped storage/service функции — **не** расширение
`routes_admin.py` (которое даёт неограниченный доступ ко ВСЕМ тестам). Чужой
тест → **404** («чужого неотличимо от несуществующего», как `session_notes`), не
403. Свой, но не editable-статус (in_review/published) → **409**
(`TestNotEditable`).

## Backend
- `app/tests/storage.py`: `find_my_tests(author_id, page, size, search, status)`
  — серверная фильтрация по статусу (НЕ клиентская — иначе пагинация ломается
  при >20 тестах и активном фильтре).
- `app/tests/service.py`: `_own_editable_test` (ownership+status гейт, общий
  для update/delete); `create_my_test` — **принудительно** `status="draft"`,
  игнорируя присланный статус (защита от прямого вызова с `status=published`);
  `update_my_test`/`delete_my_test`/`get_my_test`/`list_my_tests`. Намеренно БЕЗ
  избыточной `has_results`-проверки в `update_my_test`: она недостижима для
  draft/needs_changes (результаты бывают только у published, а `published` не
  имеет исходящих переходов в state-machine F1) — единственный источник истины
  остался внутри `storage.update_test`.
- `app/tests/routes_psych.py` расширен до полного CRUD (`GET`/`POST ""`,
  `GET`/`PATCH`/`DELETE /{uuid}`) + **дублирует** `analyze`/`preview-score`
  (не трогая `routes_admin.py` — там router-level dependency нельзя ослабить
  по одному роуту; оба вызывают те же чистые `service.analyze_test`/
  `preview_score`, stateless, без ownership-семантики).
- **Audit**: `test_created`/`test_updated`/`test_deleted` роли
  `{admin,supervisor}` → `{admin,supervisor,psychologist}` (`test_duplicated` —
  НЕ расширяется, psychologist duplicate не использует). `media_uploaded` —
  аналогично. REGISTRY count не меняется (109) — только `allowed_actor_roles`.
- **Медиа-загрузка**: `app/media/routes.py` `_UPLOAD_ROLES` расширен на
  psychologist для `/api/media/upload` и `/upload/av`.

## Frontend
- **`TestFormPage.jsx` параметризован** через проп `config` (`api`, `backPath`,
  `showStatusSelect`, `showIsActiveToggle`, `showDuplicate`) — второй конкретный
  потребитель оправдал рефакторинг (не преждевременная абстракция). Admin
  остаётся дефолтом (`ADMIN_CONFIG`, без изменений поведения); новая тонкая
  `PsychologistTestFormPage.jsx` передаёт psychologist-config. `showDuplicate`
  заодно гейтит 409-баннер «есть результаты, создайте копию» — для psychologist
  эта ветка недостижима, при 409 просто текст ошибки.
- `useTestAnalysis`/`TestPreviewModal` принимают `analyzeFn`/`previewFn` (default
  — admin-функции; JS default-параметры срабатывают и при явном
  `undefined` из `config`).
- **`TestsTable.jsx`**: статус-бейдж теперь ВСЕГДА виден (раньше — только при
  `onPublish`/`onReturn`); новый `onSubmitForReview` (иконка `send`, для
  draft/needs_changes); новый `restrictEditToStatuses` — гейтит
  Edit/Delete-кнопки НА УРОВНЕ СПИСКА (не формы), поэтому generic
  409-обработка формы никогда не всплывает для psychologist в нормальном
  потоке. Переиспользован из `features/admin/tests/` в психолога — устоявшийся
  кросс-кабинетный паттерн (как `StudentTestResults`).
- Новый независимый `features/psychologist/hooks/useMyTests.js` (не обобщение
  `useAdminTests` — не задевать протестированный admin-путь ради ~40 строк).
- `pages/psychologist/Tests/{PsychologistTestsPage,PsychologistTestFormPage}.jsx`,
  nav-пункт «Тесты» в `PsychologistLayout.jsx`, роуты `/psychologist/tests`,
  `/new`, `/:uuid`.

## Тесты
Unit: `create_my_test` форсирует draft вне зависимости от входа;
`_own_editable_test` — все комбинации найден/не найден/чужой/статус.
Integration `test_psychologist_tests_api.py`: create→draft; edit/delete свой
draft → 200/204; edit/delete свой in_review/published → 409; edit/delete чужой
→ 404; список — только свои, все статусы; media upload (image+av) → 201; analyze/
preview-score → 200.

## Итог по Этапам E/F
Все три блока (E, F1, F2) реализованы и покрыты тестами. Отложенное:
`custom` scoring, `duration_seconds`, PDF-экспорт, серверный тайм-лимит, caption
вариантов, duplicate для psychologist.

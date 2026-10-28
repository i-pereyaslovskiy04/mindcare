# Handoff (2026-10-26): реальная библиотека в кабинетах и базовые задания психолога

Решение по заданиям — **ADR-033** (`docs/DECISIONS.md`). Миграция `eb1460dc4954`
(`down_revision = a7d3f1c8e5b2`), REGISTRY 123 → 131 (AUDIT_LOG 116 → 124).
Ветка `mindcare_alex`, изменения не закоммичены.

> **Перед запуском API на стенде:** `alembic upgrade head`. `init_db.check_migrations`
> не даёт API стартовать, пока БД не на head. Порядок: миграция → перезапуск API →
> выкладка фронтенда. Миграция к dev/рабочей БД в этой задаче НЕ применялась.

## 1. Что было

- `/student/materials` — встроенный массив `ARTICLES`, вымышленное «7 мин»,
  избранное в `useState` с обещанием «Сохраняйте важное в избранное»; материал не
  открывался.
- Публичная `/materials`: сортировка «Старые» переворачивала только загруженную
  часть, раздел «Тема» был пуст и в API не уходил.
- `/psychologist/materials` — отключённый пункт меню; в карточке клиента —
  заглушка «Материалы и тесты».
- `/student/tasks` — `INITIAL_TASKS`, вымышленный комментарий «Мария Ковалёва»,
  «До следующей сессии — 2 дня», локальное переключение `done`; бейдж меню `'2'`.

## 2. Этап 1 — библиотека (frontend-only)

- Общий слой `mindcare_web/src/features/materials/`:
  - `lib/normalizeArticle.js` — только реальные поля (обложка, категория, темы,
    дата по Москве), без времени чтения;
  - `hooks/useMaterialsLibrary.js` (заменил `hooks/useMaterials.js`) — серверные
    поиск, один `category_id`, постраничная выдача, `refetch`, отброс устаревших
    ответов; сортировки и тем нет (API их не принимает). Запрос хранится после
    trim; повтор того же запроса или той же категории — no-op (раньше список
    очищался без новой загрузки, например при «сонx» → «сон» внутри debounce);
  - `hooks/useMaterial.js` — `loading | ready | notFound | error` + повтор;
  - `ui/MaterialsLibrary.jsx` (поиск, «Тип материала», ошибка с повтором, пустая
    выдача, «Загрузить ещё»), `ui/MaterialArticle.jsx` (тело + `DOMPurify.sanitize`,
    тот же вызов), `ui/MaterialView.jsx` (состояния + возврат в библиотеку);
  - `components/` — `SearchBar`, `FiltersDropdown`, `FilterSheet`, `MaterialCard`,
    `MaterialsGrid` перенесены из `pages/materials/components/` (`git mv`);
    `MaterialCard`/`MaterialsGrid` получили путь чтения через проп. Мобильный
    `FilterSheet` — модальный диалог по клавиатуре: при открытии фокус на первом
    контроле панели, Tab / Shift+Tab циклически внутри, Escape закрывает, после
    закрытия (Escape, «Закрыть», подложка) фокус возвращается на кнопку
    «Фильтры» (если пользователь сам не перевёл его на другой элемент).
- Публичные `/materials`, `/materials/:id` — прежние Navbar/Hero/Footer/AuthModal
  и маршруты, тело — общий слой. Изменение поведения: нет «Старые» и «Тема»,
  «не найдено» отличается от сетевой ошибки (есть повтор).
- Кабинеты: `/student/materials` (+ `/:id`), `/psychologist/materials` (+ `/:id`),
  пункт меню психолога включён, крошки «Материал». Прав на статьи психолог не
  получил — только публичный API.
- Удалены: `useStudentMaterials.js`, `data/materials.mock.js`, избранное,
  `TAG_OPTIONS`/`TOPIC_OPTIONS`, неиспользуемые CSS сортировки.

## 3. Этап 2 — задания

### Backend (`mindcare_api/app/assignments/`)

routes / routes_psych → service (без FastAPI, AST-тест) → storage (весь SQL и
шифрование) → `app/db/models/assignments.py`. Плюс `errors`, `context`, `guards`,
`validators` (текст, курсор), `schemas`, `sanitized_route` (`AssignmentsRoute`).

| Метод и путь | Кто | Ответ |
|---|---|---|
| `GET /api/assignments/my?view=open\|history&before&size` | student (membership), без impersonation | `{items, has_more, next_cursor, total}` |
| `GET /api/assignments/my/summary` | то же | `{open_count, completed_count, total_count}` |
| `POST /api/assignments/my/{uuid}/complete` | то же | `{uuid, status, created_at, completed_at, cancelled_at, changed}` |
| `GET /api/psychologist/clients/{student_uuid}/assignments?before&size` | psychologist, строгое сопровождение | страница + `content_read` на каждое задание |
| `POST /api/psychologist/clients/{student_uuid}/assignments` | то же | 201, мутация без текста |
| `POST /api/psychologist/assignments/{uuid}/cancel` | то же | как complete |

- Коды отказов: 404 `assignment_not_available`, 409 `assignment_engagement_inactive`
  / `assignment_finalized` (+ `current_status`), 422 `assignment_material_unavailable`
  / `assignment_invalid` (`errors: [{field, code}]` без значений), 503 — сбой
  обязательного аудита, 500 — технический сбой. 403 — impersonation и нет роли.
- `Cache-Control: no-store, private` на всех ответах обоих роутеров (в т.ч. 401/403
  из зависимостей, 422, 503, 500).
- `size` 1–50 (по умолчанию 20); keyset `(created_at DESC, uuid DESC)`, курсор —
  непрозрачный base64url, битый → 422 `invalid_cursor`.

### Миграция `eb1460dc4954_add_assignments.py`

Таблица `assignments`; CHECK статуса, согласованности отметок и `enc:v1:`;
FK `engagement_id` CASCADE, `article_id` RESTRICT; индексы
`ix_assignments_engagement_created`, partial `ix_assignments_active_engagement`,
`ix_assignments_article_id`. Backfill нет; downgrade fail-closed при наличии строк.

### Frontend

- `api/assignments.api.js`; `features/assignments/`:
  - `hooks/useKeysetList` — первая страница, догрузка по курсору, сброс,
    применение свежей первой страницы (`applyFirstPage`) и опциональная
    фатальная ошибка догрузки (`isFatalLoadMoreError`). Каждый сброс/замена
    увеличивает generation: ответы, начатые до этого (в т.ч. догрузки и пробы),
    отбрасываются; дубли по uuid отбрасываются как страховка;
  - `hooks/useMyAssignments` — `open`/`history` и сводка. Как обновляются списки:
    1. своё выполнение (успех или no-op), 409 и 404 — оба списка сбрасываются и
       грузятся с первой страницы, номер пробы увеличивается (проба в полёте
       устаревает);
    2. опрос раз в 30 с (только видимая вкладка) и возврат на вкладку — «проба»:
       сводка + первая страница `open` и `history`. Для каждого списка
       сравнивается отпечаток первой страницы — uuid, статус, `can_complete`,
       `engagement_active` каждого элемента, а также `total` и `has_more`, —
       а не счётчики сводки: при передаче или реактивации сопровождения набор
       заданий меняется при тех же числах. Изменился отпечаток — список
       заменяется этой первой страницей (догруженные страницы сбрасываются,
       курсор берётся из неё); не изменился — догруженные страницы остаются.
       Проба применяется, только если её номер актуален и generation списка не
       менялось с её начала; сбой пробы ничего не меняет;
    3. без оптимистичного успеха; ref-lock от двойной отправки;
       `notifyAssignmentsChanged` для бейджа;
  - `hooks/useActiveAssignmentsCount` — бейдж (`open_count`), паттерн
    `usePendingVerificationsCount`;
  - `hooks/useClientAssignments` — список психолога, создание, отмена. После
    создания, отмены, 409 и 404 список сбрасывается. 404 при догрузке
    (сопровождение закрыто/передано, клиент отключён) — данные очищаются,
    раздел переходит в «Задания недоступны»; сетевая и прочие ошибки догрузки
    (в т.ч. 503 аудита) — загруженное остаётся, сообщение у списка, повтор —
    «Показать ещё» с тем же курсором;
  - `ui/ClientAssignments` (форма: подписанная textarea со счётчиком, `DateInput`
    срока, выбор материала; список со статусом; отмена через подтверждение),
    `ui/MaterialPicker` (поиск по публичной библиотеке), `ui/ConfirmDialog`.
- `/student/tasks` переписан: «Активные» / «История» с «Показать ещё», плитки
  статистики из сводки, подтверждение «Отметить выполненным» (необратимо),
  задание завершённого сопровождения — «Недоступно» и пояснение про возобновление.
- `StudentLayout` — бейдж из сервера (`normalizeRoles(user).includes('student')`,
  не в impersonation), `'99+'` и доступная подпись.
- Карточка клиента: раздел «Задания»; заглушка «Материалы и тесты» заменена на
  «Назначение тестов» (скоро).

## 4. Модель доступа и lifecycle

Кратко (полностью — ADR-033): психолог — только текущее строгое сопровождение с
активным клиентом; клиент — свои задания, изменение только при активном
сопровождении; прежний психолог теряет доступ, новый не видит старые задания;
реактивация той же пары возвращает задания этой связи; admin/supervisor — нет;
impersonation — 403. active → completed | cancelled, конечные статусы
неизменны, повтор — no-op.

Блокировки:
- мутации (create/complete/cancel) — `FOR SHARE` строки сопровождения: закрытие
  или передача не проскальзывают между проверкой права и изменением;
- чтение психологом — `FOR SHARE OF therapy_engagements, users` (сопровождение
  и клиент) в одной транзакции с выборкой страницы, а выборка повторяет предикат
  права. Закрытие/передача и отключение/удаление клиента не могут
  зафиксироваться между проверкой и чтением; зафиксированные раньше — единый
  404 + `assignment_read_failed` без `assignment_content_read`. Цикла
  блокировок нет (supervisor-путь не берёт `users`, отключение не трогает
  `therapy_engagements`); детерминированные тесты двух соединений — в
  `test_assignments_concurrency.py`, включая отсутствие deadlock.

## 5. Audit impact

| Событие | Роль | Режим |
|---|---|---|
| `assignment_created` | psychologist | ATOMIC/RAISE |
| `assignment_completed` | student | ATOMIC/RAISE |
| `assignment_cancelled` | psychologist | ATOMIC/RAISE |
| `assignment_content_read` | psychologist | INDEPENDENT/RAISE, по заданию страницы |
| `assignment_create_failed` | psychologist | access_denied / material_unavailable / invalid_request |
| `assignment_complete_failed` | student | access_denied / engagement_inactive / assignment_finalized |
| `assignment_cancel_failed` | psychologist | access_denied / assignment_finalized |
| `assignment_read_failed` | psychologist | access_denied |

Target — `assignment`, metadata `{}`; текст, срок, материал, ciphertext, uuid в
журналы не попадают. Чтение владельцем — без события. Чтение публичной
библиотеки — без событий. CHANGE_REGISTRY не менялся.

## 6. Проверено тестами

Результаты финального прогона — в отчёте задачи (раздел «Проверки»).

- Backend unit: `tests/test_assignments_unit.py` (AssignmentsRoute: no-store,
  422 без значений, HTTPException, AuditError → 503, прочее → 500; validators;
  fail-closed чтение; решения переходов и гонок на фейковой сессии; санитизация
  storage), `tests/test_assignments_registry_unit.py`; счётчики REGISTRY 123 → 131
  в 10 существующих тестах; `CURRENT_HEAD` в `test_audit_created_index_model.py`.
- Backend integration (изолированная `mindcare_test_*`):
  `test_assignments_api.py` (сквозной сценарий, шифрование, no-op, конфликт,
  материал, валидация, keyset без пропусков, content_read только по странице,
  no-store, failure-injection аудита/commit/content_read),
  `test_assignments_access.py` (чужие uuid, admin/supervisor, multi-role,
  impersonation, отключённый/удалённый клиент, close/transfer, реактивация, утечки),
  `test_assignments_concurrency.py` (закрытие до/после мутации, complete vs cancel
  в обе стороны, без deadlock). Миграция ↔ ORM — `test_models_match_migrations.py`
  (`alembic check`), single head.
- Frontend: тесты `features/materials/*`, студенческой `MaterialsPage`, router,
  `features/assignments/*`, `TasksPage`, `StudentLayout`, карточки клиента;
  `npm run lint`, `npm run build`.
- Corrective pass (2026-10-27), регрессионные тесты:
  `useMyAssignments.test.js` — «те же счётчики, другой состав» (передача),
  смена статуса без смены uuid (реактивация), тот же состав не сбрасывает
  догруженные страницы, проба до своего выполнения отбрасывается, сбой пробы;
  `useClientAssignments.test.js` — 404 догрузки → данные очищены и
  `unavailable`, сетевая ошибка догрузки → данные остаются, повтор догружает;
  `useMaterialsLibrary.test.js` — повтор того же запроса / после trim / той же
  категории не очищает и не запрашивает; `ui/MaterialsLibrary.test.jsx` —
  debounce «сон» → «сонx» → «сон» и « сон » без очистки, мобильный
  `FilterSheet` (matchMedia ≤ 768px): фокус при открытии, Tab / Shift+Tab по
  кругу, Escape и «Закрыть» возвращают фокус на «Фильтры», выбор типа.
  Против версий до правки (из `.backups`) падали 10 из этих тестов (6 по
  спискам/поиску, 4 по фокусу), с правкой — проходят. Итог: frontend 145
  наборов / 2136 тестов passed, `npm run lint` без ошибок, `npm run build` —
  Compiled successfully. Backend, миграции, EventSpec и CHANGE_REGISTRY не
  менялись.

## 7. Проверка в браузере — НЕ ПРОВОДИЛАСЬ

Ручной smoke обеих ролей, мобильного вида, тёмной темы и режима доступности не
выполнялся: для этого нужна применённая миграция на dev-БД, а применять её без
отдельной команды запрещено (API не стартует, пока БД не на head). Мобильный
режим панели фильтров и клавиатура проверены только в jsdom-тестах
(эмуляция `matchMedia`), не в реальном браузере. Рекомендуемый сценарий после `alembic upgrade head`:
психолог выдаёт задание с материалом и сроком → клиент видит его и бейдж →
отмечает выполненным → перезагрузка → психолог видит «Выполнено»; закрыть
сопровождение у супервизора → у клиента «Недоступно»; назначить ту же пару снова
→ задание снова активно; проверить 375 px, тёмную палитру и `hc`.

## 8. Ограничения и открытые вопросы

- Внешние изменения состава видны клиенту с задержкой до 30 с (проба при
  опросе); при изменении состава догруженные страницы сворачиваются до первой.
- Проба сравнивает первую страницу и `total` каждого списка. Изменения за
  пределами первой страницы видны через `total` (выполнение/отмена старого
  задания) или через саму первую страницу (новое задание, смена набора при
  передаче/реактивации). Изменение, которое не меняет ни первую страницу, ни
  `total`, проба не заметит до следующего сброса.
- Реактивация той же пары открывает прежние active-задания (согласовано).
- FK `article_id` RESTRICT блокирует физическое удаление статьи с заданиями.
- Психолог не может выдать задание клиенту с отключённым аккаунтом; клиент с
  отключённым аккаунтом не входит в систему (401).
- Отложено — `docs/BACKLOG.md`, раздел «Материалы и задания — продолжение».

## 9. Доработка по замечаниям владельца (2026-10-27) — ADR-034

Решения владельца: избранное — на сервере; статьи психолога — через модерацию;
уведомление о выполнении — system-сообщением.

> **Миграции (по порядку):** `ffd5e761b87b` (избранное) → `d0ee44dc2527`
> (модерация статей). Применить `alembic upgrade head`, затем перезапуск API.
> К dev-БД не применялись.

| Замечание | Что сделано |
|---|---|
| 1. Пропал значок избранного | Серверное избранное `material_favorites`: сердечко на карточке и фильтр «Избранное · N» в кабинетах студента и психолога; сохраняется между устройствами |
| 2. Карточки стали больше | Кабинеты — компактная карточка прежнего вида (`CompactMaterialCard`, 4 → 3 → 2 → 1 колонки, плашка 130 px, 8 на страницу); публичный сайт — прежние карточки |
| 3. Психолог должен публиковать свои материалы | «Мои материалы» (черновик → на проверку → публикует супервизор/админ; возврат с комментарием; правка опубликованной снимает с публикации); очередь «Модерация материалов» у супервизора и админа |
| 4. Некрасивое окно подтверждения | `ConfirmDialog` в стиле диалогов кабинетов (`UserLifecycleDialog`): отступы, заголовок, «Отмена» + действие, на узком экране — столбиком |
| 5. Быстрое действие в списке студентов | Кнопка «Выдать задание» на карточке студента → диалог с той же формой; выбор материала — встроенная панель (не вложенная модалка) |
| 6. Нет уведомления о выполнении | System-сообщение психологу после commit выполнения (без текста задания, без дублей) |

### API

- Избранное: `GET /api/materials/favorites/ids`, `GET /api/materials/favorites`
  (page, size, search, category_id), `PUT|DELETE /api/materials/favorites/{article_uuid}`
  (204, идемпотентно; 404 `material_not_available`, 409 `favorites_limit`);
  impersonation — 403; `Cache-Control: no-store, private`.
- Автор: `GET|POST /api/psychologist/articles`, `GET|PATCH|DELETE
  /api/psychologist/articles/{uuid}`, `POST …/{uuid}/submit` (409
  `article_state_conflict` + `current_status`).
- Проверка: `GET /api/review/articles`, `GET /api/review/articles/{uuid}`,
  `POST …/{uuid}/publish`, `POST …/{uuid}/return` `{comment?}` (admin, supervisor).
- Ответы статей получили поле `status` (`ArticleRead`, `ArticleListItem`).

### Audit impact

REGISTRY 131 → 135: `article_submitted_for_review`, `article_published`,
`article_returned_for_changes`, `article_unpublished_for_edit` (ATOMIC/RAISE,
target `article`, metadata `{}`); `article_created/updated/deleted` расширены
ролью psychologist. Избранное — без событий (решение ADR-034). Уведомление о
выполнении — существующий механизм system-сообщений, новых событий нет.

### Проверки (фактически выполнены)

- Backend (изолированная БД, `isolated_test_db.py`): полный набор — 4445 passed,
  78 skipped; новые `test_material_favorites_api.py`, `test_article_moderation_api.py`
  (поток модерации, шифрованный комментарий без утечек, 409, изоляция авторов,
  роли/impersonation, публикация админом, гонка publish/return под FOR UPDATE),
  уведомление в `test_assignments_api.py`; `alembic check`, single head.
- Frontend: 148 наборов / 2159 тестов passed; `npm run lint` — 0 ошибок;
  `npm run build` — Compiled successfully. Новые тесты: компактные карточки и
  избранное (`MaterialsPage.test.jsx`), `MyArticles`, `ArticleReview`, режим
  автора `ArticleFormModal`, быстрая выдача (`PsychologistStudentsPage.test.jsx`),
  встроенный выбор материала (`ClientAssignments.test.jsx`), маршруты.
- Ручная проверка в браузере (мобильный вид, тёмная тема, клавиатура) — НЕ
  проводилась: нужна применённая миграция на dev-БД.

### Ограничения

- HTML статей психолога санитизируется только при показе (DOMPurify), как у
  статей админа.
- Уведомлений о модерации и бейджа очереди нет; failure-событий модерации нет
  (как у тестов).
- Правка опубликованной статьи делает её недоступной в заданиях до повторной
  публикации.
- Подписи журнала админки для новых событий не добавлены (BACKLOG).

## 10. Уведомления и авторство супервизора (2026-10-28) — Дополнение к ADR-034

Миграций нет; REGISTRY 135 без изменений (расширены роли событий статей).

| Замечание | Что сделано |
|---|---|
| У супервизора нет уведомления о новых материалах на проверке | Бейджи очередей в меню: «Материалы» и «Тесты» у супервизора, «Модерация материалов» и «Тесты» у админа (`pending-count`, опрос 30 с, мгновенно после решения) |
| Каких уведомлений ещё не хватает | Добавлены system-сообщения: автору — о публикации/возврате материала и теста (у теста — с причиной возврата); клиенту — о новом и об отменённом задании. Остальное — в «Не делалось» |
| Супервизор публикует свои материалы | `/api/supervisor/articles*` + вкладка «Мои материалы» на `/supervisor/materials`: черновик → «Опубликовать» (с подтверждением), без очереди |

### API

- `GET /api/review/articles/pending-count`, `GET /api/admin/tests/pending-count`
  → `{count}` (admin, supervisor), без аудита.
- `GET|POST /api/supervisor/articles`, `GET|PATCH|DELETE /api/supervisor/articles/{uuid}`,
  `POST /api/supervisor/articles/{uuid}/publish` (409 `article_state_conflict`);
  submit у супервизора нет; психологу этот API — 403; impersonation — 403.
- `POST /api/admin/tests/{uuid}/return` — `reason` теперь доходит до автора в
  system-сообщении (не хранится, не логируется).

### Тексты уведомлений (без содержания задания и комментария статьи)

- Автору статьи: «Материал «…» опубликован и доступен в библиотеке. Мои материалы»,
  «Материал «…» возвращён на доработку. Комментарий проверяющего — в разделе
  Мои материалы».
- Автору теста: «Тест «…» опубликован. Мои тесты», «Тест «…» возвращён на
  доработку. Комментарий проверяющего: … Мои тесты».
- Клиенту: «Новое задание от психолога ФИО. Задания», «Задание от психолога ФИО
  отменено. Задания».

### Audit impact

Новых событий нет (REGISTRY 135). Расширены роли: `article_created/updated/deleted`
+ supervisor, `article_unpublished_for_edit` + supervisor; публикация своей статьи
супервизором — `article_published` (роль supervisor уже разрешена). Счётчики
очередей — без аудита. Уведомления — существующий механизм system-сообщений
(первое сообщение пользователю пишет `system_conversation_created`).

### Проверки (фактически выполнены)

- Backend (изолированная БД): полный набор — 4454 passed, 78 skipped; новый
  `tests/integration/test_moderation_notifications_api.py` (счётчики очередей и
  отсутствие аудита, уведомления автора статьи без комментария и с новым ключом
  на повторный возврат, своё решение без уведомления, сбой доставки не отменяет
  публикацию, CRUD и публикация супервизора с ролями событий, границы API
  супервизора/психолога/impersonation, счётчик и уведомления по тестам с
  причиной возврата без утечки в журнал, прямая публикация черновика без
  уведомления, уведомления клиента о новом/отменённом задании без текста и без
  дубля). Обновлены ожидания ролей в `test_content_test_consent_audit_unit.py`
  и точные списки событий в `test_article_moderation_api.py` /
  `test_assignments_api.py` (исключён побочный `system_conversation_created`).
- Frontend: 150 наборов / 2174 теста passed; `npm run lint` — 0 ошибок;
  `npm run build` — Compiled successfully. Новые/обновлённые тесты:
  `useReviewQueueCounts.test.js`, `SupervisorMaterialsPage.test.jsx`,
  `SupervisorLayout.test.jsx` и `AdminLayout.test.jsx` (бейджи, impersonation),
  `MyArticles.test.jsx` и `ArticleFormModal.test.jsx` (режим супервизора),
  `ArticleReview.test.jsx` (шина бейджа), `internalLinks.test.js`, маршруты.
- Ручная проверка в браузере — НЕ проводилась (нужна применённая миграция).

### Ограничения

- Бейдж обновляется у других проверяющих с задержкой до 30 с (опрос).
- Уведомления о сроке задания, e-mail/push и центр уведомлений — не делались.
- Модерация тестов по-прежнему без блокировки строки (BACKLOG).

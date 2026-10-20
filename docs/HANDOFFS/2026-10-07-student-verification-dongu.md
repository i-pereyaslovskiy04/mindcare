# Handoff (2026-10-07): подтверждение статуса студента ДонГУ

ADR-029 (`docs/DECISIONS.md`). Миграция `f5a3c8d1e7b2`. REGISTRY 115 → 121.

## Главное

- «Студент ДонГУ подтверждён» — **отдельный статус, не роль**. Роль `student`,
  её подпись «Пользователь», маршруты `/student`, membership/permissions и доступ
  к тестам/консультациям не менялись. `student_profiles.faculty` подтверждением
  не считается; миграция ничего не подтверждает.
- Пользователь (активные роли ровно `{student}`, не impersonation) подаёт
  заявку в `/student/settings#student-verification`: факультет из каталога (12,
  стабильные коды, единственный источник — `app/student_verification/faculties.py`)
  и номер студенческого билета (строка, ведущие нули сохраняются, `enc:v1:`).
- Проверяет **только прямой supervisor** (`/supervisor/student-verifications`):
  список без номера, карточка с полным номером под fail-closed аудитом,
  «Подтвердить» / «Отклонить» (с обязательным пояснением). Admin без
  supervisor, psychologist, impersonation-сессия — 403. Свою заявку решать
  нельзя (`self_review_forbidden`).
- Одна pending; pending неизменяема; после отказа — новая заявка (история
  сохраняется строками); **одобрение финально** (`already_verified`).
- После обычной регистрации и регистрации через Яндекс приходит приглашение,
  после решения — результат. Оба — system-сообщения через outbox
  `system_message_intents` с повторной доставкой.

## API

| Метод | Путь | Доступ | Примечание |
|---|---|---|---|
| GET | `/api/student-verification/faculties` | любой аутентифицированный | `{items:[{code,label}]}`, без аудита |
| GET | `/api/student-verification/me` | чистый student, не impersonation | `{status, can_submit, current}`; номер не отдаётся; пояснение отказа — да |
| POST | `/api/student-verification/me` | то же | `{faculty_code, ticket_number}`, лишние поля → 422; 201 |
| GET | `/api/supervisor/student-verifications?status=pending\|approved\|rejected\|all&page&size&search` | supervisor, не impersonation | без номера, без аудита; поиск по ФИО/email |
| GET | `/api/supervisor/student-verifications/{uuid}` | то же | полный номер; `content_read` или 503 |
| POST | `…/{uuid}/approve` | то же | |
| POST | `…/{uuid}/reject` | то же | `{reason}` 1..1000 |

Отказы — `{"detail", "code"}`: `verification_not_allowed` (403),
`impersonation_forbidden` (403), `verification_pending_exists` (409),
`already_verified` (409), `account_inactive` (409), `verification_not_found`
(404), `self_review_forbidden` (403), `reviewer_not_allowed` (403),
`verification_already_decided` (409). Запрет impersonation на supervisor-роутере —
обычный 403 `detail` (auth-guard). Ответы со статусом/карточкой —
`Cache-Control: no-store, private`.

## Миграция

`f5a3c8d1e7b2` (после `d7e2a9c4f1b6`):

- `student_verification_requests` — uuid, `user_id` (CASCADE), `faculty_code`,
  `ticket_number_enc` / `rejection_reason_enc` (CHECK `enc:v1:`), `status`
  (CHECK), `submitted_at`, `reviewed_by` (SET NULL), `reviewed_at`,
  CHECK согласованности статуса и полей решения, partial UNIQUE
  `ux_svr_user_pending` / `ux_svr_user_approved`, индексы.
- `system_message_intents` — `recipient_id` (CASCADE), `event_key`,
  `message_code`, `created_at`, `attempts`, `last_attempt_at`, `delivered_at`;
  UNIQUE (`recipient_id`, `event_key`), partial index недоставленных.
- Backfill нет. Downgrade fail-closed, если в любой из таблиц есть строки.

**Порядок запуска:** `cd mindcare_api && alembic upgrade head` (вне lifespan) →
перезапуск API → `./deploy.sh` устанавливает и включает
`mindcare-deliver-system-messages.timer`. При ручном развёртывании:

```bash
sudo cp deploy/mindcare-deliver-system-messages.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mindcare-deliver-system-messages.timer
```

К рабочей БД в этой задаче миграция **не применялась** — только к одноразовым
тестовым БД изолированного runner'а.

## Транзакции и блокировки

- Подача: `users` заявителя `FOR UPDATE` → перечитанные заявки → INSERT +
  `student_verification_submitted` → commit.
- Решение: предварительное чтение заявки → `users` заявителя **и** reviewer'а
  `FOR UPDATE` в порядке `users.id` → повторная проверка допуска reviewer'а
  (активен, не удалён, роль supervisor) → заявка `FOR UPDATE` с
  `populate_existing` → переход + success-событие + outbox-намерение → commit.
  Reviewer блокируется явно: FK `reviewed_by` и FK актора `audit_log` берут
  `FOR KEY SHARE` на его строку; без общего порядка два supervisor'а,
  проверяющие заявки друг друга, взаимно блокировались бы.
- Сбой аудита, намерения или commit откатывает всё вместе (проверено
  failure-injection).

## Санитизация технических сбоев и минимизация SELECT (доработка 2026-10-08)

- **Неожиданные SQLAlchemy-ошибки записи** (flush подачи, условный UPDATE
  решения, вставка outbox-намерения, commit) перехватываются в
  `student_verification/storage.py`: rollback, в stderr — только
  `[STUDENT_VERIFICATION] op=<submit|decide> phase=<flush|update|enqueue|commit|rollback>
  error=<класс>`, наружу — `VerificationStorageError` (фиксированный текст,
  создаётся вне `except`, `from None`: ни `__cause__`, ни `__context__`). Это
  НЕ `VerificationError`: route его не ловит → 500, `*_failed` не пишется.
  SQL, параметры, ciphertext/plaintext номера и пояснения не попадают ни в
  ASGI traceback, ни в серверную диагностику, ни в ответ.
- **Чтения санитизируются так же** (доработка 2026-10-08, вторая итерация):
  `list_requests` (`op=list`), `get_latest_for_user` (`op=status`), `get_card`
  (`op=card`) и предварительные чтения/блокировки подачи и решения
  (`op=submit|decide`) — все с `phase=read`. Подтверждённый сценарий:
  OperationalError SELECT списка нёс в параметрах введённый supervisor'ом
  search-email и уходил в ASGI traceback. Теперь: rollback, диагностика
  `op/phase=read/error-class`, наружу `VerificationStorageError` без цепочки
  → 500. Технический сбой чтения не пишет ни `*_failed`, ни
  `student_verification_content_read` (сбой — до записи аудита); отказ
  записи аудита карточки по-прежнему → 503 без номера. Доменные отказы
  (`verification_not_found`, `account_inactive`, `self_review_forbidden` …)
  не SQLAlchemyError и проходят как есть.
- Известные конфликты (`ux_svr_user_pending` → `verification_pending_exists`,
  `ux_svr_user_approved` → `already_verified`) сохраняют typed codes.
  Не-SQLAlchemy исключения (например, ошибка шифрования) не переклассифицируются.
- **SELECT — только явные проекции колонок**, ORM-сущности `User` и заявки не
  загружаются (Row без lazy-загрузки):
  - список и история — метаданные заявки + ФИО/email/признаки активности
    заявителя + ФИО проверившего; без `ticket_number_enc`,
    `rejection_reason_enc`, `password_hash` и прочих auth-полей;
  - собственный статус — без номера; `rejection_reason_enc` — отдельный
    запрос только для `rejected`;
  - карточка — один запрос с обоими ciphertext-полями, без auth-полей users;
  - блокировки users — только `id, is_active, deleted_at` `FOR UPDATE`;
    заявка — метаданные `FOR UPDATE`; решение — условный
    `UPDATE … WHERE status='pending'` (rowcount = 1) без загрузки строки;
  - подача после commit строку не перечитывает (id — из `RETURNING`).
  Повторное чтение под блокировкой — проекция, а не сущность из identity map,
  поэтому после ожидания всегда видит свежее состояние.
- API-контракты, пагинация, поиск, fail-closed аудит карточки не изменились.

## Уведомления (outbox)

- Шаблоны — `app/notifications/templates.py` (тексты дословно из задачи;
  приглашение и отказ заканчиваются строкой
  `Открыть раздел: /student/settings#student-verification`). В outbox — только
  `message_code`, текста и ПДн нет.
- Приглашение: намерение в ОБОИХ core UoW регистрации
  (`auth.storage.register_confirm_atomic`,
  `oauth.storage.complete_registration_atomic` →
  `enqueue_registration_invite_in_tx`), ключ
  `student_verification_invite:user:{id}`; доставка после commit в
  `run_post_registration_actions`.
- Результат: намерение в транзакции решения, ключ
  `student_verification_result:{request_uuid}`; доставка после commit.
- `delivered_at` — только после успешного результата
  `publish_system_message` (в т.ч. `created=False`: сообщение уже есть).
- `create_system_message` считает дублем ТОЛЬКО нарушение
  `ux_chat_messages_event_key`; прочие `IntegrityError` пробрасываются, доставка
  не отмечается.
- Retry: `python scripts/deliver_system_message_intents.py [--dry-run] [--limit N]`
  (таймер каждые 5 мин). Exit 1 — ошибка чтения outbox или любой неуспешный
  исход публикации/отметки; пустая очередь — exit 0 только при успешном чтении.
  Лог — агрегаты `found/delivered/failed` и фаза/класс исключения.
- Ссылка: `LinkifiedText` превращает путь в router-`<Link>` «Подтверждение
  студента ДонГУ» только в system-сообщениях и только для точного allowlist;
  раздел настроек по хешу прокручивается и получает фокус.

## Аудит

| Событие | Actor | Target | Режим |
|---|---|---|---|
| `student_verification_submitted` | {student} | `student_verification_request` | ATOMIC/RAISE, metadata {} |
| `student_verification_approved` / `_rejected` | {supervisor} | то же | ATOMIC/RAISE, metadata {} |
| `student_verification_content_read` | {supervisor} | то же | INDEPENDENT/RAISE (fail-closed) |
| `student_verification_submit_failed` | student / staff (acting-роль) / admin-инициатор при impersonation | — | INDEPENDENT/SOFT |
| `student_verification_review_failed` | {supervisor} | — | INDEPENDENT/SOFT |

Без событий: чтение своего статуса и каталога, список, 422, no-op повтор
решения, запрет supervisor-эндпоинтов в impersonation (auth-guard; вход «под
именем» уже записан `admin_user_impersonated`), retry-job (техническая доставка
уже зафиксированного решения). DCL не пишется. Admin viewer и
`auditLabels.js` знают новые события, коды и тип объекта.

## Frontend

- `src/api/studentVerification.api.js`; `src/features/studentVerification/`
  (`lib/status.js`, хуки `useMyStudentVerification`, `useFaculties`,
  `useStudentVerifications` (list-контракт), `useStudentVerificationCard`;
  `ui/StudentVerificationSection`, `ui/VerificationsTable`,
  `ui/VerificationReviewModal`).
- `SettingsPage`: раздел `#student-verification` (чистый student вне
  impersonation; в impersonation — пояснение), бейдж «Студент ДонГУ
  подтверждён» в карточке «Профиль». Тот же бейдж — `ProfilePage`.
- `StudentVerificationsPage` + пункт «Подтверждение студентов» в
  `SupervisorLayout`, маршрут `/supervisor/student-verifications`.
- Shared UI: `Select`, `Button`, `Badge`, `FilterChip`, `Modal`; CSS Modules
  только на токенах. Новых локальных `.btn*/.badge*/.chip*` нет.

## Проверки (фактические результаты)

- Backend, полный изолированный прогон `..\test.ps1` (одноразовая
  `mindcare_test_*`, alembic upgrade head, drift-тест `alembic check` внутри):
  **3822 passed, 79 skipped** (2026-10-08, после санитизации чтений; до неё —
  3810, до первой доработки — 3791). Новые тесты доработок (все выполнены, не
  пропущены):
  `tests/test_student_verification_storage_unit.py` (17: typed-конфликты,
  синтетические IntegrityError/DataError/OperationalError с маркерами в SQL,
  параметрах и ошибке драйвера → чистый traceback/stderr, откат, нет
  success-аудита, контроль, что маркеры реально присутствуют до санитизации;
  сбой чтения list/status/card/decide и блокировки подачи → `phase=read`;
  доменные отказы внутри read-секции не переклассифицируются),
  `tests/integration/test_student_verification_read_sanitization.py` (6:
  настоящий OperationalError PostgreSQL — SELECT по заявкам отменяется по
  `statement_timeout`, SQLAlchemy оборачивает его реальным SQL и параметрами,
  в т.ч. search-email (контрольный тест это подтверждает); список с search,
  карточка, свой статус, подача, решение → исключение без цепочки, traceback и
  запись `uvicorn.error`, stderr/caplog и тело 500 без маркеров/SQL/параметров;
  ни `*_failed`, ни `content_read`; после сбоя модуль работает штатно),
  `tests/integration/test_student_verification_sanitization.py` (3: реальные
  нарушения CHECK на flush подачи и UPDATE отказа, синтетический сбой commit
  одобрения — исключение без цепочки, traceback и лог-запись uvicorn.error,
  stderr/caplog и тело 500 без маркеров, заявка/решение/намерение откатаны,
  нет `*_submitted|approved|rejected` и `*_failed`),
  `tests/integration/test_student_verification_queries.py` (5: перехват
  фактических SELECT — точное число запросов, отсутствие ciphertext и
  auth-полей, пояснение только для rejected, контракт DTO, поиск, пагинация).
- Новые тесты: `tests/test_student_verification_unit.py`,
  `tests/test_deliver_system_message_intents_cli_unit.py`,
  `tests/integration/test_student_verification_api.py`,
  `tests/integration/test_student_verification_concurrency.py`
  (две подачи; submit ∥ approve в обоих порядках; approve ∥ approve;
  approve ∥ reject; approve ∥ отключение; перекрёстная проверка двумя
  supervisor'ами без deadlock), `tests/integration/test_system_message_intents.py`.
- Обновлены exact-контракты registry (115 → 121), head-тест, deploy-тест,
  тест post-commit шагов OAuth-регистрации.
- Frontend: `npm test -- --watchAll=false` — **101 suites / 1388 tests passed**;
  `npm run lint` — 0 предупреждений; `npm run build` — Compiled successfully
  (прогон 2026-10-07; повторён 2026-10-08 после ручного запуска — тот же
  результат: 101 / 1388, lint 0, build OK).
- Patch задачи (каждый файл против его первого бэкапа сессии, новые — целиком):
  `tmp/patches/2026-10-07-student-verification.patch` (каталог `tmp/` в
  `.gitignore`).
- **Ручной запуск (2026-10-08, `start.ps1`):** рабочая БД `mindcare` на
  `f5a3c8d1e7b2` (head). READ-ONLY осмотр после запуска: заявок, намерений,
  событий `student_verification_*` и новых регистраций нет — сценарий через UI
  на рабочей БД не проходился; инварианты (только `enc:v1:`, нет двух
  pending/approved, нет самопроверки, DCL пуст) выполняются тривиально.
  `scripts/deliver_system_message_intents.py --dry-run` на рабочей БД →
  `pending=0`, exit 0.
- **Сквозной HTTP-smoke (2026-10-08): 47/47.** Настоящий uvicorn-процесс на
  одноразовой `mindcare_test_*` (миграции alembic, БД удалена после прогона),
  только синтетические данные: регистрация по паролю → приглашение (ровно одно,
  с путём `/student/settings#student-verification`) → каталог 12 → подача с
  ведущими нулями → 409 повторной подачи / 422 чужого факультета → staff+student
  403 → список без номера/ciphertext → карточка с полным номером (`no-store`) →
  admin без supervisor 403 → impersonation supervisor: список/карточка/решение
  403 без номера → отказ (422 без пояснения) → уведомление без пояснения/номера
  → статус rejected с пояснением → повторная подача → история в карточке →
  одобрение → no-op повтор → 409 противоположного → одно уведомление → 409
  `already_verified` → роль по-прежнему `student`; retry-job: dry-run
  `pending=1` → доставка `found=1 delivered=1 failed=0` → повтор `found=0`,
  одно сообщение, вывод только агрегатами; журналы temp-БД: ожидаемые события
  и failure-коды, без номера/пояснения/ciphertext, DCL пуст; лог сервера без
  Traceback и без номера/пояснения/ciphertext. Протокол —
  `tmp/patches/smoke_result.txt`.
- Браузерный smoke (клики по UI, переход по ссылке из чата) в этой сессии не
  выполнялся: headless-браузера в окружении нет; UI покрыт jest-тестами
  (раздел, прокрутка/фокус по хешу, ссылка в system-сообщении, страница
  supervisor).

## Не трогалось

`student_profiles.faculty`, роль `student` и её подпись, `/student`-маршруты,
membership/permissions, доступ к тестам и консультациям, welcome-сообщение
(best-effort), staff-created student flow, `get_or_create_system_conversation`,
общий `app/auth/deps.py`.

## Остаточные риски

- Браузерный smoke на стенде (миграция уже применена): клик по ссылке
  «Подтверждение студента ДонГУ» в «Сообщениях» → раздел настроек с фокусом;
  бейдж в профиле после одобрения; раздел «Подтверждение студентов» у
  supervisor и его недоступность при входе «под именем». HTTP-уровень этих
  сценариев проверен (47/47).
- Смена факультета/отзыв подтверждения, приглашение существующим
  пользователям, retention номеров — `docs/BACKLOG.md`.
- Если таймер retry не включён, недоставленные из-за сбоя уведомления ждут
  ручного запуска скрипта (сами намерения не теряются).

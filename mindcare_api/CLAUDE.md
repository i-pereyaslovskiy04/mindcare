# CLAUDE.md — бэкенд (`mindcare_api/`)

Этот файл загружается, когда работа идёт с файлами под `mindcare_api/`.
Общие правила проекта (ФЗ-152, backup-hook, Git, роли, Audit mode) — в
корневом `CLAUDE.md`. Полные правила фронта — `mindcare_web/CLAUDE.md`.

## Команды

### Backend (`mindcare_api/`)

```bash
# Активация виртуального окружения (Linux/macOS, обязательно перед всем остальным)
source .venv/bin/activate
```

```powershell
# Windows: активация виртуального окружения
.venv\Scripts\Activate.ps1

# Если PowerShell блокирует скрипты:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

```bash
# Установка зависимостей (после активации venv)
pip install -r requirements.txt

# Запуск dev-сервера (из папки mindcare_api/)
uvicorn app.main:app --reload

# Создание первого администратора (интерактивный скрипт)
python scripts/create_admin.py

# Диагностика SMTP
python scripts/test_smtp.py

# Создание будущих партиций audit-таблиц (запускать отдельно, не из FastAPI)
# Stage 7: поставлен на таймер mindcare-ensure-audit-partitions.timer
# (ежемесячно). Ручной запуск остаётся доступен; только СОЗДАЁТ партиции.
python scripts/ensure_audit_partitions.py --months-ahead 24
python scripts/ensure_audit_partitions.py --months-ahead 24 --dry-run  # проверка без DDL

# IP-анонимизация audit-журналов (Stage 7). Вызывает функции ревизии
# c8e2b5f7a3d1: dry-run → count_old_ips (read-only), live → anonymize_old_ips.
# ⚠ LIVE-ПРОГОН НЕОБРАТИМ: обнулённые ip_address не восстанавливает ни
# alembic downgrade, ни повторный запуск. Первый прогон — ВРУЧНУЮ, вне
# systemd, после dry-run (см. deploy/STAGE_7_DEPLOYMENT.md).
python scripts/anonymize_old_ips.py --days 90 --dry-run
python scripts/anonymize_old_ips.py --days 90

# ── ОБЯЗАТЕЛЬНЫЕ периодические maintenance-job'ы (внешний планировщик) ──
# Автопродление расписаний (серии с auto_extend); per-series транзакция +
# FOR UPDATE SKIP LOCKED, dry-run не пишет audit и не мутирует
python scripts/extend_schedules.py
python scripts/extend_schedules.py --dry-run

# Перевод начавшихся групповых занятий в completed (Stage 5C-3).
# ⚠ ОБЯЗАТЕЛЕН: раньше этот переход выполнялся лениво из GET/list и из
# регистрации; теперь read-пути НЕ мутируют данные, поэтому без планировщика
# status групповых занятий перестаёт актуализироваться.
python scripts/complete_group_sessions.py
```

> **Эксплуатационное требование Stage 5C-3:** `extend_schedules.py` и
> `complete_group_sessions.py` обязаны запускаться внешним планировщиком —
> готовые systemd service/timer лежат в [`deploy/`](deploy/STAGE_5C_DEPLOYMENT.md)
> (`mindcare-complete-group-sessions.timer` — каждые 10 мин;
> `mindcare-extend-schedules.timer` — ежедневно 03:20). Оба завершаются
> ненулевым кодом при любом сбое (мутация / audit / commit); мониторинг — по
> `systemctl is-failed` + `OnFailure=mindcare-maintenance-failure@`. В лог
> пишутся только фаза и класс исключения (без `str(exc)`, SQL, id и дат).
>
> **Порядок деплоя Stage 5C:** одношаговый `alembic upgrade head` без остановки
> приложения **не поддерживается** (окно совместимости между `a1c4e8b2f7d3` и
> `b5d7f0a3c9e1`). Допустимы только два пути — с гарантированным простоем либо
> поэтапный expand/contract; оба описаны в
> [`deploy/STAGE_5C_DEPLOYMENT.md`](deploy/STAGE_5C_DEPLOYMENT.md).
> Запись студента на прошедшее занятие при этом невозможна независимо от
> своевременности job: регистрация сама проверяет `status`, `booking_enabled`
> и lead time (не позднее чем за 1 час до начала).
>
> **Stage 7 — два таймера с РАЗНОЙ политикой активации.**
> `mindcare-ensure-audit-partitions.timer` (ежемесячно) `deploy.sh` включает
> автоматически: job только создаёт будущие партиции, ничего не удаляет.
> `mindcare-anonymize-ips.timer` (ежедневно 03:40) — **устанавливается, но НЕ
> активируется**: `Persistent=true` + `enable --now` запустили бы необратимый
> первый прогон немедленно, до dry-run. Порядок ввода в эксплуатацию (dry-run →
> оценка объёма → ручной live-прогон → активация) и opt-in-флаг
> `./deploy.sh --enable-ip-anonymization` — в
> [`deploy/STAGE_7_DEPLOYMENT.md`](deploy/STAGE_7_DEPLOYMENT.md).

### База данных

```bash
# ══════════════════════════════════════════════════════════
# ПОРЯДОК ЗАПУСКА (ОБЯЗАТЕЛЬНО перед стартом приложения):
# ══════════════════════════════════════════════════════════

# 1. Применить все Alembic-миграции (создаёт/обновляет схему)
cd mindcare_api/
alembic upgrade head

# 2. Запустить приложение (seed выполнится автоматически в lifespan)
uvicorn app.main:app --reload

# ══════════════════════════════════════════════════════════

# Подключение к БД для ручных запросов
psql -U MindcareUser -d mindcare

# Проверить текущую версию схемы
cd mindcare_api/ && alembic current

# Создать новую миграцию после изменения ORM-моделей
cd mindcare_api/ && alembic revision --autogenerate -m "describe_change"

# История миграций
cd mindcare_api/ && alembic history
```

> **Важно:** схема БД управляется **только** через Alembic.
> `Base.metadata.create_all()` **удалён** — не использовать.
> Все 58 таблиц создаются через `alembic upgrade head`.
> Audit-таблицы (`auth_log`, `audit_log`, `data_change_log`) включены в Alembic
> начиная с migration `3a7c5e2b8f1d`.
>
> FastAPI при старте **НЕ** применяет миграции — только проверяет revision
> и выдаёт WARNING если DB отстаёт от head.


## Архитектура

### Backend: структура модулей

Состав модулей — `ls mindcare_api/app/`. Каждый доменный модуль устроен одинаково:
`routes.py` / `routes_admin.py` · `schemas.py` · `service.py` (без FastAPI/HTTP) ·
`storage.py` (весь SQLAlchemy здесь). Вне этой схемы: `core/` (config, encryption,
normalization, rate_limit), `db/` (session, init_db, seed, models/), `auth/`,
`services/` (SMTP, email), `scripts/` (create_admin, ensure_audit_partitions,
backfill_legal_basis, extend_schedules, complete_group_sessions,
repair_missing_chat_conversations,
cleanup_orphan_attachments, test_smtp), `db/sql/` (legacy bootstrap-схема).

**Правила бэка:**

```
✅ Все эндпоинты — def (не async def)
✅ Роли проверяются на бэке через require_role — не только на фронте
✅ Email всегда нормализуется: email.lower().strip()
✅ Пароли — bcrypt через passlib. Никакого sha256, md5
✅ OTP-коды — SHA-256 хеш в БД, plaintext только в email. Никакого plaintext.
✅ Токены сброса пароля — хранятся как хеш, не plaintext
✅ Soft delete — deleted_at, не физическое удаление
✅ Внешний API использует users.uuid (UUID), не users.id (INT)
✅ Схема БД — только через Alembic (alembic upgrade head перед стартом)
✅ consent_records — ТОЛЬКО личное согласие субъекта (НЕ «согласие за пользователя»):
   студент сам принимает политику при self-registration, ЛИБО staff фиксирует личное
   согласие студента, полученное ОЧНО, при создании аккаунта через
   POST /api/supervisor/students (как у карточки незарег. студента) — это не legal basis
✅ admin/supervisor создаёт ПОЛНОЦЕННЫЙ аккаунт студента через
   POST /api/supervisor/students (temp password, как POST /api/admin/users). Основание
   ПДн — consent_records (личное согласие, получено очно; staff подтверждает
   personal_data_consent), НЕ user_legal_basis_records. Core-запись атомарна:
   User+UserRole(student)+ConsentRecord[]+опц. active TherapyEngagement+AuditLog в одном
   commit; AuditLog обязателен (consent_records не хранит actor); psychologist_id создаёт
   active engagement в ТОЙ ЖЕ транзакции (не отдельным вызовом assign_psychologist);
   карточка незарег. студента с тем же email привязывается (этап 2). Это НЕ admin
   role control (там student по-прежнему НЕ selectable). Пароль/ПДн не логировать
✅ `POST /api/admin/users` создаёт staff с одной или несколькими ролями:
   request содержит ровно одно из legacy `role` или `roles[]`; только
   `psychologist`/`supervisor`/`admin`, без `student`. `basis_reference`
   обязателен и trim-ится; на каждую уникальную staff-роль в той же
   транзакции пишется `user_legal_basis_records` с metadata
   `action=user_create`/`created_role`/`roles_after`. Response возвращает
   детерминированный `roles[]` и legacy primary `role`. Welcome email для staff
   role-neutral: без упоминания конкретной роли или прав.
✅ Добавление новой staff-роли через admin role management
   (psychologist/supervisor/admin) требует legal basis
   (legal_basis_confirmed + basis_type + basis_reference); добавление роли и запись
   user_legal_basis_records атомарны; metadata: action=role_add/added_role/
   roles_before/roles_after. Удаление staff-роли требует audit trail, но не новый
   legal basis; старые user_legal_basis_records не удаляются.
✅ Роли в admin edit-модалке РЕДАКТИРУЕМЫ как multi-role control / set-based API,
   но безопасно: при добавлении staff/admin роли UI показывает блок legal basis и
   шлёт его поля; backend guard обязателен как defense-in-depth (не полагаться
   только на UI). Запрещено заменять весь набор user_roles одним role.
   В PATCH отсутствие поля `roles` означает «не менять роли», а явный `roles: []` —
   целевой пустой набор staff-ролей: он снимает все staff-роли только если после
   операции остаётся другая активная роль (например, `student`), иначе backend
   отклоняет запрос с 422. Удаление всегда фиксируется в audit trail.
✅ student НЕ selectable в admin role control. Студенты появляются через
   self-registration ИЛИ через staff-created student flow (`POST /api/supervisor/students`);
   существующая роль student показывается read-only badge и не удаляется случайно.
   student как target роли из admin edit UI/API не отправляется без отдельного
   compliance-решения
✅ Администратор не может снять у самого себя membership-роль admin. Backend
   сравнивает actor_id и target user id; frontend lock — только UX-дублирование.
   Другой администратор может изменить роли пользователя.
✅ Все HTTP/API creation flows допускают новый аккаунт только для активного точного
   нормализованного домена из allowed_email_domains: self-registration,
   admin-created staff и supervisor/admin-created student. Existing login/password
   reset не блокировать. Authoritative check выполняется в creation transaction;
   в register confirm — до consume OTP. Локальный bootstrap `scripts/create_admin.py`
   остаётся отдельным privileged ops-path вне allowlist; использовать только при
   развёртывании и вручную выбирать разрешённый организацией домен.
✅ Allowlist управляется только admin через GET/POST/PATCH
   /api/admin/email-domains. DELETE нет; отключённую строку реактивировать PATCH,
   не повторным POST. Последний активный домен отключить нельзя. Audit не содержит
   сырой comment.
❌ Не слать role changes без legal basis при добавлении staff-роли
❌ Не писать «админ подтверждает согласие пользователя» — только «документированное
   основание для назначения роли и обработки ПДн». Не смешивать student consent и staff legal basis
✅ session_notes: psychologist — только свои; supervisor — content только поштучно
   и под audit (session_note_content_read); admin — metadata-only без decrypt
✅ Staff-чтение терапевтического content ОБЯЗАНО писать audit-событие (без plaintext)
✅ Metadata-путь session_notes не должен вызывать decrypt_text
✅ Chat content доступен только student/psychologist — участникам therapy_engagement
✅ Chat content шифруется при записи и не попадает в logs/audit
✅ Расписание создаётся серией (POST /api/supervisor/schedules): rules + breaks
   c общим series_id и периодом. meeting_type_id НЕ задаётся для новых рабочих
   окон schedule v3; тип встречи выбирается при поиске/создании записи.
   auto_extend=true требует effective_until (валидация в service → 422)
✅ Soft-delete/restore расписания — на уровне СЕРИИ через is_active (rules+breaks);
   существующие Appointment НЕ удаляются и продолжают занимать слоты. Перед
   деактивацией возвращается счётчик будущих записей в периоде (предупреждение)
✅ Ручная запись supervisor'ом (POST /api/supervisor/appointments) создаёт обычный
   Appointment в pending_confirmation; для зарегистрированного студента требует активного
   engagement студент↔психолог. Для walk-in клиента можно использовать
   unregistered_student_card_id; карточка хранит минимальные ПДн и может привязаться к
   будущему аккаунту по normalized_email. Психолог получает system-сообщение
   (event_key appointment_supervisor_new:{uuid})
✅ Групповые занятия (`group_sessions`) создаёт supervisor; student записывается только
   на `scheduled` + `booking_enabled=true`, без подтверждения психолога.
   **Stage 5C-3: lazy-completion из GET/list и из регистрации УДАЛЁН** — read-пути
   не мутируют данные. Переход `scheduled`→`completed` (+ `booking_enabled=false`)
   выполняет ТОЛЬКО `scripts/complete_group_sessions.py` (обязательный
   планировщик, событие `group_session_completed`, Actor.system()). Student видит
   только `scheduled` (список фильтруется `starts_at > now`); supervisor/
   psychologist видят `scheduled`/`completed`/`cancelled` — до очередного запуска
   job прошедшее занятие у них может числиться `scheduled` (осознанный размен на
   read-only GET). Запись на прошедшее занятие невозможна: регистрация проверяет
   `status`, `booking_enabled` и lead time самостоятельно
✅ `group_sessions.status` через generic PATCH — стабильный enum: допустим только
   переход `scheduled`→`cancelled` (событие `group_session_cancelled`).
   `completed` через API ЗАПРЕЩЁН (принадлежит system maintenance);
   `cancelled`→`scheduled` запрещён до отдельного спроектированного события
✅ Регистрация/отмена групповой записи переворачивают строку условным
   `UPDATE … WHERE <предикат> RETURNING id`: success и audit возникают ровно для
   ОДНОГО физического перехода (проверка сервиса читается до блокировки занятия и
   под конкуренцией устаревает). Не-переворот → 409 (регистрация) / 404 (отмена)
   без мутации и без audit
✅ В `GroupRegistrationConflict` (409) превращается ТОЛЬКО нарушение
   `ux_gsr_active`, опознанное по `exc.orig.diag.constraint_name`. Прочие
   IntegrityError (FK, NOT NULL, чужой unique) всплывают как есть — это дефект,
   а не «вы уже записаны». Классификацию не делать разбором текста сообщения
❌ Не отправлять в generic PATCH группового занятия явный `null` для NOT NULL-поля:
   `exclude_unset` его не отбрасывает, поэтому service отвергает такие поля 422 ДО
   мутации (иначе был бы 500 на NOT NULL violation)
✅ Автопродление расписаний — ТОЛЬКО maintenance (scripts/extend_schedules.py →
   service.auto_extend_schedules); НЕ из FastAPI lifespan. После продления —
   system-сообщение создавшему серию supervisor'у (created_by, soft-fail)
❌ Не запускать auto_extend из FastAPI lifespan; не удалять Appointment при
   деактивации/удалении расписания
✅ Auth бизнес-операции АТОМАРНЫ (Stage 31m-fix-b2/b3): registration confirm,
   password reset confirm, change password — одна SessionLocal() + один commit.
   password+revoke sessions (и consume OTP) — в одной транзакции
✅ OTP consume только ПОСЛЕ успешных core DB-изменений, тем же commit
   (validate без удаления; при сбое core-шага OTP не теряется)
✅ Хеш нового пароля считать ДО открытия транзакции (bcrypt медленный)
✅ Новые auth/security изменения требуют failure-injection тестов на реальном
   состоянии БД (см. test_register_confirm_atomic, test_password_uow_atomic)
❌ Не возвращать старую модель «несколько независимых commit в одной auth-операции»
❌ Не выполнять SMTP/email-отправку внутри core DB-транзакции
❌ Не делать system/auth_log уведомления частью core-транзакции — soft-fail после commit
❌ Не добавлять admin/supervisor доступ к chat content без отдельного compliance/security этапа
❌ Не расширять admin-доступ к therapeutic content без отдельного compliance-решения
❌ Не использовать consent_records как суррогат legal basis для staff-ролей
❌ Не писать «админ соглашается за пользователя» / «психолог даёт пациентское согласие»
❌ Не использовать fastapi-users — конфликтует с нашей схемой
❌ Не использовать async SQLAlchemy — проект на sync psycopg2
❌ Не вызывать alembic.command.upgrade() из FastAPI lifespan — deadlock
❌ Не вызывать Base.metadata.create_all() — удалён, схема только через Alembic
✅ Chat attachments хранятся в private directory (`CHAT_FILE_STORAGE_DIR`),
   не в PostgreSQL и не в public static
✅ storage_key формируется на основе UUID — original filename не используется как filesystem path
✅ Скачивание вложений только через auth backend endpoints (permission check участника)
✅ Chromium download flow использует `showSaveFilePicker`; fallback — anchor download.
   Office-файлы должны скачиваться без top-level navigation на `blob:` URL, чат остаётся открытым
✅ Attachment preview реализован только для `image/jpeg`, `image/png`, `image/webp`,
   `application/pdf` через authenticated blob flow: backend download endpoint → `blob` →
   `URL.createObjectURL(blob)` → `AttachmentPreviewLightbox` → cleanup `URL.revokeObjectURL`
✅ Preview не использует public static, прямые `<img src="/api/...">`/`<iframe src="/api/...">`
   на backend endpoint и токены в query string
✅ MVP file policy: разрешены jpg/jpeg, png, webp, pdf, txt, doc/docx, xls/xlsx, ppt/pptx;
   svg, html/htm, js, exe/bat/cmd/com/msi, sh/ps1, php/jar, vbs/scr заблокированы;
   архивы пока не добавлять как реализованные
✅ Аудит для upload/download событий — content файла в audit не пишется
✅ Для orphan-вложений чата есть helper `scripts/cleanup_orphan_attachments.py`:
   dry-run по умолчанию, `--apply` для выполнения, scope — только `message_id IS NULL`
❌ Не писать, что реализован полный cleanup/retention attachments: physical cleanup
   файлов soft-deleted вложений по retention-политике, CLI tests и cron/systemd timer pending
❌ Не отдавать chat attachments через /static/* или StaticFiles — private storage
❌ Не давать admin/supervisor доступ к chat attachments без отдельного compliance-этапа
❌ Не хранить физический файл чата в PostgreSQL (даже как bytea/blob)
❌ Не писать, что реализованы MIME magic bytes (`python-magic`), antivirus/ClamAV,
   Office/TXT preview, thumbnails, PDF.js, S3/MinIO или at-rest encryption физических файлов
✅ Diary content (mood_score, entry_text, selected emotions) хранится encrypted-at-rest
   через enc:v1: в diary_entries.mood_score_enc / entry_text_enc / emotions_enc
✅ Diary API: GET emotions, GET/PUT today, GET entries?limit&offset,
   PATCH/DELETE entries/{entry_uuid}, GET summary?period=14d|month|year;
   только role=student — остальные роли получают 403
✅ PATCH/DELETE: чужая/удалённая/несуществующая запись → 404; malformed UUID → 422;
   DELETE = soft-delete; empty PATCH {} = no-op и не меняет updated_at
✅ Partial UNIQUE (student_id, entry_date) WHERE deleted_at IS NULL:
   после soft-delete можно создать новую запись на ту же дату
✅ Справочник эмоций diary_emotions хранится в БД (не hardcoded на фронте);
   фронт получает [{key, label, sort_order}] через GET /api/diary/emotions
✅ date policy MVP: backend использует date.today() без timezone; сервер должен быть Moscow UTC+3
✅ summary contract: fixed calendar period frame — нет clamp по первой записи;
   period=14d — последние 14 дней (today-13…today), всегда 14 daily points;
   period=month — с 1-го числа текущего месяца до today, quantity=today.day;
   period=year — monthly aggregated, всегда 12 points (Jan–Dec текущего года);
     будущие месяцы (> current month) включены с mood_score=null;
     entries_count = реальные записи (future null-slots не считаются);
   day/month без записи → mood_score=null; нет записей → полный фрейм с all null;
   empty state определяется на фронте по тому, что все mood_score===null;
   year avg = round(avg, 1) → float;
✅ StudentHome: nextStepCard + actionCardsGrid + observationCard только при entriesCount>0;
   fake GAD-7/sleep/anxiety/appointment/psychologist/date удалены
✅ DiaryPage: quick check-in, mood required, emotions/text optional, collapsible details,
   observation summary, history/load more, edit/delete, inline errors;
   frontend today сравнивается по local date
✅ Diary Analytics Lite: /api/diary/summary?period=14d|month|year используется для
   описательной сводки периода — Отметок, Последняя отметка/Последний период, Диапазон,
   последние 3–5 non-null отметок; save/edit/delete обновляют active period
✅ MoodChart и его test suite удалены после manual UI smoke; в diary UI нет SVG, осей,
   линий, trend claims или медицинской/диагностической интерпретации
⚠️ Audit trail для diary edit/delete не реализован; это compliance backlog
❌ Не логировать entry_text, decrypted mood_score, selected emotions из дневника
❌ Не давать psychologist/supervisor/admin доступ к diary content без compliance-этапа
❌ Не смешивать diary с session_notes — разные таблицы, разные маршруты, разная цель
❌ Не хранить selected emotions пользователя как FK в отдельной связующей таблице —
   только encrypted JSON в diary_entries.emotions_enc
✅ Психодиагностика: вопросы теста, по которому есть test_results, НЕ редактируются.
   student_answers ссылается на questions/options через ON DELETE RESTRICT, поэтому
   замена дерева физически невозможна. service.update_test → TestHasResults → HTTP 409;
   routes_admin дополнительно ловит IntegrityError (defense-in-depth). Штатный путь —
   POST /api/admin/tests/{uuid}/duplicate (копия как черновик is_active=false, version=1).
   Метаданные и test_interpretations менять можно: FK из результатов на них нет,
   а расшифровка снапшотится в test_results/test_result_scales при submit
✅ Admin-конструктор шлёт questions/interpretations в PATCH только если они реально
   изменились (dirty-tracking по снапшоту загрузки) — иначе переименование теста
   с результатами упиралось бы в 409 на ровном месте
✅ Шкалы вопросов — правило «все или ни одной»: scoring.compute_result считает тест
   многошкальным, если config["scale"] есть хоть у одного вопроса, и выбрасывает из
   подсчёта остальные (total_score → NULL). Частичное заполнение отвергается
   service._validate_scale_coverage (422) + предупреждение в QuestionBuilder
✅ Покрытие порогов интерпретации — ПРЕДУПРЕЖДЕНИЕ, не 422: правило проверяемо только
   когда известны И вопросы, И пороги, а PATCH частичный (можно прислать одни
   interpretations). service.analyze_test отдаёт score_bounds + issues
   (gap / out_of_range / unknown_scale) через POST /api/admin/tests/analyze;
   конструктор показывает их в TestAnalysisPanel. Не превращать в 422 — правило
   применится наполовину и будет обходиться частичным PATCH
✅ Предпросмотр методики автором: POST /api/admin/tests/analyze (диапазон+пороги) и
   POST /api/admin/tests/preview-score (пробный подсчёт несохранённого дерева).
   Оба НИЧЕГО не сохраняют и объявлены ДО `/{uuid}`-маршрутов (иначе FastAPI примет
   путь за uuid). Вопросы адресуются по question_order, варианты по option_order —
   у несохранённого дерева нет id
✅ Предпросмотр рендерится ТЕМ ЖЕ QuestionRenderer, что и прохождение студентом
   (`src/features/tests/ui/QuestionRenderer.jsx` — общий слой, не под pages/).
   value_score в предпросмотр не передаётся: студент ключа теста не видит
❌ Не дублировать scoring в JS ради «живых» подсчётов в конструкторе — считает только
   app/tests/scoring.py, фронт ходит на analyze/preview-score. Иначе предупреждения
   разойдутся с реальным результатом студента
❌ Не считать «черновик можно посмотреть студенческим аккаунтом»: student-роутер
   закрыт require_role("student"), а get_active_test_full фильтрует is_active=true
✅ student_answers.free_text_answer_enc — Fernet `enc:v1:`, как session_notes/chat.
   На wire (SubmitIn) поле по-прежнему называется free_text_answer; шифрование —
   в storage.save_result. Plaintext не хранить и не логировать
❌ Не возвращать plaintext-колонку free_text_answer и не писать свободный текст
   ответа в audit/logs
❌ Не считать «результаты тестов не шифруются» распространяющимся на free_text:
   решение опиралось на «не свободный терапевтический текст»
❌ Не давать psychologist доступ к результатам тестов (в MVP закрыто осознанно);
   supervisor-просмотр (Этап E) — отдельный этап, и чтение результата обязано писать
   audit-событие по аналогии с session_note_content_read
```

---

### База данных: схема

58 таблиц в 14 доменных модулях. Схема управляется через Alembic.
Миграции: `mindcare_api/alembic/versions/`.

**Миграции (в порядке применения).** Полный rationale каждой ревизии — в
docstring файла миграции (`alembic/versions/<rev>_*.py`); порядок и
родственные связи — `alembic history`. Ниже — только индекс для навигации по
веткам/head'ам:

| Revision | Описание |
|----------|----------|
| `af13ad7a133c` | baseline: 38 таблиц (все кроме audit) |
| `3a7c5e2b8f1d` | add_audit_tables: auth_log, audit_log, data_change_log |
| `c5d8a1b4e7f2` | otp_code_varchar64 |
| `e9a3d7f2b5c0` | rebuild_audit_indexes |
| `f4b9e2c6a1d8` | audit_indexes_and_types |
| `a8c3f1d9e2b5` | add_tags_tables |
| `b3c5e7a9f1d2` | extend_auth_log_event |
| `d2e5f8a1b4c7` | add_supervisor_engagement_index |
| `e5a8f3c1d2b6` | add_normalized_email_unique_index |
| `b6e1f4a7c9d3` | add_user_legal_basis_records (Stage 23b) |
| `d8f3a6c1e9b4` | add_chat_conversations_and_messages (Stage 28b) |
| `c4f7a2e9d1b8` | add_system_conversation_support (Stage 29b) |
| **Ветка psychodiagnostics+chat (dev):** | |
| `f7e9c2a4b8d1` | add_chat_message_edited_at (Stage 31z) |
| `a9b3e1f7c2d4` | add_chat_attachments (Stage 32b) |
| `c1d4e7a2f9b3` | add_test_interpretations — **head A** |
| **Ветка appointments (alex):** | |
| `e1a2b3c4d5f6` | add_appointments_system: meeting_types, group_sessions, appointments |
| `71dfb9c56b13` | add_online_to_appointment_modality |
| `9e193b84bba8` | rework_schedule_slot_model |
| `c9a3f2e1d8b6` | schedule_rule_not_null_break_periods |
| `b2d4f6a8c1e3` | schedule_auto_extend_created_by |
| `d3e6f9a2b5c8` | appointments_booking_source_created_by |
| `f1a4c7e0b9d2` | schedule_rule_meeting_type_optional |
| `a1b2c3d4e5f6` | add_unregistered_student_cards |
| `b7c8d9e0f1a2` | index_card_linked_user_id — **head B** |
| `be8d3ad39b3a` | merge_appointments_and_psychodiagnostics_heads (A+B) |
| **Ветка diary (igor, от `a9b3e1f7c2d4`):** | |
| `b2e4d7f1a9c3` | add_diary_tables |
| `c3a7f8e2d1b9` | update_diary_emotions_catalog |
| `db0b2e177da5` | merge_diary_into_dev_heads |
| **Ветка themes (dev, от `db0b2e177da5`):** | |
| `e7c1a9d4b385` | add_user_ui_theme_prefs |
| **Ветка tests-fix (vb, от `e7c1a9d4b385`):** | |
| `a4f2c8e1b7d9` | encrypt_student_answer_free_text |
| **Ветка email-domains (alex, от `db0b2e177da5`):** | |
| `c7f1a9e4d2b8` | add_allowed_email_domains |
| `27202a87a892` | merge_email_domains_and_ui_theme_heads |
| `3b46b9d94c08` | merge_tests_fix_and_email_domains_theme_heads |
| **Ветка unified audit trail (Stage 2 / Stage 5C):** | |
| `f2a9c4e7b1d8` | add_audit_outcome |
| `a1c4e8b2f7d3` | add_schedule_series_identity (Stage 5C-0A) |
| `b5d7f0a3c9e1` | enforce_schedule_series_fk (Stage 5C-0C) |
| **Ветка minimized data_change_log (Stage 6):** | |
| `d4a7b2c9f6e1` | harden_data_change_log — ⚠ downgrade НЕ восстанавливает legacy-функцию |
| **Ветка IP-анонимизации (Stage 7):** | |
| `c8e2b5f7a3d1` | adopt_ip_anonymization — создаёт `anonymize_old_ips`/`count_old_ips`, ⚠ необратимо (см. «О проекте») |
| **Ветка read-only admin viewer журналов (Stage 8):** | |
| `e6c3a9f1d574` | add_audit_chronological_indexes — **head** |

**Ключевые таблицы:**

| Таблица | Описание |
|---------|----------|
| `users` | Все пользователи системы. FK из всех модулей |
| `roles`, `user_roles`, `permissions`, `role_permissions` | RBAC. Роли через M:N |
| `student_profiles`, `psychologist_profiles` | Профили 1:1 с users |
| `user_sessions` | Сессии (заменяют JWT). Soft-revoke через `is_revoked` |
| `otp_verifications` | OTP для регистрации и сброса пароля. code = SHA-256 хеш |
| `consents`, `consent_records` | Согласия на ПДн (личное согласие субъекта). Обязательны при регистрации |
| `user_legal_basis_records` | Документированное основание организации для admin-created staff-пользователей. Не путать с consent |
| `allowed_email_domains` | Управляемый allowlist точных нормализованных доменов для создания новых аккаунтов; отключённые строки сохраняются для истории и могут быть реактивированы |
| `chat_conversations`, `chat_messages` | Messenger (Stage 28b/29b): `type` engagement/system; engagement-беседа — одна на engagement (UNIQUE), system-беседа — одна на `recipient_id` (partial UNIQUE); `chat_messages.message_kind` user/system, `event_key` для idempotency system-сообщений; content — только `enc:v1:` |
| `chat_attachments` | Вложения чата (Stage 32b): metadata (original_filename, mime_type, file_size, storage_key, checksum, is_image); физический файл — в `CHAT_FILE_STORAGE_DIR` (private FS, не public static); soft delete через `deleted_at`; скачивание только через auth backend endpoint |
| `appointments` | Записи на консультации |
| `unregistered_student_cards` | Карточки walk-in клиентов без аккаунта: минимальные ПДн, consent_source/created_by, archived, optional linked_user_id. Используются supervisor manual booking через `unregistered_student_card_id`; при регистрации/создании аккаунта могут привязаться по normalized_email |
| `meeting_types` | Типы встреч; владеют `duration_minutes` + `buffer_minutes` (по ним строятся слоты), `description`, форматами, `is_group/is_active/is_bookable` |
| `schedule_rules` | Рабочие окна психолога (только доступность; `meeting_type_id` опционален/legacy и НЕ ограничивает тип встречи в schedule v3, `period`, `series_id` для серии rules+breaks, `auto_extend`, `created_by`). Длительность/буфер — НЕ здесь, а в `meeting_types`. Soft-delete/restore расписания — через `is_active` на уровне серии (не трогает Appointment) |
| `schedule_breaks` | Повторяющиеся перерывы по дню недели (например обед 13:00–14:00); вырезают пересекающиеся слоты. Перерыв, созданный вместе с расписанием, разделяет `series_id` и период с правилами |
| `schedule_exceptions` | Разовые изменения на дату: `day_off` / `unavailable` / `extra_availability`; на одну дату допускается несколько (без уникальности) |
| `tests`, `questions`, `options`, `test_results` | Психодиагностика |
| `categories`, `article_categories`, `test_categories` | Типы материалов/категории. В MVP плоские: `parent_id` не используется в Admin CRUD |
| `tags`, `article_tags`, `news_tags`, `test_tags` | Темы/теги контента. M:N с articles, news, tests. Уникальность через `lower(name)` |
| `auth_log`, `audit_log`, `data_change_log` | Три журнала с разделёнными зонами ответственности (см. «Три журнала аудита» ниже). Партиционированы по месяцам; схема — только через Alembic |
| `diary_emotions` | Справочник эмоций дневника: 12 активных состояний (after c3a7f8e2d1b9); key, label, sort_order, is_active; angry/light — деактивированы (is_active=false), legacy labels в DiaryEntryItem.jsx |
| `diary_entries` | Дневник студента: одна активная запись в день (partial UNIQUE по student_id + entry_date WHERE NOT deleted); mood_score_enc, entry_text_enc, emotions_enc — Fernet encrypted; только student |
| `refresh_tokens`, `user_mfa_methods` | NOT IMPLEMENTED. Таблицы зарезервированы. |

> **Партиционирование audit-таблиц:** `auth_log`/`audit_log`/`data_change_log`
> создаются как `PARTITION BY RANGE (created_at)` с начальными партициями 2026-01..2028-12.
> Будущие партиции управляются через `scripts/ensure_audit_partitions.py`.
> Запускать заблаговременно (не из FastAPI). Начиная со Stage 7 скрипт стоит на
> таймере `mindcare-ensure-audit-partitions.timer` (ежемесячно, `--months-ahead 24`).
> Он ТОЛЬКО создаёт недостающие будущие партиции: DROP старых партиций и удаление
> строк журналов в него не входят и требуют отдельного решения DPO.
>
> **IP в этих трёх журналах** обнуляется через 90 дней (`anonymize_old_ips`,
> ревизия `c8e2b5f7a3d1`) — но только если запущен соответствующий job; его
> таймер по умолчанию НЕ активирован, т.к. первый прогон необратим.

### Три журнала аудита: зоны ответственности

Разделение — по зоне ответственности, не по эксклюзивности данных: `audit_log` и
`data_change_log` могут писаться совместно для одной business-операции (Stage 6
generic paired events), но несут непересекающуюся информацию — семантику
действия и перечень изменённых полей соответственно.

| Журнал | Зона | Что НЕ пишется |
|--------|------|----------------|
| `auth_log` | Аутентификация и жизненный цикл сессии: login/failed_login/logout, registration, password change/reset | Роль актора (колонки нет), бизнес-сущности, metadata |
| `audit_log` | Семантические события: **кто** (actor: `user_id`/`user_role`), **над чем** (target: `entity_type`/`entity_id`), **с каким исходом** (`outcome`/`failure_reason_code`). Четыре Stage 6 generic paired events (`meeting_type_updated`, `group_session_updated`, `admin_user_updated`, `unregistered_student_card_updated`) пишут `metadata={}` и получают field-level дополнение через `data_change_log`. Некоторые ДРУГИЕ semantic-события несут минимизированную allowlisted metadata (например `profile_updated.metadata.fields` — имена self-profile полей `users.full_name`/`users.phone`, `admin_role_add/remove/update.metadata` — role diff) | Plaintext content; произвольные ПДн в metadata (только явно allowlisted значения) |
| `data_change_log` | Минимизированный field-level журнал для четырёх generic UPDATE-потоков: **имена каких allowlisted полей** изменились (значения — только per-field opt-in для нечувствительных enum/bool/int; name-only поле может обозначать ПДн, но само значение не копируется) | Семантика действия (она в `audit_log`); значения по умолчанию; свободный текст; ПДн-значения |

**Event REGISTRY: 94 события** (`AUTH_LOG=7`, `AUDIT_LOG=87`) — `app/audit/registry.py`,
единый facade `record_event()`.

**CHANGE_REGISTRY: 4 таблицы / 25 полей** (15 name-only, 10 value-enabled) + 1
derived-поле — `app/audit/change_registry.py`, отдельный writer `record_data_change()`:

| Таблица | paired_event | Полей | value-enabled | derived |
|---------|--------------|-------|---------------|---------|
| `users` | `admin_user_updated` | 2 | — (только `full_name`, `phone`, name-only) | — |
| `unregistered_student_cards` | `unregistered_student_card_updated` | 6 | — (все шесть name-only) | `normalized_email` |
| `meeting_types` | `meeting_type_updated` | 9 | 7 (`duration_minutes`, `buffer_minutes`, `display_order`, `allow_in_person`, `allow_online`, `is_group`, `is_bookable`) | — |
| `group_sessions` | `group_session_updated` | 8 | 3 (`format`, `capacity`, `meeting_type_id`) | — |

**Ровно ЧЕТЫРЕ production call site `record_data_change` (проверяется AST-тестом
`tests/test_data_change_callsites_ast.py`):**
- `app/appointments/storage.py::update_meeting_type`
- `app/appointments/storage.py::update_group_session`
- `app/appointments/storage.py::update_unregistered_student_card`
- `app/users/storage.py::_apply_role_and_scalar_changes`

```
✅ data_change_log — ТОЛЬКО ATOMIC/fail-closed: writer делает исключительно
   db.add в caller-сессию; commit/rollback/close принадлежат владельцу
   бизнес-транзакции. SOFT/fail-open режима не существует
✅ Значения НЕ пишутся по умолчанию: политика поля — name-only, если явно не
   размечено иначе. Штатные Stage 6 call sites для `users` и
   `unregistered_student_cards` всегда передают values=None, поэтому
   создаваемые ими строки имеют old_values/new_values IS NULL — ФИО, телефон,
   email, дата рождения, комментарий и запрос клиента не копируются. Это
   application-инвариант, а не DB-гарантия: исторические строки и
   привилегированный прямой SQL находятся вне него
✅ old/new допускаются только per-field opt-in и только для нечувствительных
   enum/bool/int; registry-инвариант запрещает value-политику любому полю,
   чьё имя срабатывает на denylist (`is_denylisted_key`)
✅ Transition-поля НЕ дублируются в DCL: `users.is_active`, роли,
   `meeting_types.is_active`, `group_sessions.booking_enabled`/`status`
   описаны выделенными событиями audit_log и физически отсутствуют в
   field-allowlist
✅ `normalized_email` — derived-поле: отбрасывается проекцией; смена email даёт
   changed_fields=["email"]. Если изменилось ТОЛЬКО derived-поле — мутация и
   generic audit сохраняются, а DCL-строка не пишется (пустой changed_fields
   запрещён контрактом)
✅ Схема audit-таблиц (включая data_change_log) меняется ТОЛЬКО через Alembic;
   ORM объявляет те же имена ограничений и тот же текст CHECK — расхождение
   ловится drift-тестом
❌ Не писать значения ПДн в old_values/new_values ни при каких обстоятельствах
❌ Не вызывать record_data_change с пустым changed_fields
❌ Не добавлять пятый call site без обновления CHANGE_REGISTRY и AST-теста
❌ Не использовать legacy PostgreSQL-функцию log_data_change() — удалена
   миграцией d4a7b2c9f6e1 (принимала полные old/new и копировала ПДн)
```

> **Природа решения.** `data_change_log` — **техническая мера
> прослеживаемости**, введённая инженерным решением проекта. Это НЕ утверждение
> о прямом требовании ФЗ-152 или иного закона и НЕ утверждение о соответствии
> законодательству: такую оценку даёт DPO/ответственное лицо. Открытые вопросы
> (retention, достаточность name-only, доступ привилегированных
> DB-пользователей, отсутствие correlation_id) — в
> [`docs/BACKLOG.md`](docs/BACKLOG.md); архитектурное обоснование — ADR-021.
> Технический охват IP-анонимизации для этого журнала закрыт Stage 7:
> `data_change_log` входит в неё наравне с `audit_log` и `auth_log`
> (ADR-022); подтверждение самого срока 90 дней остаётся за DPO.

> **Парность `audit_log` ↔ `data_change_log` — caller-инвариант, а НЕ гарантия
> facade или БД.** Строка DCL пишется только рядом с успешным
> `TableSpec.paired_event` в той же транзакции. Инвариант удерживают: статические
> проверки `paired_event` при построении CHANGE_REGISTRY, AST-тест call sites и
> integration-тесты совместного commit/rollback. `correlation_id` намеренно не
> введён — связь восстанавливается по (`entity_type`/`table_name`, id, время).

### Read-only просмотр журналов администратором (Stage 8)

`GET /api/admin/audit/{events,auth-events,data-changes,options}` —
`app/audit/routes_admin.py` → `admin_service.py` → `admin_storage.py`.
Writer-facade `record_event()` остаётся отдельной публичной точкой записи.
Множества, производные от registry (классы актора, допустимые цели, имена
событий/таблиц), живут в `app/audit/admin_policy.py` и импортируются И
storage (SQL-предикаты), И service (проекция DTO) — это структурная гарантия
того, что фильтр и отображение классифицируют строку одинаково.

```
✅ Доступ — только активная membership-роль `admin` через router-level
   require_role("admin"); acting role — resolve_role_or_403(allowed={"admin"}).
   Seed-permissions `admin:audit` / `auth:view_logs` источником авторизации НЕ
   являются: application-level permission enforcement отсутствует
✅ Три журнала — три отдельных эндпоинта. UNION-ленты нет: у них разные
   контракты, разные безопасные DTO, а надёжного correlation_id между
   `audit_log` и `data_change_log` не существует
✅ Окно обязательно: без дат берутся последние 7 календарных дней по
   Europe/Moscow, максимум 90 дней, ровно одна из двух дат → 422. Фильтр по
   `created_at` присутствует в КАЖДОМ запросе — иначе теряется partition pruning
✅ Сортировка только `created_at`, затем `id` (детерминированный tie-break);
   произвольный `sort` не принимается. `size` 1..100, глубина ≤ 100 000
✅ `actor_kind` выводится из `ActorPolicy` конкретного EventSpec/TableSpec, а НЕ
   из «user_id IS NULL ⇒ anonymous»: FK объявлен ON DELETE SET NULL, поэтому
   после физического удаления аккаунта `login`/`logout`/`password_change` тоже
   получают NULL. Для `audit_log`/`data_change_log` дополнительно проверяется,
   что роль строки входит в `allowed_actor_roles` спеки
✅ SQL-предикаты классов актора оборачиваются в `coalesce(expr, false)`:
   без этого `role = 'system'` при NULL даёт NULL, `NOT(...)` — тоже NULL, и
   строка молча выпадает из `unavailable`
✅ `actor.kind = unavailable` ВСЕГДА даёт `details_redacted=true`: этот класс
   возникает только при аномалии (обнулённый `ON DELETE SET NULL` actor_id,
   отсутствующая строка `users`, роль вне allowlist, неизвестное событие).
   `anonymous` и `system` — штатные классы и признака редактирования не дают
✅ Target валидируется против конкретного EventSpec (TargetPolicy + ожидаемый
   `entity_type` + положительный id). Target-фильтры отбирают только
   семантически корректные строки, поэтому повреждённая строка не попадает в
   выдачу и не показывается с пустым target
✅ `validate_metadata()` — НЕ финальная DTO-проекция. Поверх неё закрытый
   `_METADATA_DTO_POLICY`: `linked_user_id` → `linked_user_uuid` (батч-резолв на
   страницу), неклассифицированный ключ отбрасывается. Полнота проверяется на
   импорте модуля, как `build_registry`
✅ Неизвестное/legacy/destination-mismatch событие → `event_code =
   "legacy_unknown_event"`, `known_event=false`, `outcome=null`,
   `failure_code=null`, `target=null`, `details={}`, `details_redacted=true`.
   К `spec` в этой ветке обращаться нельзя — его нет
✅ `/options` вычисляется из живых REGISTRY/CHANGE_REGISTRY: `operations` —
   union реальных `allowed_operations` (сегодня ровно `["UPDATE"]`),
   `actor_kinds` — per-journal producible-набор (для `data_change_log` сегодня
   `["user","unavailable"]`, без `system`). Событие просмотра `/options` не пишет
✅ Просмотр пишет `audit_logs_viewed` (AUDIT_LOG, USER_REQUIRED {admin}, target
   FORBIDDEN, success-only, INDEPENDENT + RAISE) ПОСЛЕ выборки и ДО ответа.
   metadata — только `journal` и `filter_keys` (стабильные ИМЕНА применённых
   фильтров). Сбой записи → 503 без единой строки журнала
✅ `filter_keys`: `date_range` присутствует всегда (окно применяется и по
   умолчанию); применённость определяется через `is not None`, а не по
   истинности — иначе `success=false` не попал бы в журнал; `access_events`
   добавляется только при `include_access_events=true`
✅ Все list-ответы отдают `Cache-Control: no-store, private`; ETag не ставится
❌ Не отдавать внутренний `users.id` ни в ответе, ни в query: цель-человек
   адресуется только `target_user_uuid`, а `entity_ref`/`record_id` для
   пользователя равны null
✅ Целочисленный идентификатор цели допускается ТОЛЬКО с явным
   НЕ-пользовательским типом: `entity_id` требует `entity_type`, `record_id`
   требует `table_name`. Без типа integer неоднозначен и сопоставляется в том
   числе с пользовательскими строками, то есть превращает `users.id` в рабочий
   ключ поиска — перебором можно получить UUID и текущее ФИО. Отдельно
   запрещены `entity_type=user`+`entity_id` и `table_name=users`+`record_id`.
   Все четыре нарушения → 422 ДО обращения к журналам и ДО access-события
❌ Не выбирать из БД `description`, `ip_address`, `user_agent`, `session_id`,
   `request_url`, `request_method`, `mfa_method`, `old_values`, `new_values` —
   запрет структурный: этих полей нет ни в SELECT, ни в схемах DTO
❌ Не отдавать полный email — только `mask_email()`; невалидное значение → `***`
❌ Не добавлять свободный ILIKE по metadata, поиск по email/IP/UA, произвольную
   колонку сортировки, export CSV/Excel/PDF и detail-эндпоинт
❌ Не подставлять роль актора в `auth_log` — этот журнал её не хранит
❌ Не вызывать `record_data_change` из viewer: чтение не является generic UPDATE
❌ Не давать доступ supervisor/psychologist/student и не менять seed/RBAC
```

**Роли в системе:**

| Роль | Кто | Как создаётся |
|------|-----|---------------|
| `student` | Студент/клиент | Публичная регистрация с OTP, либо admin/supervisor через `POST /api/supervisor/students` (очное согласие, consent_records) |
| `psychologist` | Психолог | Только через `POST /api/admin/users` |
| `admin` | Администратор | Только через `POST /api/admin/users` или `scripts/create_admin.py` |
| `supervisor` | Супервизор | Только через `POST /api/admin/users` |

**Multi-role policy (ADR-018):**
- `user_roles` — источник прав доступа. У одного пользователя может быть несколько
  активных ролей одновременно, например `["admin", "supervisor", "psychologist"]`.
- Auth/session/profile API должны возвращать `roles: Role[]`. Поле `role` можно
  временно сохранять как primary/default/effective role для совместимости, но
  backend authorization не должен полагаться только на него.
- Backend `require_role(...)` проверяет пересечение allowed roles с
  `current_user.roles`. Frontend `RoleRoute` проверяет `user.roles`.
- Для экранов и аудита, где важно “в каком кабинете действует пользователь”,
  использовать `active_role`/`effective_role`, валидированный по `user_roles`.
  Клиентский выбор роли — только hint; backend всё равно проверяет membership.
- Admin role edit должен быть set-based: добавлять/удалять конкретные роли, не
  удаляя весь набор `user_roles`. Запрещён destructive replace-all roles.
- Для PATCH отсутствие `roles` означает «не менять роли»; явный `roles: []`
  означает снять все staff-роли. Операция допустима только если у пользователя
  остаётся другая активная роль; оставить аккаунт без ролей нельзя.
- Admin create принимает ровно одно из `role`/`roles[]`; admin list,
  single-read и create response возвращают активные `roles[]` и legacy primary
  `role` (может быть `null` только у аккаунта без активных ролей).
- Добавление staff-роли (`psychologist`, `supervisor`, `admin`) требует
  `user_legal_basis_records`; роль `student` не назначается через admin role
  control без отдельного compliance-решения.
- Пользователь с `admin` + `supervisor` попадает в `/admin/*` по роли `admin`.
  Чистая роль `supervisor` не наследует доступ к admin panel.
- Администратор не может снять у самого себя активную membership-роль `admin`.
  Guard авторитетно работает на backend по стабильному actor/user id; другой
  администратор может изменить этот набор ролей. Самодеактивация и самоудаление
  этим guard не запрещены и требуют отдельного продуктового решения.
- Аккаунт может фактически остаться без активных ролей (единственная роль
  истекла по `expires_at` или снята). Контракт разделён по стадиям:
  - **новый вход отклоняется контролируемым 403**: `service.authenticate_user`
    fail-closed отвергает аккаунт без валидной активной роли ДО
    `update_last_login`/`create_session`; audit — `failed_login` с
    `failure_reason = no_active_roles`, сообщение клиенту обобщённое (состав
    ролей не раскрывается). НЕ 500 и НЕ `internal_error`: это штатный доменный
    отказ, а не авария;
  - **уже выданная сессия остаётся валидной**: `/api/auth/me` отдаёт
    `roles: []`, `role: null`, прикладные эндпоинты дают 403, а `logout`
    обязан отработать 200 — иначе пользователь не смог бы завершить сессию.
  Поэтому audit-facade допускает user-актора с `role=None` **только** для
  событий `Destination.AUTH_LOG` (`auth_log` роль актора не хранит вообще);
  для `AUDIT_LOG` роль по-прежнему обязательна — там она пишется в `user_role`.
  Не подставлять фиктивную роль и не «чинить» logout отказом.
- `internal_error` — только для настоящих внутренних сбоев; `invalid_credentials`
  — только для неверных credentials. Новое событие под `no_active_roles` не
  заводится: это failure reason того же `failed_login` (счётчик registry этим не меняется).

**Email-domain policy для новых аккаунтов (ADR-019):**
- Через HTTP/API новый аккаунт можно создать только с точным нормализованным
  доменом, для которого в `allowed_email_domains` есть активная строка. Отсутствие
  домена в allowlist означает запрет; отдельного denylist нет.
- Политика применяется к self-registration, admin-created staff и
  supervisor/admin-created student. В registration flow ранняя проверка выполняется
  до отправки OTP, а authoritative проверка — в транзакции confirm до consume OTP.
- Существующие пользователи с доменом, который отсутствует или был отключён,
  сохраняют login и password reset. Политика не является ретроактивной блокировкой.
- Реактивация soft-deleted пользователя считается созданием/возвратом аккаунта и
  требует активного домена.
- Admin API: `GET/POST/PATCH /api/admin/email-domains`; физического DELETE нет.
  Повторный POST существующего отключённого домена даёт 409, реактивация делается
  только PATCH `is_active=true`. Последний активный домен отключить нельзя.
- Это управляемая организационная политика проекта, а не утверждение об
  официальном или исчерпывающем государственном перечне почтовых сервисов.
- `scripts/create_admin.py` — отдельный локальный bootstrap/ops path и сейчас не
  проверяет allowlist. Не использовать его как обычный account-creation API.


### Соглашения по коду: Backend

Структура модуля — см. «Backend: структура модулей» выше (`routes.py` /
`schemas.py` / `service.py` / `storage.py`).

**Pydantic-схемы:**
```python
# Всегда раздельные схемы для разных операций
class UserCreate(BaseModel): ...   # входящие данные
class UserUpdate(BaseModel): ...   # частичное обновление
class UserRead(BaseModel): ...     # исходящие данные

# UserRead НИКОГДА не содержит password_hash или другие чувствительные поля
# model_config = {"from_attributes": True} — для создания из SQLAlchemy-моделей
```

**Защита эндпоинтов:**
```python
# Защита на уровне роутера (предпочтительно) — нельзя забыть на новом эндпоинте
router = APIRouter(
    prefix="/admin/users",
    dependencies=[Depends(require_role("admin"))],
)

# Не защищать только на фронте — всегда на бэке
```

**Работа с БД:**
```python
# Всегда with SessionLocal() as db — автозакрытие сессии
with SessionLocal() as db:
    ...

# db.flush() перед db.commit() если нужен id до коммита
# db.refresh(obj) после commit() если поля генерирует БД (uuid, created_at)

# Soft delete — никогда не удалять физически через основные таблицы
db.query(User).filter(...).update({"deleted_at": datetime.now(timezone.utc)})
```

**Email:**
```python
# Все отправки через BackgroundTasks — не блокировать HTTP-ответ
bg.add_task(send_registration_otp, user.email, code)

# EMAIL_MODE=dev — печатает в stdout, не шлёт реально (для разработки)
# EMAIL_MODE=smtp — реальная отправка
```

**Порядок импортов:**
```python
# 1. Стандартная библиотека
import secrets
from datetime import datetime

# 2. Сторонние пакеты
from fastapi import APIRouter
from sqlalchemy.orm import Session

# 3. Внутренние модули
from app.db.session import SessionLocal
from app.auth.deps import require_role
```

**Audit-impact review и диагностическое логирование:**

Каждый новый backend-сценарий (endpoint, service/storage mutation, security-
проверка, чтение чувствительного content или maintenance-job) ОБЯЗАН до
реализации получить явное решение по audit impact: какое событие пишется либо
почему событие не требуется. Отсутствие события допустимо для обычного чтения,
валидации до бизнес-операции и истинного no-op, но не должно быть результатом
молчаливого пропуска анализа.

```text
1. Проверить существующий app/audit/registry.py; динамические event_type запрещены.
2. Если события нет — сначала добавить EventSpec и его exact-contract тесты.
3. Писать событие только через app.audit.record_event(); прямые
   AuditLog/AuthLog/DataChangeLog и legacy app.auth.audit.log_auth_event запрещены.
4. ATOMIC-success стейджить в caller-сессии до единственного commit; режимом
   транзакции и failure policy владеет registry, caller их не переопределяет.
5. Ожидаемый business-failure писать только типизированным стабильным code через
   record_secondary_failure(), если такой failure-event предусмотрен registry.
   Commit/postcommit/неожиданные сбои не маскировать ложным business outcome.
6. Для generic UPDATE отдельно решить, нужен ли data_change_log. Новый call site
   требует CHANGE_REGISTRY + AST/integration-тестов; значения ПДн запрещены.
7. metadata/description/context минимизировать: никаких паролей, OTP, токенов,
   ciphertext, plaintext content, свободного текста исключений и произвольных ПДн.
8. Тестами зафиксировать actor/target/outcome, точную metadata, отсутствие утечек,
   no-op semantics и commit/rollback boundary.
```

Подробная каноника журналов и транзакций — в разделе «Три журнала аудита» выше.
Для технической диагностики сохранять принятый минимизированный формат
`event/phase/error-class`; не выводить `str(exc)`, SQL, credentials, id или ПДн.


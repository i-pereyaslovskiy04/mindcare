# ФЗ-152 Compliance Checklist

Статус выполнения требований ФЗ-152 «О персональных данных» для платформы MindCare.
Последнее обновление: 2026-08-20.

Этот документ фиксирует техническое состояние реализации и открытые вопросы.
Он не является юридическим заключением и сам по себе не подтверждает
соответствие требованиям законодательства; итоговую оценку даёт
DPO/ответственное лицо.

---

## ✅ Реализовано

### Согласие на обработку ПДн
- При регистрации студента фиксируется согласие в `consent_records`
- Таблицы `consents` (версии политик) и `consent_records` (факты согласия) в БД
- Перед регистрацией проверяется наличие актуальных политик
- `consent_records` self-registration фиксируют контекст запроса — IP-адрес и
  User-Agent (Stage 31m-fix-b1: `register/confirm` route передаёт их в storage);
  запись согласий происходит атомарно с созданием пользователя (Stage 31m-fix-b2)

### Legal basis для admin-созданных пользователей (Stage 23b)
Разделение двух сущностей:
- **Personal consent** (`consent_records`) — личное согласие субъекта
  (студент сам принимает политику при регистрации). Никто не может
  «согласиться за пользователя».
- **Organization legal basis** (`user_legal_basis_records`) — документированное
  основание организации для создания учётной записи и обработки ПДн
  сотрудника (трудовой договор, служебная необходимость, приказ, договор,
  административное назначение, иное).

Реализация:
- self-registration студента → `consent_records` (личное согласие субъекта),
  основание организации НЕ создаётся;
- `POST /api/admin/users` (создание staff) принимает ровно одно из legacy
  `role` или `roles[]`; только `psychologist`/`supervisor`/`admin`, без
  `student`. `legal_basis_confirmed=true`, валидный `basis_type` и непустой
  `basis_reference` обязательны (иначе 422); reference trim-ится. На каждую
  уникальную создаваемую staff-роль в одной транзакции с User/UserRole
  создаётся отдельная запись в `user_legal_basis_records` с actor admin id, IP,
  user-agent и metadata `action="user_create"`/`created_role`/`roles_after`;
- `PATCH /api/admin/users/{uuid}` / role-management endpoint при добавлении новой
  staff-роли (`psychologist`/`supervisor`/`admin`), которой у пользователя ещё нет,
  тоже требует документированного основания:
  `legal_basis_confirmed=true` + валидный `basis_type` + непустой `basis_reference`
  (иначе роль не добавляется; 400, либо 422 на невалидный basis_type); добавление роли
  и запись основания атомарны; `metadata` фиксирует `action="role_add"`, `added_role`,
  `roles_before`, `roles_after`;
- удаление staff-роли не требует нового legal basis, но требует audit trail; старые
  `user_legal_basis_records` не удаляются как historical record;
- в admin PATCH отсутствие поля `roles` означает, что роли не меняются; явный
  `roles: []` является целевым пустым staff-набором и снимает все staff-роли только
  если после операции остаётся другая активная роль (например, `student`). Оставить
  пользователя без активных ролей нельзя — backend возвращает 422;
- админ НЕ создаёт consent от имени пользователя ни в create, ни в PATCH;
- роли доступны в admin edit-модалке как multi-role control, но `student`
  НЕ назначается через admin role control — студенты появляются через
  self-registration или staff-created student flow `POST /api/supervisor/students`
  (их личное согласие — `consent_records`); при добавлении staff-роли UI требует
  подтвердить документированное основание;
- UI-формулировка при создании: «Подтверждаю наличие документированного основания
  для создания учётной записи и обработки персональных данных пользователя»;
- UI-формулировка при добавлении staff-роли: «Подтверждаю наличие документированного основания
  для назначения этой роли и обработки персональных данных» (НЕ «согласие пользователя»)
- `scripts/create_admin.py` пишет legal basis (`basis_type=bootstrap`)
  и больше НЕ создаёт consent_records за пользователя
- `scripts/backfill_legal_basis.py` — backfill для существующих staff-юзеров
  (`--dry-run` по умолчанию)
- Исторические bootstrap consent_records (`user_agent='bootstrap-script'`)
  не удалялись — оставлены как historical record

### Multi-role пользователи и compliance (ADR-018)
- Один пользователь может иметь несколько активных ролей одновременно через `user_roles`.
  Это не даёт роли-наследования: например, `supervisor` не получает `/admin/*` без
  отдельной membership-роли `admin`.
- Для чувствительных контуров (`session_notes`, chat, diary, test results) policy должна
  смотреть не на legacy `role`, а на validated `roles` + `effective_role`/активный кабинет.
- `effective_role` влияет на audit wording и policy branch, но не может расширять доступ
  сверх membership-ролей в `user_roles`.
- Frontend `activeRole` хранится только как UI preference выбора кабинета. Он не
  является доказательством полномочий, очищается вместе с auth session и всегда
  сверяется с `roles[]`.
- Если endpoint принимает явный role context (например, `X-Active-Role` для
  session notes), backend обязан отклонять неизвестную или отсутствующую у
  пользователя роль с 403, а не делать тихий fallback на primary role.
- Роль `student` остаётся связанной с личным consent субъекта. Добавление `student` к
  существующему staff-пользователю через admin UI/API не разрешено без отдельного
  compliance-решения.
- Администратор не может снять у самого себя активную membership-роль `admin`.
  Проверка выполняется на backend по actor/target id; frontend lock не считается
  рубежом безопасности. Другой администратор может изменить роли. Самодеактивация
  и самоудаление этим правилом не покрыты.

### Allowlist email-доменов для новых аккаунтов (ADR-019, 2026-07-16)
- `allowed_email_domains` хранит управляемый список точных нормализованных доменов.
  Новый аккаунт разрешён только при наличии активной строки; отсутствие домена в
  списке означает запрет. Отдельного denylist нет.
- Политика применяется ко всем HTTP/API путям создания аккаунта: self-registration,
  `POST /api/admin/users` и `POST /api/supervisor/students`.
- В self-registration ранняя проверка выполняется до создания/отправки OTP;
  authoritative проверка повторяется внутри транзакции confirm до consume OTP.
  Если домен отключили между init и confirm, confirm возвращает 422, а OTP не
  потребляется.
- Существующие пользователи с отсутствующим или отключённым доменом сохраняют
  login и password reset. Политика не применяется ретроактивно к действующим
  аккаунтам. Реактивация soft-deleted пользователя требует активного домена.
- Управление доступно только `admin` через `GET/POST/PATCH
  /api/admin/email-domains`. Физического DELETE нет; отключённый домен
  реактивируется PATCH `is_active=true`. Последний активный домен отключить нельзя.
- Add/disable/reactivate/update фиксируются в `audit_log`. Сырой admin comment в
  audit metadata не копируется, потому что в нём могут случайно оказаться ПДн;
  metadata остаётся пустой, target определяется через
  `entity_type="allowed_email_domain"` / `entity_id`.
- Начальный seed — техническая стартовая конфигурация. Динамический allowlist
  является организационной политикой MindCare и не должен описываться как
  официальный, исчерпывающий или автоматически следующий из закона перечень
  российских/иностранных почтовых сервисов. Юридическое обоснование состава списка
  должно отдельно подтверждаться ответственным лицом организации.
- Локальный `scripts/create_admin.py` является privileged bootstrap/ops path и
  сейчас не проверяет allowlist. Его нельзя использовать как обычный путь создания
  пользователей; оператор развёртывания обязан вручную выбрать разрешённый
  организацией домен. Усиление bootstrap-проверки — отдельная hardening-задача.

### Создание аккаунта студента силами staff (2026-06-23)
Помимо self-registration и карточки незарегистрированного студента, admin/supervisor
может создать **полноценный** аккаунт студента через `POST /api/supervisor/students`
(временный пароль, как `POST /api/admin/users`).

Правовое основание обработки ПДн:
- **личное согласие субъекта**, полученное ОЧНО (`consent_records`) — staff
  подтверждает `personal_data_consent` («студент лично дал согласие»), как у карточки
  незарегистрированного студента; это НЕ «согласие за пользователя»;
- **НЕ** `user_legal_basis_records` — legal basis остаётся механизмом только для
  staff-ролей (psychologist/supervisor/admin); студент — субъект, у него consent;
- ответственность сотрудника фиксируется в `audit_log` (`supervisor_create_student`;
  при назначении психолога — `supervisor_assign_psychologist`), т.к. `consent_records`
  не хранит actor.

Реализация:
- core-запись атомарна: `User` + `UserRole(student)` + `ConsentRecord[]`
  (privacy_policy + data_processing) + опц. active `TherapyEngagement` + audit-event
  в одной транзакции/одном commit; audit стейджится через facade и не swallow'ится
  (его сбой откатывает всю запись); сбой валидации психолога не оставляет
  студента-orphan;
- `consent_records.ip_address/user_agent` = контекст запроса staff, в котором согласие
  внесено (личность actor — в `audit_log`);
- post-commit (soft-fail): привязка карточки незарег. студента по `normalized_email`,
  welcome-письмо (нейтральный текст, без staff-специфики), system-уведомления;
- временный пароль и ПДн не логируются (только HTTP-ответ авторизованному caller и
  тело письма; в `EMAIL_MODE=dev` тело письма печатается в stdout — как все OTP/welcome).

### Записи, walk-in карточки и групповые занятия (2026-06-27)
- `appointments` хранит факт записи на консультацию и может ссылаться либо на
  зарегистрированного студента (`client_id`), либо на walk-in карточку
  (`unregistered_student_card_id`); CHECK constraint допускает ровно один субъект записи.
- `unregistered_student_cards` хранит минимальные ПДн walk-in клиента и факт очного
  согласия; карточка может позже привязаться к аккаунту по `normalized_email`, но
  автоматически не объединяется с другими карточками.
- Ручная запись supervisor'ом создаёт обычную индивидуальную запись в
  `pending_confirmation`; психолог всё равно должен подтвердить/отклонить встречу.
- Групповые занятия (`group_sessions`) не являются group chat: это события/записи.
  Group chat и waitlist не реализованы и требуют отдельного compliance/security решения.
- Автопродление расписаний выполняется только maintenance-скриптом
  `scripts/extend_schedules.py`; DDL/фоновые scheduler-задачи не запускаются из FastAPI lifespan.

### Хранение данных
- Все данные хранятся в PostgreSQL на серверах в РФ
- Пароли хранятся как bcrypt-хеш — plaintext нигде не сохраняется
- OTP-коды хранятся как SHA-256 хеш (`otp_verifications.code`)

### Шифрование заметок сессий (`session_notes.content`)
- Application-layer Fernet encryption (`AES-128-CBC + HMAC-SHA256`)
- Реализовано в `app/core/encryption.py`; ключ через `DATA_ENCRYPTION_KEY` env-переменную
- Ciphertext с префиксом `enc:v1:` хранится в TEXT-колонке без изменения схемы БД
- encrypt-on-write / decrypt-on-read в `app/session_notes/storage.py`
- Plaintext fallback намеренно отсутствует; ORM-объект не мутируется plaintext
- Снижает риск хранения психологических данных (специальная категория ПДн) в открытом виде
- **Операционное требование:** `DATA_ENCRYPTION_KEY` должен быть настроен и резервно скопирован
  отдельно от бэкапов БД; потеря ключа = невозможность восстановить заметки

### Политика доступа к `session_notes` (Stage 25b)
Encryption-at-rest защищает от утечки БД; политика доступа защищает
от избыточно широких ролей приложения:
- **psychologist** — создаёт/читает/обновляет только свои заметки (с content)
- **supervisor** — список: metadata-only; чтение конкретной заметки: content
  разрешён, но **каждое такое чтение пишется в `audit_log`**
  (`session_note_content_read`: actor, role, target note id, IP/UA; metadata пустая)
- **admin** — metadata-only везде (`content_available: false`);
  расшифрованный терапевтический content админу не предоставляется;
  metadata-путь вообще не вызывает decrypt
- **student** — доступа нет (403)
- Для multi-role пользователя ветка policy выбирается по validated `effective_role`
  текущего endpoint/cabinet, а не по legacy primary `role`. Например, пользователь
  `admin` + `psychologist` не должен случайно получить admin metadata-only поведение
  на psychologist endpoint или supervisor content-read поведение без supervisor context.
- create/update заметок также логируются (`session_note_created` /
  `session_note_updated`)
- Audit-записи не содержат plaintext content (хелпер принимает только
  идентификаторы — content не попадает в сигнатуру by design)
- Future: supervision-scope модель (сужение зоны супервизора);
  break-glass admin access — только отдельным compliance-решением

### Шифрование и доступ к переписке (`chat_messages.content`)
- Содержимое one-to-one чата — чувствительные психологические данные
- `chat_messages.content` шифруется at-rest через Fernet (`enc:v1:`) тем же
  `DATA_ENCRYPTION_KEY`, который защищает `session_notes`
- Доступ к plaintext есть только у student и psychologist — участников
  соответствующего `therapy_engagement`
- Admin и supervisor не имеют доступа к chat content в MVP
- Plaintext сообщений нельзя писать в application logs или audit; audit-событие
  `chat_conversation_created` содержит только идентификаторы
- **System conversation** (уведомления MindCare): system-сообщения **могут содержать
  персональные данные** (например имя назначенного психолога), поэтому `chat_messages` с
  `message_kind='system'` шифруются at-rest тем же ключом; publisher не логирует
  plaintext (только тип ошибки + `event_key`); это read-only feed получателю, а не
  замена `audit_log`
- **Presence** (`peer_is_online`): вычисляется только по `user_sessions.last_active`
  (приблизительный статус, порог 10 минут); не раскрывает содержимое и не пишет
  «был N минут назад» / last-seen-метку
- Staff break-glass access требует отдельного compliance/security этапа
- **Удаление сообщения** (Stage 31y/31y-hotfix): только soft delete — физического
  удаления строки `chat_messages` нет, шифротекст и техническая запись остаются
  для audit/security; участникам удалённое сообщение не показывается (без
  placeholder-текста в UI); правило **«Право на удаление данных»** ниже (нет
  полного erasure-механизма по запросу субъекта) применимо и к chat-сообщениям
- **Group chat — postponed**: до реализации требуется отдельный design audit,
  включая access policy и encryption policy для групповых сообщений
- **Attachments/files — реализованы (Stage 32b–32j + hotfixes)**: upload/download/preview вложений в
  engagement chat. Реализованные меры безопасности: original filename не используется
  как filesystem path (storage_key на основе UUID); path traversal guard в storage;
  скачивание только через auth endpoint с проверкой membership; MIME allowlist +
  extension blocklist; размер ограничен; audit событий upload/download (без content файла).
  MVP file policy: разрешены jpg/jpeg, png, webp, pdf, txt, doc/docx, xls/xlsx, ppt/pptx;
  svg/html/htm/js, executable/script extensions (`exe`, `bat`, `cmd`, `com`, `msi`, `sh`,
  `ps1`, `php`, `jar`, `vbs`, `scr`) заблокированы; архивы (`zip`, `rar`, `7z` и т.п.)
  пока не разрешены. Chromium download использует safe save flow через `showSaveFilePicker`,
  fallback — anchor download; Office attachments скачиваются без top-level navigation на `blob:` URL.
  Preview разрешён только для `image/jpeg`, `image/png`, `image/webp`, `application/pdf` и
  использует тот же authenticated backend download path, что и скачивание: после successful fetch
  frontend создаёт временный `URL.createObjectURL(blob)` и очищает его через `URL.revokeObjectURL`.
  Public static serving, прямые `<img src="/api/...">`/`<iframe src="/api/...">` на backend endpoint
  и токены в query string не используются. Office/TXT/SVG/unknown MIME остаются download-only.
  Closed/archive чат: upload запрещён (409), download разрешён участникам.
  System conversation: upload запрещён, download не предусмотрен.
  Admin/supervisor: нет доступа к chat attachments (403).
  **Pending compliance/security:** MIME magic bytes validation (`python-magic` не реализована);
  antivirus/ClamAV scanning; at-rest encryption физических файлов в FS (MVP хранит
  файлы unencrypted на диске — только metadata encrypted через Fernet не применяется к FS);
  S3/MinIO с server-side encryption; retention policy для attachment files.
  Orphan cleanup helper `scripts/cleanup_orphan_attachments.py` существует для записей
  `message_id IS NULL` и работает в dry-run/`--apply` режиме, но не заменяет полноценную
  retention policy. Физическое удаление файлов soft-deleted attachments по retention-политике,
  cleanup CLI tests и cron/systemd timer остаются pending / production-hardening.
- Retention policy для chat messages остаётся открытым продуктовым и
  compliance-вопросом

### Шифрование и доступ к дневнику студента (`diary_entries`)
- Дневник студента содержит чувствительные психологические self-report данные:
  mood score (самооценка настроения 1–10), произвольный текст, выбранные эмоции
- `diary_entries.mood_score_enc`, `entry_text_enc`, `emotions_enc` хранятся
  encrypted-at-rest через Fernet (`enc:v1:`), тот же `DATA_ENCRYPTION_KEY`
  (используется также для `session_notes` и `chat_messages`)
- Справочник эмоций (`diary_emotions`) — открытые метаданные (key/label), не ПДн
- Доступ к дневнику — **только student** (роль самого субъекта данных);
  psychologist, supervisor, admin получают 403 на всех diary-эндпоинтах
- Plaintext mood score, entry_text, selected emotions **не пишутся в application logs и audit**;
  summary расшифровывает только `mood_score` для построения агрегатов
- UI «Самонаблюдение» показывает только описательную self-report сводку периода:
  количество отметок, последнюю отметку/период, диапазон и недавние заполненные значения
- Сводка не является диагностикой: нет medical/risk score, labels «норма/отклонение»,
  выводов об улучшении или ухудшении и автоматической клинической интерпретации
- Audit trail для diary edit/delete сейчас **не реализован** и остаётся
  compliance-hardening backlog перед production; при реализации в audit допустимы только
  идентификаторы и метаданные операции, без plaintext diary content
- Доступ психолога к дневнику студента требует отдельного compliance-решения, consent
  субъекта и visibility policy — **не реализовывать без отдельного этапа**
- Export дневника (CSV/PDF) — потенциальный риск утечки; при реализации требует
  отдельной политики, явного legal basis/consent и аудита
- MVP date policy: backend использует `date.today()` без timezone; при многозональном
  деплое нужен user-timezone header

### Аудит auth-событий (`auth_log`)
Все события пишутся через единый `app.audit.record_event()` и закрытый registry;
legacy-модуль `app/auth/audit.py` удалён. В `auth_log` находятся ровно семь
канонических событий аутентификации и жизненного цикла сессии:

| События | Семантика |
|---------|-----------|
| `registration_succeeded`, `registration_failed` | результат регистрации |
| `login`, `failed_login`, `logout` | жизненный цикл сессии |
| `password_change`, `password_reset` | изменение/сброс пароля |

Admin CRUD, роли, self-profile и прочие бизнес-события пишутся в `audit_log`, где
`user_id`/`user_role` — actor, а `entity_type`/`entity_id` — target. UUID не
кодируется в `event_type`; ожидаемые business-failure используют стабильные
`failure_reason_code`. Каноника — ADR-006 (SUPERSEDED) и текущий audit registry.

### Soft delete
- Физического удаления пользователей нет — только `deleted_at + is_active=False`
- При soft delete отзываются все активные сессии пользователя

### Анонимизация IP (Stage 7)
- Охват — **только три audit-журнала**: `audit_log`, `auth_log`, `data_change_log`.
  `user_sessions`, `consent_records`, `user_legal_basis_records` НЕ затрагиваются:
  там IP другого назначения (активная сессия, доказательство согласия,
  документированное основание), и решение по ним остаётся за DPO
- Механизм: `public.anonymize_old_ips(integer)` (ревизия `c8e2b5f7a3d1`) обнуляет
  `ip_address` строк старше границы; парная `public.count_old_ips(integer)` —
  строго read-only счётчик для dry-run
- **Анонимизация не выполняется сама по себе.** Функцию вызывает
  `scripts/anonymize_old_ips.py`; его таймер `mindcare-anonymize-ips.timer`
  `deploy.sh` устанавливает, но **не активирует** — первый прогон необратим.
  Пока таймер не включён оператором, IP хранятся бессрочно
- Историческая справка: до Stage 7 функция существовала только в legacy
  bootstrap-SQL (`db/sql/`), не входила в Alembic-цепочку и не имела ни одного
  вызывающего. На стендах, развёрнутых через Alembic, 90-дневная анонимизация
  фактически **не происходила**, хотя документация её обещала
- Источник IP — `request.client.host`. За reverse-proxy это адрес прокси, а не
  конечного пользователя; доверенные прокси (`X-Forwarded-For` / `X-Real-IP`) —
  отдельный этап, см. `docs/BACKLOG.md`
- Порядок ввода в эксплуатацию и мониторинг —
  [`deploy/STAGE_7_DEPLOYMENT.md`](../deploy/STAGE_7_DEPLOYMENT.md)

### Сессии (Stage 22b — hashed tokens)
- Сессии хранятся в `user_sessions`, не в JWT
- В `user_sessions.id` хранится только SHA-256 hash токена (hash-on-lookup);
  значение из дампа БД нельзя использовать как Bearer credential
- Новые `auth_log.session_id` содержат hash, не raw token
- Мягкий отзыв через `is_revoked=True` без физического удаления
- Остаток (отдельные maintenance-этапы): зачистка legacy plaintext-строк
  `user_sessions` и маскирование исторических `auth_log.session_id`

### Rate limiting auth-эндпоинтов (Stage 21)
- Login / register init+confirm / password reset init+confirm защищены
  sliding-window лимитером (`app/core/rate_limit.py`): лимиты по IP
  и нормализованному email, 429 без раскрытия существования аккаунта
- MVP-ограничение: per-process state; для multi-worker production — Redis
  (отдельный этап)

---

## ❌ Не реализовано (нарушения)

### ~~Согласие для admin-созданных пользователей~~ ✅ Закрыто (Stage 23b)
- Переформулировано: для psychologist/supervisor/admin это не «согласие»,
  а документированное основание организации — см. раздел
  «Legal basis для admin-созданных пользователей» выше
- Реализовано через `user_legal_basis_records`; создание пользователя
  без подтверждения основания невозможно (422)
- Backfill существующих пользователей: `scripts/backfill_legal_basis.py`
  (`--apply` на момент Stage 23b не запускался)

---

## ⚠️ Частично реализовано / требует улучшения

### ~~Аудит admin-операций~~ ✅ Закрыто (Stages 3–6)
- Actor и target разделены структурно в `audit_log`; `target_user_id` в
  `auth_log` не требуется.
- Success и ожидаемые типизированные failure-события используют стабильный
  registry и `outcome`/`failure_reason_code`.
- Generic UPDATE пользователей дополнительно пишет только имена allowlisted
  изменённых полей в минимизированный `data_change_log`; значения ПДн не копируются.

### Партиции audit-таблиц
- Начальные партиции 2026-01..2028-12 созданы миграцией `3a7c5e2b8f1d`
- Будущие партиции управляются через `scripts/ensure_audit_partitions.py --months-ahead 24`
- Начиная со Stage 7 ежемесячный `mindcare-ensure-audit-partitions.timer`
  устанавливается и автоматически активируется через `deploy.sh`; скрипт только
  создаёт будущие партиции и не удаляет старые строки/партиции
- Статус: закрыто в `BACKLOG.md §🔴`

### Право на удаление данных
- Soft delete реализован, но физического удаления нет
- Механизма полного удаления данных по запросу субъекта не существует

---

## Области ПДн в системе

| Данные | Таблица | Чувствительность |
|--------|---------|-----------------|
| ФИО, email, телефон | `users` | Базовые ПДн |
| ФИО, email, телефон walk-in клиента | `unregistered_student_cards` | Базовые ПДн |
| Результаты тестов | `test_results` | Специальные категории |
| Заметки сессий | `session_notes` | Специальные категории |
| Переписка student ↔ psychologist | `chat_messages` | Специальные категории |
| Вложения чата (metadata + файл на FS) | `chat_attachments` + `CHAT_FILE_STORAGE_DIR` | Специальные категории |
| Дневник студента (mood, текст, эмоции) | `diary_entries` | Специальные категории |
| Записи на консультации | `appointments` | Базовые ПДн |
| IP-адреса (audit-журналы) | `auth_log`, `audit_log`, `data_change_log` | Обнуляются через 90 дней — но ТОЛЬКО при включённом `mindcare-anonymize-ips.timer` (по умолчанию не активирован) |
| IP-адреса (вне audit-журналов) | `user_sessions`, `consent_records`, `user_legal_basis_records`, `refresh_tokens` | НЕ анонимизируются; хранятся бессрочно. Политика — открытый вопрос DPO |

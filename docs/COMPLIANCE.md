# ФЗ-152 Compliance Checklist

Статус выполнения требований ФЗ-152 «О персональных данных» для платформы MindCare.
Последнее обновление: 2026-06-16.

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
- `POST /api/admin/users` (создание staff) требует `legal_basis_confirmed=true` (иначе 422);
  запись `user_legal_basis_records` создаётся в одной транзакции с пользователем
  (basis_type, basis_reference, actor admin id, IP, user-agent)
- `PATCH /api/admin/users/{uuid}` со сменой роли на staff (`psychologist`/`supervisor`/
  `admin`, при `old_role != new_role`) тоже требует документированного основания:
  `legal_basis_confirmed=true` + валидный `basis_type` + непустой `basis_reference`
  (иначе роль не меняется; 400, либо 422 на невалидный basis_type); смена роли и запись
  основания атомарны; `metadata` фиксирует `action="role_change"`, `old_role`, `new_role`;
- переход `staff → student` основания не требует и старые `user_legal_basis_records` не удаляет;
- админ НЕ создаёт consent от имени пользователя ни в create, ни в PATCH;
- смена роли доступна в admin edit-модалке (Stage 31n / 31n-hotfix), но `student`
  НЕ назначается через admin role-dropdown — студенты появляются только через
  self-registration (их личное согласие — `consent_records`); при смене роли на
  staff/admin UI требует подтвердить документированное основание;
- UI-формулировка при создании: «Подтверждаю наличие документированного основания
  для создания учётной записи и обработки персональных данных пользователя»;
- UI-формулировка при смене роли: «Подтверждаю наличие документированного основания
  для назначения этой роли и обработки персональных данных» (НЕ «согласие пользователя»)
- `scripts/create_admin.py` пишет legal basis (`basis_type=bootstrap`)
  и больше НЕ создаёт consent_records за пользователя
- `scripts/backfill_legal_basis.py` — backfill для существующих staff-юзеров
  (`--dry-run` по умолчанию)
- Исторические bootstrap consent_records (`user_agent='bootstrap-script'`)
  не удалялись — оставлены как historical record

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
  (`session_note_content_read`: actor, role, note id, author_id, IP/UA)
- **admin** — metadata-only везде (`content_available: false`);
  расшифрованный терапевтический content админу не предоставляется;
  metadata-путь вообще не вызывает decrypt
- **student** — доступа нет (403)
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
- **Attachments/files — реализованы (Stage 32b–32g + hotfixes)**: upload/download вложений в
  engagement chat. Реализованные меры безопасности: original filename не используется
  как filesystem path (storage_key на основе UUID); path traversal guard в storage;
  скачивание только через auth endpoint с проверкой membership; MIME allowlist +
  extension blocklist; размер ограничен; audit событий upload/download (без content файла).
  MVP file policy: разрешены jpg/jpeg, png, webp, pdf, txt, doc/docx, xls/xlsx, ppt/pptx;
  svg/html/htm/js, executable/script extensions (`exe`, `bat`, `cmd`, `com`, `msi`, `sh`,
  `ps1`, `php`, `jar`, `vbs`, `scr`) заблокированы; архивы (`zip`, `rar`, `7z` и т.п.)
  пока не разрешены. Chromium download использует safe save flow через `showSaveFilePicker`,
  fallback — anchor download; Office attachments скачиваются без top-level navigation на `blob:` URL.
  Closed/archive чат: upload запрещён (409), download разрешён участникам.
  System conversation: upload запрещён, download не предусмотрен.
  Admin/supervisor: нет доступа к chat attachments (403).
  **Pending compliance/security:** MIME magic bytes validation (`python-magic` не реализована);
  antivirus/ClamAV scanning; at-rest encryption физических файлов в FS (MVP хранит
  файлы unencrypted на диске — только metadata encrypted через Fernet не применяется к FS);
  S3/MinIO с server-side encryption; retention policy для attachment files;
  physical file cleanup для soft-deleted записей (скрипт существует, не запускается автоматически)
- Retention policy для chat messages остаётся открытым продуктовым и
  compliance-вопросом

### Аудит auth-событий (`auth_log`)
Логируются через `log_auth_event` из `app/auth/audit.py`:

| Событие | Где логируется |
|---------|----------------|
| `register` | `auth/routes.py` |
| `login` | `auth/routes.py` |
| `failed_login` | `auth/routes.py` |
| `logout` | `auth/routes.py` |
| `password_reset` | `auth/routes.py` |
| `password_change` | `auth/routes.py` |
| `admin_create_user:{uuid}` | `users/routes_admin.py` |
| `admin_update_user:{uuid}` | `users/routes_admin.py` |
| `admin_delete_user:{uuid}` | `users/routes_admin.py` |

UUID цели закодирован в строке события (временное решение, см. ADR-006 в DECISIONS.md).

### Soft delete
- Физического удаления пользователей нет — только `deleted_at + is_active=False`
- При soft delete отзываются все активные сессии пользователя

### Анонимизация IP
- Функция `anonymize_old_ips()` в БД — IP-адреса анонимизируются через 90 дней

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

### Аудит admin-операций
- Операции над пользователями логируются, но UUID цели закодирован в строке события
- Нет поля `target_user_id` в `auth_log` — затруднён поиск по конкретному субъекту ПДн
- Неуспешные admin-операции не логируются
- В бэклоге: `BACKLOG.md §🔵`

### Партиции audit-таблиц
- Начальные партиции 2026-01..2028-12 созданы миграцией `3a7c5e2b8f1d`
- Будущие партиции управляются через `scripts/ensure_audit_partitions.py --months-ahead 24`
- Запускать заблаговременно (рекомендуется раз в год через cron)
- Статус: закрыто в `BACKLOG.md §🔴`

### Право на удаление данных
- Soft delete реализован, но физического удаления нет
- Механизма полного удаления данных по запросу субъекта не существует

---

## Области ПДн в системе

| Данные | Таблица | Чувствительность |
|--------|---------|-----------------|
| ФИО, email, телефон | `users` | Базовые ПДн |
| Результаты тестов | `test_results` | Специальные категории |
| Заметки сессий | `session_notes` | Специальные категории |
| Переписка student ↔ psychologist | `chat_messages` | Специальные категории |
| Вложения чата (metadata + файл на FS) | `chat_attachments` + `CHAT_FILE_STORAGE_DIR` | Специальные категории |
| Записи на консультации | `appointments` | Базовые ПДн |
| IP-адреса | `auth_log` | Анонимизируются через 90 дней |

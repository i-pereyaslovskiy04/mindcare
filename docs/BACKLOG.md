# Backlog

Известные проблемы, технический долг и отложенные функции.
**Не «исправляй» эти вещи без явного запроса** — они отложены осознанно.

---

## 🔴 Критические (влияют на прод)

**~~Партиции audit-таблиц закончатся 31.12.2026~~** ✅ Закрыто
- Миграция `3a7c5e2b8f1d` переписана: audit-таблицы создаются как partitioned tables
  с начальными партициями 2026-01..2028-12
- Maintenance-скрипт управляет будущими партициями:
  ```
  cd mindcare_api/
  python scripts/ensure_audit_partitions.py --months-ahead 24
  ```
- Запускать скрипт заблаговременно (например, раз в год через cron)
- Файлы: `mindcare_api/alembic/versions/3a7c5e2b8f1d_add_audit_tables.py`,
  `mindcare_api/scripts/ensure_audit_partitions.py`

**~~`session_notes.content` не шифруется~~** ✅ Закрыто
- Реализовано Fernet application-layer шифрование в `app/core/encryption.py`
- `DATA_ENCRYPTION_KEY` env-переменная; алгоритм AES-128-CBC + HMAC-SHA256
- Ciphertext хранится с prefix `enc:v1:` в TEXT-колонке без изменения схемы БД
- encrypt-on-write / decrypt-on-read в `app/session_notes/storage.py`
- Plaintext fallback намеренно отсутствует; ORM-объект не мутируется plaintext
- Live API/DB verification прошла: DB хранит ciphertext, API возвращает plaintext
- Минимальные unit-тесты: `mindcare_api/tests/test_encryption.py` (21 passed)
- **Операционное требование:** `DATA_ENCRYPTION_KEY` должен быть настроен и резервно скопирован
  в каждой среде, хранящей заметки. Потеря ключа = потеря всех зашифрованных заметок.
- Файлы: `mindcare_api/app/core/encryption.py`, `mindcare_api/app/session_notes/`

---

## 🟠 Backend quality / security backlog

**~~Session tokens хранились plaintext (C1)~~** ✅ Закрыто (Stage 22b)
- `user_sessions.id` теперь хранит SHA-256 hash (64 hex), не raw token
- Клиент получает raw token как раньше; lookup/revoke/touch — hash-on-lookup
  (`hash_session_token()` в `app/auth/security.py`)
- `auth_log.session_id` пишет hash (совпадает с `user_sessions.id` — join работает)
- Значение из дампа БД больше нельзя использовать как `Authorization: Bearer`
- Dual-read fallback намеренно отсутствует: **деплой инвалидирует все активные
  сессии**, пользователи перелогиниваются один раз (фронт корректно показывает
  «Сессия истекла»)
- Тесты: `tests/test_session_security.py` + `tests/integration/test_session_token_hashing.py`
- **Оставлено на потом (low-priority maintenance):**
  - старые plaintext-строки `user_sessions` недостижимы и истекут сами
    (`SESSION_EXPIRE_DAYS=7`); ручная зачистка:
    `DELETE FROM user_sessions WHERE length(id) <> 64`
  - старые plaintext `auth_log.session_id` — historical risk: после деплоя эти
    токены не дают доступ; маскирование (`UPDATE ... SET session_id = NULL`
    для записей до деплоя) — отдельный cleanup-stage

**~~`auth_log.id` SAWarning~~** ✅ Закрыто
- Исправлено: `autoincrement=True` добавлен в `AuditLog.id`, `AuthLog.id`, `DataChangeLog.id`
- DB schema не менялась — sequences существовали; проблема была только в ORM metadata
- Файл: `mindcare_api/app/db/models/audit.py`

**~~H3: staff-доступ к content `session_notes` без audit~~** ✅ Закрыто для MVP (Stage 25b)
- Политика B: psychologist — только свои с content; supervisor — list metadata-only,
  GET by id с content **+ audit-событие `session_note_content_read`** в `audit_log`
  (actor, role, entity_id, author_id/engagement_id/appointment_id, IP/UA — без content);
  admin — metadata-only везде (`content_available: false`), decrypt не вызывается
- create/update также пишут audit-события (`session_note_created`/`session_note_updated`)
- Тесты: `tests/integration/test_session_notes_api.py` (15 сценариев)
- **Остаток (future):**
  - supervision-scope модель (супервизор ↔ психолог/кейс) — сейчас supervisor
    видит content всех заметок под audit; сужение зоны — отдельный этап
  - break-glass admin content access — только отдельным compliance/security
    решением, если когда-нибудь понадобится
  - full fix decrypt-error в content-list психолога (одна битая заметка валит
    список; metadata-пути уже не подвержены)

**~~Auth error leakage: raw SMTP/auth exceptions, `[object Object]` на 422, email в логах~~** ✅ Закрыто (Stage 31m-fix-a)
- frontend `api/client.js` парсит FastAPI/Pydantic 422 `detail` (array of `{loc,msg,type}`) — больше нет `[object Object]`
- SMTP/auth ошибки санитизированы: raw exception не отдаётся клиенту
- email в auth/SMTP логах маскируется через `mask_email` (`app/core/normalization.py`)
- Тесты: `tests/test_email_error_sanitization.py` (11)

**~~OTP INFO-логи раскрывают email; confirm не пишет IP/UA в consent; `_assign_role` silent skip~~** ✅ Закрыто (Stage 31m-fix-b1)
- OTP INFO-логи маскируют email; `register_confirm` route передаёт IP/User-Agent в `consent_records`;
  `_assign_role` бросает `RegistrationDataError` при отсутствующей роли (раньше молча пропускал → роль маскировалась дефолтом)
- Тесты: `tests/test_auth_hardening_b1.py` (6), `tests/integration/test_register_consent_context.py` (1)

**~~Registration confirm не атомарен (возможен user без consent при сбое)~~** ✅ Закрыто (Stage 31m-fix-b2)
- `storage.register_confirm_atomic`: validate OTP без удаления → user/reactivate → role `student` →
  все `consent_records` → consume OTP → один commit. Сбой core-шага откатывает всё, OTP остаётся;
  welcome/system message — soft-fail после commit
- Тесты: `tests/integration/test_register_confirm_atomic.py` (8, с failure-injection)

**~~Password reset confirm / change password не атомарны (пароль изменён, старые сессии остаются)~~** ✅ Закрыто (Stage 31m-fix-b3)
- `storage.password_reset_confirm_atomic`: validate OTP без удаления → `password_hash` → revoke всех сессий →
  consume OTP → один commit;
- `storage.change_password_atomic`: verify current password (callback внутри транзакции) → `password_hash` →
  revoke всех сессий → один commit;
- сбой revoke sessions откатывает смену пароля; OTP не теряется; новый хеш считается до транзакции;
  system-уведомление soft-fail после commit; `auth_log` soft-fail вне core-транзакции
- Тесты: `tests/integration/test_password_uow_atomic.py` (11, с failure-injection); backend full suite **282 passed**

**Открытые security/future направления (после Stages 21–25b):**
- **OTP concurrency / row locking** — атомарные confirm-flows не берут `SELECT … FOR UPDATE`;
  при гонке двух одновременных confirm возможен двойной проход OTP-валидации. Решение —
  `SELECT FOR UPDATE` или conditional update. **Deferred** (вне scope Stage 31m-fix-b3)
- **`_get_primary_role` read-fallback `"student"`** — при отсутствии активной роли `auth/storage._get_primary_role`
  возвращает дефолт `"student"`; cleanup (явная ошибка вместо тихого дефолта на чтении) — deferred
- **Transactional outbox** — гарантированная доставка post-commit уведомлений (welcome/security/engagement);
  сейчас они best-effort soft-fail. **Deferred** (намеренно не делаем на этом этапе)
- **HttpOnly Secure SameSite cookie + CSRF** вместо localStorage-токена
  (текущий localStorage — осознанный MVP-компромисс, Stage 18f)
- **Redis/shared storage для rate limiting** при multi-worker/multi-instance деплое
- **Cleanup legacy plaintext**: старые строки `user_sessions WHERE length(id) <> 64`
  и маскирование исторических `auth_log.session_id` (см. Stage 22b выше)
- ~~**`touch_session` debounce**~~ ✅ Закрыто (Stage 26): `last_active`
  обновляется не чаще раза в `TOUCH_SESSION_DEBOUNCE_SECONDS = 300` (5 мин),
  одним условным UPDATE без отдельного SELECT; revoked/expired сессии
  не «оживляются». Точность `last_active` — до 5 минут.
  Тесты: `tests/integration/test_touch_session.py` (9)
- **Request-scoped DB session / объединение auth storage calls** — future
  optimization: `get_current_user` по-прежнему делает `find_session` +
  `touch_session` (теперь чаще no-op) + `find_user_by_id` отдельными
  транзакциями; объединение в одну сессию — отдельный этап
- **`target_user_id` в auth_log** — см. 🔵-секцию (ADR-006)
- **~~Legal basis при смене роли через `PATCH /api/admin/users`~~** ✅ Закрыто (Stage 31f-fix)
  - PATCH смены роли на staff (`psychologist`/`supervisor`/`admin`, при `old_role != new_role`)
    требует `legal_basis_confirmed=true`, валидный `basis_type` и непустой `basis_reference`
    (иначе 400; невалидный `basis_type` → 422); роль не меняется, частичных записей нет;
  - смена роли и создание `user_legal_basis_records` — атомарны (одна транзакция);
  - `record_metadata` фиксирует `action="role_change"`, `old_role`, `new_role`;
  - `staff → student` основания не требует и старые записи не удаляет; смена не-роли — не требует;
  - тесты: `tests/integration/test_admin_role_patch_legal_basis.py` (12); backend full suite **245 passed**.
    Без миграций (использовано существующее JSONB-поле `metadata`)
- **~~Admin edit роли пользователя через UI~~** ✅ Закрыто (Stage 31n / 31n-hotfix), frontend-only
  - Stage 31h сделал роль read-only в `UserEditModal` — **правило отменено**; роль снова
    редактируема, но безопасно: при реальной смене на staff/admin UI показывает блок legal
    basis и шлёт `role` + `legal_basis_confirmed`/`basis_type`/`basis_reference`(+опц. comment)
    в PATCH; если роль не менялась — `role` не отправляется и основание не требуется;
  - Stage 31n-hotfix: поле «Роль пользователя» перенесено под ФИО; edit-dropdown содержит
    только `psychologist`/`supervisor`/`admin` — `student` не selectable (студенты —
    self-registration); текущая роль `student` отображается через shared `Select` `displayLabel`,
    но недоступна для повторного выбора; добавлен optional `displayLabel` в shared `Select`
    (backward-compatible);
  - формулировка подтверждения — «документированное основание для назначения роли» (не «согласие»);
  - backend legal basis policy и PATCH guard (Stage 31f-fix) **не менялись** — UI поверх
    существующей защиты (defense-in-depth);
  - тесты (frontend): `roleLabels.test.js` (edit options без student), `UserEditModal.smoke.test.jsx`
    (порядок поля, текущая роль student, dropdown без «Студент», раскрытие legal basis),
    обновлены `useUserForm.test.js` / `users.api.test.js`; итог **14 suites / 75 tests**;
  - **pending:** manual visual smoke edit-модалки (desktop/mobile) перед demo.
- **UI просмотра legal basis records** в карточке пользователя админки (отдельный pending-этап;
  смена роли пишет запись, но просмотр истории оснований в UI ещё не реализован)
- **Chat MVP** — one-to-one чат поверх `therapy_engagements` — **MVP завершён**:
  - ✅ Stage 28b: DB foundation — миграция `d8f3a6c1e9b4` (`chat_conversations`
    UNIQUE по engagement_id + `chat_messages` c partial-индексами), модели
    `app/db/models/chat.py`, constraint-тесты (`test_chat_models.py`, 6)
  - ✅ Stage 28c: backend `app/chat/` — polling API (`/api/chat/*`),
    encrypt-on-write/decrypt-after-permission (enc:v1:), access только
    student+psychologist по engagement (admin/supervisor → 403, без
    staff-доступа к content), lazy-create беседы с race-защитой,
    read receipts (`read_at`), before/after пагинация, audit
    `chat_conversation_created` (без content и без per-message шума),
    rate limit на отправку 30 сообщений/мин/пользователь
    (`tests/integration/test_chat_api.py`, 20)
  - ✅ Stage 28d: student frontend — `api/chat.api.js`, ChatPage на реальных
    данных (mock CONTACTS/INITIAL_MESSAGES/группа/поддержка/online/видеокнопка
    удалены, дизайн сохранён), loading/empty/error/closed states, polling 8s
    через `after=<id>`, mark-read при открытии и новых входящих, hardcoded
    unread badge в StudentLayout убран (реальный глобальный badge — future)
  - ✅ Stage 28e: psychologist chat frontend — `/psychologist/chat` (нав-пункт
    включён), список бесед с unread_count/статусом, окно переписки на
    переиспользованных student chat-компонентах (ChatSidebar/ChatWindow),
    polling 8s/30s, mark-read, closed-state (включая 409 при отправке)
  - ✅ Stage 28f: full-stack HTTP/API smoke `38 passed / 0 failed`,
    документация и hardening завершены; ручной browser smoke обоих кабинетов
    остаётся рекомендованным перед demo/deploy
  - ✅ Stage 29a: READ-ONLY дизайн Unified Messenger + System Conversation
    (выбор: `conversation_type` + nullable engagement_id, system как read-only
    feed, не замена audit_log, encryption-at-rest, idempotency через event_key)
  - ✅ Stage 29b: **System Conversation backend foundation** — миграция
    `c4f7a2e9d1b8` (chat_conversations.type/recipient_id + nullable engagement_id
    + CHECK + partial UNIQUE(recipient) WHERE system; chat_messages.message_kind/
    event_key + nullable sender_id + CHECK + partial UNIQUE(conversation,event_key)),
    `app/chat/system_publisher.py` (lazy-create, encrypt-on-write, idempotency,
    soft-fail, content не логируется), read-only API
    `GET/POST /api/chat/system-conversation*` (любая авторизованная роль — к своей
    беседе), подключены события welcome (register + admin-create) и password_changed;
    `tests/integration/test_system_conversation.py` (17). engagement chat-эндпоинты
    не изменены, frontend не тронут
  - ✅ Stage 29c: **frontend Unified Messenger + system conversation UI** — единый
    раздел «Сообщения» (student + psychologist), общие chat-компоненты вынесены в
    `src/features/chat/`, system-беседа как read-only feed (закреплена сверху, без
    composer), nav badge по числу диалогов с unread (не сумма сообщений), linkify
    http/https (без `dangerouslySetInnerHTML`), read receipts (✓/✓✓ по `read_at`),
    роуты `/student/chat` и `/psychologist/chat` сохранены; backend не менялся
    (lint 0 / build OK / backend 205)
  - ✅ Stage 29d: **system messages для engagement-событий** — `publish_system_message`
    подключён в `supervisor/service.py` (assign/transfer/close, после commit, soft-fail,
    имя психолога фиксируется до commit, reason не раскрывается). System-сообщения
    теперь публикуются для: **welcome**, **password_changed**, **engagement_assigned**,
    **engagement_transferred**, **engagement_closed** (idempotent по event_key);
    `tests/integration/test_engagement_system_messages.py` (11). Frontend/Alembic/схема
    не менялись (backend 216)
  - ✅ Stage 30a/30b: **Messenger polish** — system-беседа всегда видима + empty state,
    фикс высоты/обрезки шапки, live refresh через snapshot (limit=50) + `mergeMessages`
    (`read_at` обновляется без F5), per-dialog unread (badge/маркер/bold/фон), глобальный
    nav badge через `messagesEvents`; **VK-like entry**: при входе в раздел диалог не
    открывается автоматически, mark-read только после явного клика (placeholder справа).
    Frontend-only
  - ✅ Stage 30c: **presence + порядок диалогов** — system-беседа перемещена в конец
    списка; approximate online/offline через `user_sessions.last_active` (порог 10 минут,
    мягче debounce touch_session 300с), API-поле `peer_is_online` в `my-conversation`/
    `conversations`/`conversations/{uuid}`; frontend показывает online/offline точкой в
    списке и шапке; без WebSocket, без last-seen-текста; новой колонки/миграции нет;
    `tests/integration/test_chat_presence.py` (12). System-беседа presence не имеет
    (backend 228, lint 0, build OK)
  - ✅ Stage 30d + hotfixes: **mobile Messenger + mobile CabinetLayout** — Messenger
    list/thread на `≤900px` (back-кнопка в шапке открытого чата); CabinetLayout: `>980px`
    full sidebar, `601–980px` icon-rail, `≤600px` мобильный drawer (открытие по hamburger,
    закрытие backdrop/✕/Escape/кликом по пункту; `sidebarInner` переиспользуется из desktop
    sidebar, collapse-правила заскоуплены под `.sidebar`); фикс пустого кабинета на `<600px`
    (`.app` = `grid-template-columns: 1fr`); topbar разгружен (скрыты bell/mail, оставлены
    hamburger + breadcrumb + logout); удалён описательный подзаголовок под «Сообщения».
    Frontend-only; добавлен `ChatPage.smoke.test.jsx` (render list/thread). Ручной browser
    smoke desktop/tablet/mobile остаётся обязательным перед demo
  - ✅ Stage 31y: **меню действий со своим сообщением** — кебаб-меню «…»
    (`MessageActionsMenu`) вместо отдельной кнопки-карандаша, пункты «Редактировать»/
    «Удалить»; удаление через confirm-диалог (`DeleteMessageDialog`, на shared
    `Modal`/`Button`); меню недоступно для system-сообщений и в закрытой/архивной
    беседе. Frontend-only
  - ✅ Stage 31y-hotfix: **скрытие удалённых сообщений** — удалённые сообщения больше
    не показываются плейсхолдером в ленте; soft delete в БД/audit сохранён
    (физического удаления строки нет); runtime-текст «Сообщение удалено» не
    используется; `MessageList` фильтрует `messages.filter(m => !m.deleted)` до
    расчёта date-сепараторов/author-header. Frontend-only
  - ✅ Stage 31z: **`MessageBubble` — выделение визуального компонента** —
    `MessageItem` (полный компонент сообщения: own/incoming/system, author header,
    avatar/layout, `canManage`, меню действий) и `MessageBubble` (feature-specific
    визуальный bubble: текст + linkify + meta) разделены; meta (время/«изменено»/
    ✓/✓✓) — внутри bubble; system-сообщения рендерятся как bubble от «MindCare».
    Frontend-only
  - ✅ Stage 31z-hotfix: **компактная Telegram-style meta** — `.bubble` через
    `display:flex;flex-wrap:wrap;align-items:flex-end`: короткое сообщение и meta —
    в одну строку, длинное — meta переносится вниз-направо без JS-измерения ширины;
    кебаб-меню остаётся соседом bubble, не переносится внутрь него. Hardening:
    system-сообщения никогда не считаются исходящими (даже при `mine=true` от
    backend) и никогда не показывают «изменено» (даже при наличии `editedAt`).
    Frontend-only; обновлены `MessageBubble.module.css`, `MessageList.test.jsx`
  - ✅ Stage 31ab: **snapshot reconcile при polling** — `reconcileMessagesSnapshot`
    в `pollNew` (student + psychologist): удалённое сообщение исчезает у собеседника
    после следующего polling tick (≤ 8 сек) без переоткрытия диалога; без WebSocket/SSE;
    без placeholder; backend/API/Alembic не менялись; `mergeMessages` (add/update)
    сохранён. Тесты: `features/chat/lib/messageShape.test.js` (+10 тестов, 150 passed).
    MVP-ограничение: reconcile покрывает только последние 50 сообщений (snapshot window
    `limit=50`); история старше этой границы синхронизируется только при переоткрытии диалога.
  - ✅ Stage 31ad: **useChatCore — общий core hook** — audit (31ad-audit) выявил ~90%
    дублирования; fix-a: hook-level тесты; fix-b: общие константы + `errText` в
    `chatHookUtils.js`; fix-c: нормализация 409 у психолога (deleteMessage + helper
    `refreshConversationAfterConflict`); fix-d: `useChatCore(adapter)` создан
    (`features/chat/hooks/useChatCore.js`), `useStudentChat` и `usePsychologistChat` —
    thin wrappers. Public return shape хуков не изменился; page-компоненты не менялись;
    `useSystemConversation` — отдельный hook, не входит в `useChatCore`; backend/API/
    Alembic не менялись. 166/166 тестов. Frontend-only.
  - **Ограничения Messenger MVP** (зафиксированы осознанно, не баги):
    - presence приблизительный — не realtime; порог 10 минут; зависит от
      `user_sessions.last_active` и debounce `touch_session` 300с;
    - read-receipt live-обновление только в пределах snapshot `limit=50`;
    - без WebSocket/SSE (polling 8s/30s);
    - mobile drawer пока без focus-trap / `inert` фона;
    - snapshot reconcile при polling ограничен последними 50 сообщениями; история
      старше snapshot window синхронизируется только при переоткрытии диалога
  - **Group chat — postponed / future:**
    - не входит в текущий Messenger MVP; **не начат и не проектируется** на этом этапе
    - текущий Messenger покрывает только student↔psychologist one-to-one chat и
      system conversation — не смешивать с group chat
    - group chat будет **отдельным этапом** после стабилизации Messenger
    - учебная группа **не является** автоматическим чатом; она может быть только
      будущим источником отбора участников
    - перед реализацией обязателен отдельный **READ-ONLY design audit**, покрывающий:
      `chat_groups`; `chat_group_members`; roles/moderation; access policy;
      unread/read model; encryption policy; system messages внутри группы;
      privacy/compliance-риски
  - ✅ Stage 32b: **chat_attachments DB foundation** — миграция `a9b3e1f7c2d4`
    (`chat_attachments`: uuid, conversation_id FK, message_id nullable FK,
    uploader_id FK, original_filename, mime_type, file_size, storage_key, checksum,
    is_image, deleted_at); model `app/db/models/chat.py`; constraint-тесты
    (`test_chat_attachment_models.py`, 20)
  - ✅ Stage 32c: **backend attachment upload/download** — `POST .../attachments`
    (pre-upload, allowlist MIME, blocklist extensions, size limit, UUID storage_key,
    private FS `CHAT_FILE_STORAGE_DIR`); `GET .../download` (permission check,
    streaming response); send with `attachment_uuids`; `test_chat_attachment_api.py` (37)
  - ✅ Stage 32c-hotfix: **safe file type policy** — WEBP, Excel (`.xls/.xlsx`) и
    PowerPoint (`.ppt/.pptx`) разрешены; SVG запрещён; архивы отложены; blocklist
    расширен `.vbs`/`.scr`
  - ✅ Stage 32d + 32d-hotfix: **frontend attachment rendering** — `AttachmentCard`/
    `AttachmentList` в `MessageBubble`; high-contrast outgoing dark-card fix
  - ✅ Stage 32d-hotfix-b: **safe Office download** — Chromium safe save flow через
    `showSaveFilePicker`, fallback через anchor download; Office attachments скачиваются
    без top-level navigation на `blob:` URL; чат остаётся открытым; Office header tests пройдены
  - ✅ Stage 32d-hotfix-b layout: **files-first attachment layout** — в сообщениях с
    файлами и текстом сначала отображаются файлы, затем divider, затем текст как caption;
    attachment-only сообщения без divider
  - ✅ Stage 32e: **composer attachment picker** — скрепка, hidden file input,
    `SelectedAttachmentList` (pre-send), attachment-only send, text+attachment send,
    upload error без потери черновика; `SelectedAttachmentList.test.jsx`
  - ✅ Stage 32f: **drag & drop** — `DragDropOverlay`, counter-based enter/leave,
    merge с existing selected, empty file/max-files guard; drag disabled in edit-mode;
    `DragDropOverlay.test.jsx`, `ChatWindow.test.jsx` drag tests
  - ✅ Stage 32g: **edit/remove individual attachment** — `remove_attachment_uuids`
    в schema/storage/service/routes; soft delete атомарно с content/edited_at;
    `EditableAttachmentList` (optimistic UI); `test_chat_attachment_edit.py` (18)
  - ✅ Stage 32i: **Image Preview / Lightbox** — preview `image/jpeg`, `image/png`,
    `image/webp` через `AttachmentPreviewLightbox`; authenticated blob flow
    (`URL.createObjectURL` / `URL.revokeObjectURL`), без public static и без токенов в URL
  - ✅ Stage 32j: **PDF Preview / Lightbox** — preview `application/pdf` в том же
    `AttachmentPreviewLightbox` через native browser PDF rendering в iframe с blob URL;
    Office/TXT/SVG/unknown MIME остаются download-only; frontend/backend suites пройдены
  - **Future (chat):** preview последнего сообщения в списке бесед; WebSocket/SSE
    realtime presence; inline image thumbnails; Office preview; TXT preview; PDF.js integration
    при необходимости; upload progress percent; upload retry queue; MIME magic bytes validation (`python-magic`);
    antivirus/ClamAV scanning; at-rest encryption физических файлов в FS; S3/MinIO
    storage backend; добавление новых файлов в edit-mode; staff break-glass access;
    Action Center / колокольчик; system messages для заданий/материалов/анкет/legal
    announcements; усиление a11y mobile drawer (focus-trap/`inert`);
    глубокий рефакторинг chat-модуля
  - **Orphan attachments cleanup helper — существует:** `scripts/cleanup_orphan_attachments.py`
    работает в dry-run режиме по умолчанию, `--apply` включает выполнение, scope —
    только orphan-записи `chat_attachments` с `message_id IS NULL`.
  - **Full attachment cleanup/retention — pending / production-hardening:**
    физическое удаление файлов soft-deleted вложений по retention-политике,
    тесты cleanup CLI, manual smoke и опциональный cron/systemd timer после ручной
    проверки. Не считать реализованными full retention, автоматический cleanup и
    scheduler.
  - **Open product question:** retention policy для chat messages
    (срок хранения переписки после завершения терапии)
  - `questions_answers` — не чат, не использовать

**✅ Student Diary MVP + UX/History Hotfix** — завершено:
  - ✅ Backend `routes → service → storage → models`; миграция `b2e4d7f1a9c3`;
    `diary_emotions` с seed `calm`, `joyful`, `anxious`, `sad`, `tired`, `angry`,
    `inspired`, `confused`, `light`, `focused`; `diary_entries` с partial UNIQUE
    `(student_id, entry_date) WHERE deleted_at IS NULL`
  - ✅ API: emotions, today GET/PUT, entries `limit/offset`, PATCH/DELETE по UUID,
    summary `14d|month|year`; все endpoints student-only, non-student → 403;
    чужая/удалённая/несуществующая запись → 404, malformed UUID → 422
  - ✅ DELETE — soft-delete через `deleted_at`; после delete можно создать новую запись
    на ту же дату; empty PATCH `{}` — no-op без изменения `updated_at`
  - ✅ Encryption-at-rest: `mood_score_enc`, `entry_text_enc`, `emotions_enc` —
    Fernet `enc:v1:`; plaintext diary content не логируется
  - ✅ Frontend: StudentHome вокруг `nextStepCard`, action cards и `observationCard`;
    fake GAD-7/sleep/anxiety/appointment/psychologist/date удалены; DiaryPage —
    quick check-in, optional collapsible details, history/load more, edit/delete,
    inline errors; после delete история перечитывается с offset=0
  - ✅ Hotfix: local frontend today helper вместо UTC `toISOString()`, честный session copy,
    malformed UUID 422 и empty PATCH no-op
  - ✅ Проверенный статус проекта: backend **587 passed**; frontend
    **40 suites / 530 passed**; lint **0 warnings**; build **success**
  - **Pending / будущие этапы:**
    - Diary analytics / интеграция существующего `MoodChart` в `/student/diary`
    - Audit trail для diary edit/delete — compliance gap до production hardening
    - Доступ психолога — только отдельная policy с explicit consent/legal basis
    - Timezone-aware backend date policy вместо server-side `date.today()` MVP
    - Admin UI для `diary_emotions`
    - Export diary data с отдельной политикой/согласием/audit
    - Advanced analytics: тренды, корреляции, сравнения периодов
    - GAD-7/PHQ-9 как отдельный валидированный questionnaire-модуль, не dashboard stats
    - Реальная appointments integration для session data
    - Mobile/a11y hardening: `aria-live`, focus management delete confirm, textarea labels

---

## 🟡 Важные (влияют на качество)

**~~OTP-коды хранятся в открытом виде~~** ✅ Закрыто
- Исправлено: migration `c5d8a1b4e7f2`, `app/auth/otp_service.py` — SHA-256 хеш

**`_get_primary_role` недетерминирован при нескольких ролях**
- ~~Использует `.first()` без `ORDER BY`~~
- Закрыто: заменено коррелированным подзапросом с `ROLE_PRIORITY` в `users/storage.py`

**~~Email без нормализации в `register_init`~~** ✅ Закрыто
- Добавлен единый helper `normalize_email()` в `app/core/normalization.py`
- Применён в `otp_service` (create/verify/delete), `auth/storage` (find/save/reactivate), `users/storage` (create_user), `scripts/create_admin.py`
- 16 unit-тестов в `tests/test_normalization.py`; Stage 17c: API/integration tests
- DB-level защита: migration `e5a8f3c1d2b6` добавляет `ux_users_email_normalized` — functional unique index `lower(trim(email))` на таблице `users`

**~~Нет фиксации основания обработки ПДн для юзеров, созданных через `POST /api/admin/users`~~** ✅ Закрыто (Stage 23b, H4)
- Переформулировано: для psychologist/supervisor/admin это не «согласие пациента»,
  а **документированное основание организации** (трудовое/служебное/договорное/приказ).
  `consent_records` не использовать как суррогат legal basis для staff-ролей.
- Реализовано: таблица `user_legal_basis_records` (миграция `b6e1f4a7c9d3`,
  модель `app/db/models/legal_basis.py`); запись создаётся в одной транзакции
  с пользователем; `legal_basis_confirmed=true` обязателен (422 без него);
  фиксируются basis_type, basis_reference, actor admin id, IP, user-agent
- `scripts/create_admin.py` пишет legal basis (bootstrap) вместо consent-имитации;
  исторические bootstrap consent_records не удалялись
- Backfill: `scripts/backfill_legal_basis.py` (`--dry-run` по умолчанию);
  **`--apply` на момент Stage 23b не запускался** — выполнить при деплое
- Тесты: `tests/integration/test_legal_basis_api.py` (11 сценариев)

**~~`AdminUserCreate` не допускает роль `supervisor`, `AdminUserUpdate` — допускает~~** ✅ Закрыто
- Асимметрия устранена: `AdminUserCreate.role` теперь `Literal["psychologist", "admin", "supervisor"]`
- Файл: `mindcare_api/app/users/schemas.py`

---

## 🟢 Технический долг (не срочно)

**IP-адрес в аудит-логе некорректен за proxy/nginx**
- `request.client.host` возвращает IP прокси-сервера, а не реального пользователя
- В продакшене нужно читать `X-Forwarded-For` или `X-Real-IP` из заголовков
- Решение: добавить хелпер `get_client_ip(request)` в `app/core/` который проверяет заголовки прокси, и использовать его во всех роутерах
- Файлы: `app/users/routes_admin.py`, `app/tags/routes_admin.py`, `app/auth/routes.py`

**Документирование HTTP-статусов ошибок в OpenAPI (Swagger)**
- FastAPI автоматически документирует только 200/201/204 — ошибочные статусы (400, 404, 409, 422) не видны в Swagger без явного указания
- Нужно добавить параметр `responses={...}` к эндпоинтам во всех роутерах (`users`, `tags`, `auth`)
- Актуально когда появится внешний потребитель API (мобильное приложение, сторонний сервис)
- Файлы: все `routes_admin.py` и `routes.py` в модулях

**Кастомные исключения в service-слое вместо ValueError + проверки текста**
- `users/service.py` и `tags/service.py` определяют HTTP-статус ошибки по содержимому строки (`"не найден" in msg`)
- Хрупкий паттерн: стоит переименовать строку — статус сломается
- Правильное решение: завести `NotFoundError`, `ConflictError` (или доменные аналоги) в `app/core/exceptions.py`, использовать везде
- Заодно выровнять статусы: сейчас `users` возвращает 400 для конфликтов, `tags` — 409
- Файлы: `app/users/service.py`, `app/tags/service.py`, создать `app/core/exceptions.py`

**~~`datetime.utcnow()` в `otp_service.py`~~** ✅ Закрыто
- Исправлено: `_utcnow()` → `datetime.now(timezone.utc).replace(tzinfo=None)` (naive UTC, совместимо с `DateTime` без timezone в `OtpVerification`); `email_service.py` → `datetime.now(timezone.utc).year`
- Файлы: `app/auth/otp_service.py`, `app/services/email_service.py`, `tests/test_normalization.py`

**`print()` вместо `logging`**
- Весь проект использует `print()` для диагностики
- Нужен переход на `logging` с уровнями (DEBUG/INFO/WARNING/ERROR)
- Менять везде сразу, не по одному файлу

**~~`ssl.CERT_NONE` в `app/services/_smtp.py`~~** ✅ Закрыто (Stage 18d)
- Удалены `ctx.check_hostname = False` и `ctx.verify_mode = ssl.CERT_NONE`
- Удалён `server.set_debuglevel(1)` из runtime transport
- Добавлена явная поддержка `SMTP_TLS` / `SMTP_SSL` в `Settings` и `.env.example`
- STARTTLS и implicit SSL используют `ssl.create_default_context()` без мутации
- 21 тест в `tests/test_smtp_transport.py`
- Остаток: `scripts/test_smtp.py` сохраняет `set_debuglevel(1)` намеренно (diagnostic tool) — помечено WARNING в docstring

**`_hash` приватная функция используется снаружи**
- `app/users/service.py` импортирует `_hash` из `app/auth/service.py`
- Нарушение инкапсуляции
- Вынести в `app/core/security.py` и сделать публичной
- Файл: `app/auth/service.py`, `app/core/` (создать `security.py`)

**`store/store.js` на фронте не реализован**
- Файл существует как заглушка
- Redux/Context не подключён
- AuthContext покрывает текущие потребности
- Нужен ли Redux — решать когда появится необходимость

**~~Нативный `datetime-local` в admin news/articles формах~~** ✅ Закрыто (Stage 31j-fix / 31j-hotfix)
- Заменён shared `DateInput` (`src/components/UI/DateInput/`): date-only, value `YYYY-MM-DD`, кастомный popover через portal, без нативного popup
- `published_at` API-контракт не менялся (ISO datetime / `null`); конверсия через `dateHelpers`
- Позиционирование popover: flip вверх/вниз + clamp в viewport (`computePopoverPosition`, тесты `popoverPosition.test.js`)
- Остаток (pending): manual smoke `DateInput` на mobile / low-height viewport
- `DateTimePicker` / `TimeInput` / `SlotPicker` — НЕ нужны в ближайшем этапе; `SlotPicker` появится отдельно для записи на приём (не замена `DateInput`)

**Раздел 1 в `ARCHITECTURE.md` устарел**
- Project Tree не отражает реальную структуру `mindcare_web/src/`
- Обновить когда структура стабилизируется

**`LoginForm` использует устаревший паттерн ошибок**
- Хранит ошибки полей как булевы значения (`errors.email: true`) и серверную ошибку в отдельном `apiError`
- По стандарту `ARCHITECTURE.md §10` — должен быть единый `errors` со строками + `errors._form`
- Файл: `mindcare_web/src/features/auth/ui/LoginForm.jsx`

**CSS-классы ролей в `UsersTable` нарушают camelCase-конвенцию**
- Динамические классы `role_student`, `role_psychologist` и т.д. используют underscore
- По конвенции ARCHITECTURE.md §10 — должны быть `roleStudent`, `rolePsychologist`, `roleAdmin`, `roleSupervisor`
- Файл: `mindcare_web/src/features/admin/users/components/UsersTable.jsx`

**`phone` не стрипается при обновлении юзера**
- `update_user` в storage стрипает `full_name`, но не стрипает `phone`
- Непоследовательная нормализация входных данных
- Файл: `mindcare_api/app/users/storage.py`

**Дублирование стилей между UserCreateModal и UserEditModal**
- Общие классы (`.body`, `.title`, `.field`, `.input`, `.btnPrimary`, `.btnSecondary` и др.)
  продублированы в двух CSS-модулях слово в слово
- CSS Modules не поддерживают наследование — решение: вынести общие стили
  в `admin/users/components/adminModal.module.css` и импортировать в оба компонента
- Файлы: `mindcare_web/src/features/admin/users/components/UserCreateModal.module.css`,
  `mindcare_web/src/features/admin/users/components/UserEditModal.module.css`

**`DeleteConfirmDialog` — setState после закрытия диалога**
- Если нажать Escape пока идёт DELETE-запрос, Modal закроет диалог,
  но `setDeleting(false)` в `.finally()` выполнится на скрытом компоненте
- Добавить `cancelled`-флаг по аналогии с useUserForm useEffect
- Файл: `mindcare_web/src/features/admin/users/components/DeleteConfirmDialog.jsx`

**`useUserForm` — нет защиты от двойного submit**
- `handleSubmit` не проверяет `submitting` перед запуском запроса
- Двойной клик по кнопке Submit (если она не задизейблена) запустит два параллельных запроса
- Добавить `if (submitting) return;` в начало `handleSubmit`
- Файл: `mindcare_web/src/features/admin/users/hooks/useUserForm.js`

**`authApi.register` в AuthContext — неиспользуемый экспорт**
- Регистрация идёт через `registerInit` + `registerConfirm`; `register` — остаток ранней реализации
- Файл: `mindcare_web/src/features/auth/AuthContext.jsx`

**`create_category` открывает вторую DB-сессию после создания**
- `storage.create_category()` после `commit()` вызывает `get_category_by_id(cat.id)`, который открывает новую сессию
- Для MVP это не критично, но это лишний round-trip к БД на каждое создание типа материалов
- Позже вернуть dict прямо из первой сессии после `db.refresh(cat)` или вынести общий mapper
- Файл: `mindcare_api/app/categories/storage.py`

**`find_categories` считает `total` на запросе с коррелированным подзапросом**
- `query.count()` выполняется поверх запроса, который уже содержит `article_count` subquery
- На больших объёмах это может быть лишней нагрузкой; такой же паттерн есть в `tags/storage.py`
- Позже выделить отдельный count-запрос без subquery и исправить сразу categories + tags
- Файлы: `mindcare_api/app/categories/storage.py`, `mindcare_api/app/tags/storage.py`

**Domain-сервисы используют `AuthError` из auth-модуля**
- `categories`, `tags`, `users` используют `AuthError` как generic service error
- Это cross-domain зависимость: content/admin модули зависят от `app/auth/service.py` ради HTTP-статуса
- Позже вынести общий `ServiceError` / `NotFoundError` / `ConflictError` в `app/core/exceptions.py` и заменить во всех service-слоях
- Файлы: `mindcare_api/app/categories/service.py`, `mindcare_api/app/tags/service.py`, `mindcare_api/app/users/service.py`

---

**Кодировка категорий в БД**
- Категории были созданы с кодировкой CP1251/UTF-8 mismatch — названия отображались иероглифами
- Исправлено скриптом `scripts/fix_category_encoding.py` (запускать один раз)
- Причина: данные вставлялись через клиент с неправильной кодировкой соединения
- При создании новых категорий через API проблема не воспроизводится

---

## 🔵 Запланировано (следующие задачи)

**Admin-создание пользователя с email soft-deleted аккаунта**
- `storage.create_user` проверяет уникальность только среди активных записей (`deleted_at IS NULL`)
- Если email принадлежит удалённому аккаунту — создаётся дубль в БД
- Решение: реактивировать старую запись по аналогии с `reactivate_user()` в `auth/storage.py`
- Файл: `mindcare_api/app/users/storage.py` → `create_user()`

**`audit_log` и `data_change_log` не используются — только `auth_log`**
- Таблицы созданы в схеме (migration `3a7c5e2b8f1d`), но нигде в коде нет записей в них
- `audit_log` предназначен для системных событий (деактивация теста, закрытие приёма, смена категории)
- `data_change_log` предназначен для хранения old/new значений при изменении данных (требование ФЗ-152 для прослеживаемости)
- Нужно решить: писать вручную через хелпер (`log_data_change(table, record_id, old, new)`) или через PostgreSQL-триггеры
- Актуально для таблиц с ПДн: `users`, `student_profiles`, `psychologist_profiles`, `session_notes`, `appointments`
- Файлы: создать `app/audit/service.py`, подключить в модули которые меняют ПДн

**Аудит-лог admin-операций: добавить target_user_id и логировать неудачи**
- `log_auth_event` не имеет поля `target_user_id` — нельзя ответить «когда и кем изменён конкретный пользователь»
- Сейчас uuid цели закодирован в строке события (`admin_create_user:{uuid}`) — костыль
- Правильное решение: добавить `target_user_id` в модель `AuthLog` + параметр в `log_auth_event` + миграция БД
- Дополнительно: логировать неуспешные операции (`success=False`) в except-блоках
- Файлы: `mindcare_api/app/db/models/audit.py`, `mindcare_api/app/auth/audit.py`,
  `mindcare_api/app/users/routes_admin.py`, новая Alembic-миграция

**Защита от самоудаления и удаления последнего администратора**
- Администратор может удалить свой аккаунт → потеря доступа к панели
- Администратор может удалить/понизить роль единственного активного admin → никто не войдёт
- В `service.delete_user` и `service.update_user` добавить проверки:
  1. `uuid != current_user["uuid"]` — нельзя трогать себя
  2. После операции должен остаться хотя бы один активный admin
- Требует передачи `current_user` из роутера в сервис
- Файлы: `mindcare_api/app/users/service.py`, `mindcare_api/app/users/routes_admin.py`

**Следующий крупный модуль после Admin Content**
- Admin Categories CRUD закрыт: `/api/admin/categories` и `/admin/categories` реализованы
- Нужно выбрать следующий приоритет с владельцем проекта: Appointments, Admin Tests или личные кабинеты
- При выборе учитывать ФЗ-152: appointments и результаты тестов затрагивают чувствительные психологические данные

**Белый экран при загрузке роутов (PrivateRoute / RoleRoute)**
- `router.jsx`: `if (loading) return null` — пустая страница пока AuthContext восстанавливает сессию
- Заменить на `<PageSkeleton />` или аналогичный placeholder
- Файл: `mindcare_web/src/app/router.jsx`

**Показ удалённых пользователей в админке**
- Сейчас `find_users` всегда фильтрует `deleted_at IS NULL` — удалённые не видны
- Бэк: добавить `include_deleted: bool = False` в `find_users`, `AdminUserListQuery` и роутер;
  добавить `deleted_at: Optional[datetime]` в `AdminUserListItem`
- Фронт: фильтр «Показать удалённых» в `UsersFilters`; визуальный индикатор в `UsersTable`
  (зачёркнутый текст или отдельный бейдж «Удалён»)
- Файлы: `mindcare_api/app/users/storage.py`, `mindcare_api/app/users/schemas.py`,
  `mindcare_api/app/users/routes_admin.py`,
  `mindcare_web/src/features/admin/users/components/UsersFilters.jsx`,
  `mindcare_web/src/features/admin/users/components/UsersTable.jsx`

---

## 🔲 Отложено на Этап 2 (не MVP)

Следующие функции **намеренно не реализованы** в MVP:

- MFA / двухфакторная аутентификация (таблица `user_mfa_methods` готова в БД)
- Интеграция с Яндекс.Календарь
- Видеоконсультации (Rutube / SberJazz)
- Telegram-бот и Telegram-уведомления
- ИИ-анализ (видеокамера, распознавание эмоций)
- Платные услуги
- Полнотекстовый поиск с морфологией
- Экспорт данных (Excel, PDF-отчёты)
- Принудительная смена пароля при первом входе
- ~~Rate limiting на auth-эндпоинты~~ — закрыто (Stage 21): in-memory sliding window
  в `app/core/rate_limit.py`, подключён к login / register init+confirm /
  password reset init+confirm. Лимиты по IP и нормализованному email, 429 с единым
  сообщением без раскрытия существования аккаунта.
  **Ограничение MVP:** состояние per-process; при multi-worker/multi-instance
  деплое каждый процесс считает независимо — для production нужен Redis/shared
  storage (интерфейс `enforce()` сохраняется). Rate limiting на остальные
  API-эндпоинты (не auth) — по-прежнему Этап 2.
- ~~Автогенерация партиций audit-таблиц~~ — закрыто `ensure_audit_partitions.py`

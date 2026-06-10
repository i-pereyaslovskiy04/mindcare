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

**`auth_log.id` SAWarning (open)**
- Severity: Medium
- ORM-модель `AuthLog` не объявляет `server_default` или `Sequence` для `id` на партиционированных таблицах
- SQLAlchemy выдаёт SAWarning при старте: `Implying autoincrement for column...` для партиционированных таблиц
- Причина: ORM не отражает DB-side sequence generator для `id` в partitioned audit table
- Риск: основной auth/admin flow не падает (`log_auth_event()` ловит исключения), но audit events могут теряться
- Next: Stage 14b — live DB inspection (`information_schema`, `pg_inherits`) перед любым ORM/Alembic fix
- Файл: `mindcare_api/app/db/models/audit.py`

---

## 🟡 Важные (влияют на качество)

**~~OTP-коды хранятся в открытом виде~~** ✅ Закрыто
- Исправлено: migration `c5d8a1b4e7f2`, `app/auth/otp_service.py` — SHA-256 хеш

**`_get_primary_role` недетерминирован при нескольких ролях**
- ~~Использует `.first()` без `ORDER BY`~~
- Закрыто: заменено коррелированным подзапросом с `ROLE_PRIORITY` в `users/storage.py`

**Email без нормализации в `register_init`**
- `save_user` нормализует email (`.lower().strip()`)
- Но `otp_verifications.email` сохраняется как есть (без нормализации)
- Если юзер введёт `Ivan@MAIL.ru` при init и `ivan@mail.ru` при confirm — не найдёт OTP
- Нужна нормализация в `otp_service.create_or_update_otp`
- Файл: `app/auth/otp_service.py`

**Нет `consent_records` для юзеров созданных через `POST /api/admin/users`**
- Психологи и админы создаются без фиксации согласия на ПДн
- Юридически: согласие должно быть получено при первом входе
- Нужен флаг `must_accept_consent` и проверка при логине
- Файл: `app/users/service.py`, `app/auth/service.py`

**`AdminUserCreate` не допускает роль `supervisor`, `AdminUserUpdate` — допускает**
- Создать супервизора через `POST /api/admin/users` нельзя, но сменить роль на `supervisor` через `PATCH` — можно
- Асимметрия не задокументирована; уточнить намеренность и при необходимости выровнять
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

**`datetime.utcnow()` в `otp_service.py`**
- Deprecated в Python 3.12+, удалён в 3.14
- Заменить на `datetime.now(timezone.utc)` везде
- Файл: `app/auth/otp_service.py`

**`print()` вместо `logging`**
- Весь проект использует `print()` для диагностики
- Нужен переход на `logging` с уровнями (DEBUG/INFO/WARNING/ERROR)
- Менять везде сразу, не по одному файлу

**`ssl.CERT_NONE` в email_sender.py**
- Отключена проверка SSL-сертификата SMTP-сервера
- Уязвимость к MITM-атаке на SMTP
- Вернуть нормальную проверку перед деплоем в прод
- Файл: `app/services/email_sender.py`

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
- Rate limiting на API-эндпоинты
- ~~Автогенерация партиций audit-таблиц~~ — закрыто `ensure_audit_partitions.py`

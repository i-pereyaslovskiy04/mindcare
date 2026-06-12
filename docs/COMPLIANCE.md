# ФЗ-152 Compliance Checklist

Статус выполнения требований ФЗ-152 «О персональных данных» для платформы MindCare.
Последнее обновление: 2026-06-11.

---

## ✅ Реализовано

### Согласие на обработку ПДн
- При регистрации студента фиксируется согласие в `consent_records`
- Таблицы `consents` (версии политик) и `consent_records` (факты согласия) в БД
- Перед регистрацией проверяется наличие актуальных политик

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
- `POST /api/admin/users` требует `legal_basis_confirmed=true` (иначе 422);
  запись основания создаётся в одной транзакции с пользователем
  (basis_type, basis_reference, actor admin id, IP, user-agent)
- UI-формулировка: «Подтверждаю наличие документированного основания для
  создания учётной записи и обработки персональных данных пользователя»
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
| Записи на консультации | `appointments` | Базовые ПДн |
| IP-адреса | `auth_log` | Анонимизируются через 90 дней |

# Backlog

Известные проблемы, технический долг и отложенные функции.
**Не «исправляй» эти вещи без явного запроса** — они отложены осознанно.

---

## 🔴 Критические (влияют на прод)

**Партиции audit-таблиц закончатся 31.12.2026**
- Таблицы `auth_log`, `audit_log`, `data_change_log` партиционированы по месяцам
- Партиции захардкожены только до конца 2026 года
- После 31.12.2026 любой INSERT в эти таблицы упадёт → логин сломается
- Нужен скрипт автогенерации партиций или `pg_partman`
- Файл: `db/sql/008_audit.sql`

**`session_notes.content` не шифруется**
- В схеме БД написано «шифруется на уровне приложения» — это не реализовано
- Клинические заметки хранятся открытым текстом
- Нужен `cryptography.fernet` с ключом из env
- Файл: будущий модуль `app/appointments/`

---

## 🟡 Важные (влияют на качество)

**OTP-коды хранятся в открытом виде**
- `otp_verifications.code` — plaintext, не хеш
- При утечке БД можно сбросить пароль любого юзера в окне 10 минут
- Нужен `sha256(code)` при сохранении, сравнение по хешу
- Файл: `app/db/models.py` (OtpVerification), `app/auth/otp_service.py`

**`_get_primary_role` недетерминирован при нескольких ролях**
- Использует `.first()` без `ORDER BY`
- Если у юзера две роли — вернёт случайную
- Сейчас безопасно (один юзер = одна роль), но сломается при расширении
- Нужен `ORDER BY granted_at DESC` или явный приоритет ролей
- Файл: `app/auth/storage.py`

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
- Файл: `mindcare_web/src/features/admin-users/ui/UsersTable.jsx`

**`phone` не стрипается при обновлении юзера**
- `update_user` в storage стрипает `full_name`, но не стрипает `phone`
- Непоследовательная нормализация входных данных
- Файл: `mindcare_api/app/users/storage.py`

**Дублирование стилей между UserCreateModal и UserEditModal**
- Общие классы (`.body`, `.title`, `.field`, `.input`, `.btnPrimary`, `.btnSecondary` и др.)
  продублированы в двух CSS-модулях слово в слово
- CSS Modules не поддерживают наследование — решение: вынести общие стили
  в `admin-users/ui/adminModal.module.css` и импортировать в оба компонента
- Файлы: `mindcare_web/src/features/admin-users/ui/UserCreateModal.module.css`,
  `mindcare_web/src/features/admin-users/ui/UserEditModal.module.css`

**`DeleteConfirmDialog` — setState после закрытия диалога**
- Если нажать Escape пока идёт DELETE-запрос, Modal закроет диалог,
  но `setDeleting(false)` в `.finally()` выполнится на скрытом компоненте
- Добавить `cancelled`-флаг по аналогии с useUserForm useEffect
- Файл: `mindcare_web/src/features/admin-users/ui/DeleteConfirmDialog.jsx`

**`useUserForm` — нет защиты от двойного submit**
- `handleSubmit` не проверяет `submitting` перед запуском запроса
- Двойной клик по кнопке Submit (если она не задизейблена) запустит два параллельных запроса
- Добавить `if (submitting) return;` в начало `handleSubmit`
- Файл: `mindcare_web/src/features/admin-users/hooks/useUserForm.js`

**`authApi.register` в AuthContext — неиспользуемый экспорт**
- Регистрация идёт через `registerInit` + `registerConfirm`; `register` — остаток ранней реализации
- Файл: `mindcare_web/src/features/auth/AuthContext.jsx`

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
- Автогенерация партиций audit-таблиц (pg_partman)

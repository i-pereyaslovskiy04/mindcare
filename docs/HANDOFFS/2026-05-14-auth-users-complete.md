# Handoff: Auth + Users (Admin) — 2026-05-14

## Состояние проекта

**Проект:** MindCare — платформа психологической службы ДонГУ  
**Этап:** MVP (Этап 1), ~3-4 недели в разработке  
**Команда:** 2-3 разработчика  
**Стек:** FastAPI + SQLAlchemy (sync) + PostgreSQL 15+ / React 19 + CRA + CSS Modules

---

## Что полностью готово

### Backend: модуль `app/auth/`

Все файлы рабочие, покрыты ручным тестированием.

**Эндпоинты:**
- `POST /api/auth/register/init` — валидация → OTP в БД → письмо на email
- `POST /api/auth/register/confirm` — верификация OTP → создание user + consent_records
- `POST /api/auth/login` — bcrypt проверка → сессия в user_sessions → токен
- `POST /api/auth/logout` — отзыв сессии
- `GET /api/auth/me` — текущий юзер по сессии
- `POST /api/auth/password/reset/init` — OTP для сброса
- `POST /api/auth/password/reset/confirm` — новый пароль + отзыв всех сессий

**Файлы:**
```
app/auth/
├── audit.py        — log_auth_event() → auth_log
├── deps.py         — get_current_user, require_role
├── otp_service.py  — create_or_update_otp, verify_otp (DB-backed)
├── routes.py       — все эндпоинты с логированием
├── schemas.py      — Pydantic-схемы
├── security.py     — generate_session_token
├── service.py      — бизнес-логика, AuthError
└── storage.py      — users, sessions, consents, log_auth_event
```

**Важные решения:**
- Auth: сессии в `user_sessions` (не JWT). Токен в `Authorization: Bearer`
- OTP: 6 цифр, 10 минут TTL, max 5 попыток, cooldown 60 сек
- Email: синхронный smtplib, `EMAIL_MODE=dev|smtp` в .env
- Согласия ПДн: `consent_records` пишется при регистрации (privacy_policy + data_processing)
- Логирование: все auth-события → `auth_log` через `audit.log_auth_event()`
- `OtpVerification` таблица создаётся через `create_all`, не через SQL-миграции

**Скрипт создания первого админа:**
```bash
cd mindcare_api
python scripts/create_admin.py
```

---

### Backend: модуль `app/users/`

Полный CRUD для управления пользователями (только для админа).

**Эндпоинты:**
- `GET /api/admin/users` — список с пагинацией, фильтрами, поиском
- `POST /api/admin/users` — создание психолога/админа + автогенерация пароля + email
- `GET /api/admin/users/{uuid}` — профиль юзера
- `PATCH /api/admin/users/{uuid}` — обновление (ФИО, телефон, роль, блокировка)
- `DELETE /api/admin/users/{uuid}` — soft delete + отзыв сессий

**Файлы:**
```
app/users/
├── __init__.py
├── routes_admin.py  — все 5 эндпоинтов, защита через router-level require_role
├── schemas.py       — Query, ListItem, Paginated, Create, CreateResponse, Update, Read
├── service.py       — get_users_list, create_user, get_user, update_user, delete_user
└── storage.py       — find_users, get_user_by_uuid, update_user, soft_delete_user, create_user
```

**Важные решения:**
- URL использует UUID (`/api/admin/users/{uuid}`), не INT id
- Защита на уровне роутера: `dependencies=[Depends(require_role("admin"))]`
- `POST /api/admin/users` — только роли `psychologist` и `admin` (student регистрируется сам)
- Пароль генерируется автоматически через `secrets`, отправляется на email
- Soft delete: выставляет `deleted_at` + `is_active=False` + отзывает все сессии
- UUID-валидация во всех storage-функциях перед запросом в БД
- Фильтрация по полям: whitelist `ALLOWED_SORT_FIELDS` для защиты от инъекций
- `student` в `PATCH` роль — намеренно исключён. Если понадобится — добавить в `AdminUserUpdate.role`

**Дополнительно:**
```
app/services/
├── email_sender.py    — SMTP транспорт
└── email_service.py   — send_registration_otp, send_password_reset_otp,
                         send_welcome_psychologist (новое)
```

---

### Frontend: Auth (полностью)

Регистрация, логин, восстановление пароля — работают end-to-end.

**Ключевые файлы:**
```
src/features/auth/
├── AuthContext.jsx       — user, token, login(), logout()
├── authUtils.js
├── ui/
│   ├── LoginForm.jsx
│   └── RegisterForm.jsx  (с чекбоксом согласия на ПДн)
└── forgot-password/      — полный stepper (email → OTP → новый пароль → успех)
    ├── ForgotPasswordModal.jsx
    ├── ForgotPasswordStepper.jsx
    ├── hooks/useForgotPassword.js
    ├── components/OTPInput.jsx, PasswordStrength.jsx
    └── steps/StepEmail, StepOTP, StepNewPassword, StepSuccess
```

**Роутинг (AppRoutes.jsx):**
- `/student` → `ClientDashboard` (Auth + role: student)
- `/psychologist` → `ConsultantDashboard` (Auth + role: psychologist)
- `/admin` → `AdminDashboard` (Auth + role: admin)
- `ProtectedRoute`: нет user → `/`, неверная роль → `/`

**Транспорт (`api/client.js`):**
- `apiFetch(url, options)` — добавляет Bearer токен
- При 401 → `window.dispatchEvent(new Event('auth:session-expired'))`
- `configureClient({ getToken })` — инициализация

---

### База данных

PostgreSQL 15+, 38 таблиц, миграции в `db/sql/`.

**Применение:**
```bash
psql -U postgres -d mindcare -f db/sql/full_schema.sql
```

**Таблица `otp_verifications`** — создаётся через `create_all` в `main.py` (не в SQL-схеме).

**Seed-данные** (из `010_seed_data.sql`):
- Роли: student, psychologist, admin, supervisor
- 19 permissions с привязкой к ролям
- 10 категорий
- 3 политики consent (privacy_policy, data_processing, test_consent)
- 6 шаблонов уведомлений

---

### Документация

- `CLAUDE.md` — обновлён, актуален. Включает стек, структуру, правила, бэклог, эндпоинты.
- `ARCHITECTURE.md` (в `mindcare_web/`) — обновлён. Добавлены разделы 6.1 (серверная фильтрация), hook-контракты.
- `DECISIONS.md` — ещё не создан (TODO)
- `BACKLOG.md` — ещё не создан (TODO, содержимое есть в CLAUDE.md)

---

## Открытые вопросы

1. **`student` в PATCH роли** — нужна ли операция «понизить до студента»? Пока исключена.
2. **consent_records для психологов** — при создании через POST не создаётся. Требует флага `must_accept_consent` при первом входе (Этап 2).
3. **Вопрос про `student` vs `client` терминология** — в БД роль `student`, в appointments — `client_id`. Оставить как есть (разные уровни абстракции).

---

## Текущий приоритет работы

### Frontend: AdminDashboard — список пользователей

**Что нужно сделать:**

Реализовать страницу списка пользователей в Admin панели.

По ARCHITECTURE.md (раздел 6.1 — серверная фильтрация):
- Hook: `useAdminUsers` по контракту `{ items, loading, error, total, page, setPage, query, setQuery, filters, setFilters, refetch }`
- API: `src/api/admin.api.js` — функция `getUsers(params)`
- Feature: `src/features/admin-users/` — компоненты таблицы
- Page: `src/pages/admin/AdminDashboard.jsx` — только композиция

**Что сейчас:**
- `AdminDashboard.jsx` — stub (только приветствие и logout)
- `DashboardLayout.jsx` — готов (Navbar + main + Footer)
- `api/client.js` — готов (apiFetch с токеном)

**Стиль:** Смотреть на `src/pages/client/ClientDashboard.jsx` (личный кабинет студента) — делать похожее.

**Бэкенд готов:**
```
GET /api/admin/users?page=1&size=20&search=...&role=...&is_active=...&sort=...&order=...

Ответ:
{
  "items": [{ id, uuid, email, full_name, role, is_active, created_at, last_login }],
  "total": 142,
  "page": 1,
  "size": 20
}
```

---

## Критические риски (не забыть)

1. **Партиции audit-таблиц закончатся 31.12.2026** → логин сломается. Нужен скрипт автогенерации.
2. **`session_notes.content` не шифруется** — в схеме обещано, не реализовано.
3. **OTP хранится открытым текстом** — в бэклоге.

---

## Следующие модули после AdminDashboard фронта

1. **Content** (`app/content/`) — CRUD статей и новостей. Модели в БД есть (`articles`, `news`, `categories`).
2. **Appointments** — запись на консультации. Самый сложный модуль (календарь, слоты).
3. **Tests** — психодиагностика.
4. **Личные кабинеты** — студент, психолог.

---

## Первое сообщение для нового стратегического чата

```
Прочитай CLAUDE.md и docs/HANDOFFS/2026-05-14-auth-users-complete.md.

Проект: MindCare — платформа психологической службы ДонГУ.
Бэкенд модули auth и users (admin) полностью готовы.

Сейчас начинаем фронт: страница списка пользователей в AdminDashboard.

Прочитай также:
- ARCHITECTURE.md (правила фронта)
- src/pages/admin/AdminDashboard.jsx (текущий stub)
- src/api/client.js (транспортный слой)
- src/components/layouts/DashboardLayout.jsx (layout)
- src/pages/client/ClientDashboard.jsx (пример стиля)

После прочтения — предложи план реализации.
Файлы не трогай, только обсуждение.
```

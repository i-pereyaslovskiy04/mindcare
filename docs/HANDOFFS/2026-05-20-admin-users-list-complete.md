# Handoff: Admin Users — список готов, CRUD-модалки следующие — 2026-05-20

## Состояние проекта

**Проект:** MindCare — платформа психологической службы ДонГУ  
**Этап:** MVP (Этап 1)  
**Стек:** FastAPI + SQLAlchemy (sync, psycopg2) + PostgreSQL 15+ / React 19 + CRA + CSS Modules

---

## Что полностью готово

### Backend: модуль `app/users/`

Полный CRUD для управления пользователями (только для admin).

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/admin/users` | Список с пагинацией, фильтрами, поиском |
| POST | `/api/admin/users` | Создание психолога/админа + автопароль + email |
| GET | `/api/admin/users/{uuid}` | Профиль пользователя |
| PATCH | `/api/admin/users/{uuid}` | Обновление (ФИО, телефон, роль, блокировка) |
| DELETE | `/api/admin/users/{uuid}` | Soft delete + отзыв всех сессий |

**Важные решения:**
- URL использует UUID, не INT id
- Защита на уровне роутера: `dependencies=[Depends(require_role("admin"))]`
- `POST` создаёт только роли `psychologist` и `admin` (student регистрируется сам)
- Пароль генерируется автоматически через `secrets`, отправляется на email
- Soft delete: `deleted_at` + `is_active=False` + отзыв всех сессий
- `is_active=False` без `deleted_at` = временная блокировка (аккаунт существует, email занят)
- Реактивация: если email принадлежит soft-deleted аккаунту и пользователь регистрируется заново — `reactivate_user()` обновляет старую запись вместо INSERT (избегает UniqueViolation)

**Файлы:**
```
app/users/
├── __init__.py
├── routes_admin.py  — все 5 эндпоинтов
├── schemas.py       — AdminUserCreate, AdminUserUpdate, AdminUserRead, AdminUserListItem
├── service.py       — get_users_list, create_user, get_user, update_user, delete_user
└── storage.py       — find_users, get_user_by_uuid, update_user, soft_delete_user, create_user

app/auth/storage.py  — добавлена reactivate_user()
```

---

### Frontend: Admin Users список

**Роутинг:**
```
/admin           → AdminDashboard (AdminLayout + Outlet)
  index          → redirect на /admin/users
  /admin/users   → UsersPage
```

**Файлы:**
```
src/
├── api/
│   └── admin.api.js                      — getUsers(params)
├── features/
│   └── admin-users/
│       ├── hooks/
│       │   └── useAdminUsers.js          — server-side list hook
│       └── ui/
│           ├── UsersFilters.jsx          — поиск + фильтр роли + фильтр статуса
│           ├── UsersFilters.module.css
│           ├── UsersTable.jsx            — таблица + скелетон
│           └── UsersTable.module.css
└── pages/
    └── admin/
        ├── AdminLayout.jsx               — sidebar + topbar + Outlet
        ├── AdminLayout.module.css
        ├── AdminDashboard.jsx            — рендерит AdminLayout
        └── users/
            ├── UsersPage.jsx             — только композиция
            └── UsersPage.module.css
```

**Hook-контракт `useAdminUsers`:**
```js
return { items, loading, error, total, page, setPage,
         query, setQuery, filters, setFilters, refetch }
```

**Sidebar AdminLayout:** Пользователи (активный) + Контент (disabled) + Тесты (disabled)

---

## Текущий приоритет: CRUD-действия в Admin Users

### Что нужно реализовать

Три действия над пользователями прямо в таблице:

#### 1. Создание пользователя

**Триггер:** кнопка «Добавить пользователя» над таблицей  
**UI:** модальное окно  
**API:** `POST /api/admin/users`

Поля формы:
| Поле | Тип | Валидация |
|------|-----|-----------|
| ФИО (`full_name`) | text | обязательное, ≥ 2 символа |
| Email (`email`) | email | обязательное, формат email |
| Роль (`role`) | select | `psychologist` / `admin` |

Пароль не вводится — генерируется на бэке и отправляется на email.  
После успеха → закрыть модалку → `refetch()` списка.

Схема запроса:
```json
{ "full_name": "...", "email": "...", "role": "psychologist" }
```

Схема ответа:
```json
{ "uuid": "...", "full_name": "...", "email": "...", "role": "...",
  "temporary_password": "..." }
```

#### 2. Редактирование пользователя

**Триггер:** клик по строке таблицы или иконка карандаша  
**UI:** модальное окно с предзаполненными полями  
**API:** `GET /api/admin/users/{uuid}` (загрузка) + `PATCH /api/admin/users/{uuid}` (сохранение)

Редактируемые поля:
| Поле | Тип |
|------|-----|
| ФИО (`full_name`) | text |
| Телефон (`phone`) | text |
| Роль (`role`) | select: `psychologist` / `admin` / `supervisor` |
| Статус (`is_active`) | toggle/checkbox |

Нередактируемые (показать, но задизейблить): email, UUID, дата регистрации.

После успеха → закрыть модалку → `refetch()`.

#### 3. Удаление пользователя

**Триггер:** иконка корзины в строке таблицы  
**UI:** диалог подтверждения (не полная модалка — просто «Вы уверены?» + две кнопки)  
**API:** `DELETE /api/admin/users/{uuid}`

После успеха → `refetch()`.

---

### Какие файлы создать

```
src/
├── api/
│   └── admin.api.js                      — ДОПОЛНИТЬ: createUser, getUser,
│                                            updateUser, deleteUser
└── features/
    └── admin-users/
        ├── hooks/
        │   └── useUserForm.js            — NEW: form hook для создания/редактирования
        └── ui/
            ├── UserCreateModal.jsx       — NEW
            ├── UserCreateModal.module.css
            ├── UserEditModal.jsx         — NEW
            ├── UserEditModal.module.css
            └── DeleteConfirmDialog.jsx   — NEW (inline, без отдельного CSS)
```

`UsersPage.jsx` — дополнить: кнопка «Добавить», состояния `selectedUuid` и `isCreateOpen`,
передать колбэки в `UsersTable`.

`UsersTable.jsx` — дополнить: колонка «Действия» с иконками карандаша и корзины.

### Hook-контракт `useUserForm`

```js
// создание
const { values, errors, loading, handleChange, handleSubmit, reset } = useUserForm({ mode: 'create' })

// редактирование
const { values, errors, loading, handleChange, handleSubmit } = useUserForm({ mode: 'edit', uuid })
```

При `mode: 'edit'` — загружает пользователя через `getUser(uuid)` при mount.

---

## Известные проблемы в бэклоге

Полный список — в [`docs/BACKLOG.md`](../BACKLOG.md).

Критические:
- Партиции `auth_log`, `audit_log`, `data_change_log` захардкожены до **31.12.2026**
- `session_notes.content` хранится открытым текстом
- OTP-коды хранятся plaintext

Нерешённое из ревью (в бэклоге, не трогать без запроса):
- CSS-классы ролей в `UsersTable`: `role_student` → `roleStudent`
- Асимметрия `supervisor`: в `AdminUserUpdate` есть, в `AdminUserCreate` нет
- `phone` не стрипается при update
- `authApi.register` — неиспользуемый экспорт в `AuthContext.jsx`

---

## Исключения из правил (задокументированы)

**`AuthContext.jsx` использует нативный `fetch()` напрямую** — намеренно.
Использование `apiFetch` создало бы циклическую зависимость при 401-обработке.
Задокументировано в `ARCHITECTURE.md` раздел 2.

---

## Следующие модули после Admin Users CRUD

1. **Admin Content** — CRUD статей и новостей (`articles`, `news`, `categories` в БД)
2. **Admin Tests** — управление тестами психодиагностики
3. **Appointments** — запись на консультации (самый сложный модуль)
4. **Личные кабинеты** — психолог, студент

---

## Первые сообщения для чатов

### Стратегический чат

```
Прочитай CLAUDE.md и docs/HANDOFFS/2026-05-20-admin-users-list-complete.md.

Проект: MindCare — платформа психологической службы ДонГУ.
Список пользователей в AdminDashboard реализован и прошёл ревью.

Следующий шаг: CRUD-действия в модуле Admin Users —
создание, редактирование и удаление пользователей через модальные окна.

Прочитай также:
- mindcare_web/ARCHITECTURE.md
- mindcare_web/src/api/admin.api.js
- mindcare_web/src/features/admin-users/hooks/useAdminUsers.js
- mindcare_web/src/features/admin-users/ui/UsersTable.jsx
- mindcare_web/src/pages/admin/users/UsersPage.jsx
- mindcare_web/src/components/Modal/Modal.jsx (готовый примитив)

После прочтения — предложи план реализации.
Файлы не трогай, только обсуждение.
```

---

### Чат для работы с кодом

```
Это implementation-чат проекта MindCare.
Прочитай CLAUDE.md и docs/HANDOFFS/2026-05-20-admin-users-list-complete.md.
Жди конкретные задачи на изменение кода.
Перед каждым изменением — план что и зачем меняешь, после моего OK — реализация.
```

---

### Чат ревью

```
Это ревью-чат проекта MindCare.
Прочитай CLAUDE.md и mindcare_web/ARCHITECTURE.md.
ТВОЯ РОЛЬ:
- Прочитать указанные файлы
- Найти проблемы (безопасность, производительность, архитектура)
- Не править — только репортить
- Конкретные предложения как починить (но не делать)
Жди конкретный фокус ревью.
```

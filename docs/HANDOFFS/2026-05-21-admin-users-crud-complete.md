# Handoff: Admin Users CRUD + дизайн админки — 2026-05-21

## Состояние проекта

**Проект:** MindCare — платформа психологической службы ДонГУ  
**Этап:** MVP (Этап 1)  
**Стек:** FastAPI + SQLAlchemy (sync, psycopg2) + PostgreSQL 15+ / React 19 + CRA + CSS Modules

---

## Что полностью готово

### Backend: фикс AdminUserUpdate

`AdminUserUpdate.role` теперь включает все четыре роли:
```python
role: Optional[Literal["student", "psychologist", "admin", "supervisor"]]
```
**Причина:** без `"student"` любое PATCH-действие над студентом (включая блокировку)
возвращало 422 — Pydantic отклонял валидное значение роли.

**Файл:** `mindcare_api/app/users/schemas.py`

---

### Frontend: Admin Users CRUD

Полный цикл управления пользователями в AdminDashboard.

**Роутинг:**
```
/admin           → AdminLayout (features/admin/AdminLayout.jsx)
  index          → redirect на /admin/users
  /admin/users   → UsersPage
```

**Файлы:**
```
src/
├── api/
│   └── users.api.js                          — getUsers, getUser, createUser,
│                                               updateUser, deleteUser
├── app/
│   └── router.jsx                            — полный роутер с PrivateRoute / RoleRoute
└── features/
    └── admin/
        ├── AdminLayout.jsx                   — сайдбар + топбар + Outlet
        ├── AdminLayout.module.css
        └── users/
            ├── hooks/
            │   ├── useAdminUsers.js          — server-side list hook
            │   └── useUserForm.js            — form hook (create + edit)
            ├── components/
            │   ├── UsersFilters.jsx          — поиск + фильтры
            │   ├── UsersTable.jsx            — таблица + скелетон + иконки действий
            │   ├── UserCreateModal.jsx       — создание (2 экрана: форма → пароль)
            │   ├── UserEditModal.jsx         — редактирование с загрузкой данных
            │   └── DeleteConfirmDialog.jsx   — подтверждение удаления
            └── pages/
                └── UsersPage.jsx             — композиция, состояния модалок
```

**Hook-контракт `useUserForm`:**
```js
// Create
const { values, errors, loading, submitting, handleChange, handleSubmit, reset }
  = useUserForm({ mode: 'create', onSuccess })

// Edit — загружает getUser(uuid) при mount
const { values, errors, loading, submitting, handleChange, handleSubmit }
  = useUserForm({ mode: 'edit', uuid, onSuccess })
```

**Важные решения:**
- `users.api.js` вместо расширения `admin.api.js` — отдельный файл с `const BASE`
- `client.js`: добавлен `if (res.status === 204) return null` — DELETE не падает на пустом теле
- `client.js`: добавлен `credentials: 'include'` — подготовка к cookie-auth (пришло из влитой ветки)
- `useUserForm` — два флага: `loading` (загрузка данных) и `submitting` (отправка формы)
- `onSuccess` передаётся в hook как параметр — hook сам вызывает после успеха
- `updateUser` отправляет все поля целиком, не diff — бэк поддерживает partial update
- Edit-модалка получает `userInfo` (объект строки таблицы) как prop для нередактируемых полей — без дублирования запроса
- `useUserForm` useEffect: `if (!uuid) return` — защита от запроса с null

**Ошибки в формах (стандарт ARCHITECTURE.md §10):**
```js
errors = { full_name: 'Минимум 2 символа' }  // клиентская ошибка поля
errors = { _form: 'Email уже занят' }         // серверная / общая ошибка
```

---

### Frontend: дизайн AdminLayout

AdminLayout приведён к стилю StudentLayout:

| Элемент | Было | Стало |
|---------|------|-------|
| Ширина сайдбара | 240px | 264px |
| Бренд | «MindCare Admin» sans-serif | «Психология ДонГУ» Cormorant Garamond |
| Блок пользователя | отсутствовал | аватар с инициалами + имя + роль |
| Иконки в навигации | нет | users / articles / tests |
| Активный пункт | `--cream` фон | `--espresso` фон, светлый текст |
| Топбар справа | текст с именем | иконка выхода |
| Футер сайдбара | кнопка «Выйти» | текст университета + email |

Иконка `users` и `edit` добавлены в `Icon.jsx`.

---

### Frontend: дизайн таблицы и страницы

- `UsersPage.module.css`: serif-заголовок, fadeIn-анимация, border-radius 10px на кнопках
- `UsersTable.module.css`: border-radius 16px, box-shadow как у student-карточек,
  иконки-кнопки (edit/trash) вместо текстовых, hover с translateY + shadow
- `UsersFilters.module.css`: border-radius 10px

---

## Изменения в документации

- **`ARCHITECTURE.md §10`** — добавлен стандарт «Error handling в формах»
- **`ARCHITECTURE.md §8`** — добавлен пункт 8.4 (LoginForm устаревший паттерн)
- **`DECISIONS.md`** — 5 ADR: ADR-001 по ADR-005
- **`BACKLOG.md`** — добавлены записи: дублирование CSS модалок, setState после закрытия,
  двойной submit, LoginForm паттерн, удалённые пользователи (🔵 Запланировано)

---

## Известные проблемы (бэклог)

Полный список — в [`docs/BACKLOG.md`](../BACKLOG.md).

Нерешённое (технический долг):
- Дублирование стилей UserCreateModal / UserEditModal → вынести в `adminModal.module.css`
- `DeleteConfirmDialog` — setState на скрытом компоненте при Escape во время запроса
- `useUserForm` — нет guard-а от двойного submit
- `LoginForm` — устаревший паттерн ошибок (`errors` булевы + `apiError`)

Запланировано:
- Показ удалённых пользователей (фильтр + визуальный индикатор)

---

## Структура роутера (актуальная)

```
/                    → Home (public)
/about               → About (public)
/services            → Services (public)
/news, /news/:id     → NewsPage, NewsItemPage (public)
/materials, ...      → MaterialsPage, MaterialsItemPage (public)
/health              → HealthPage (public)
/login               → LoginPage (public)
/register            → RegisterPage (public)
/dashboard           → DashboardRedirect (private, по роли)
/profile             → ProfilePage (private)
/student/*           → StudentLayout + вложенные страницы (role: student)
/psychologist        → ConsultantDashboard (role: psychologist)
/admin/*             → AdminLayout + UsersPage (role: admin, supervisor)
```

Route guards: `PrivateRoute` (требует auth), `RoleRoute` (требует роль).

---

## Code Review — результаты (2026-05-21)

Проведён полный security review модуля Admin Users. Найдено 17 проблем.

### Исправлено

| # | Проблема | Файл |
|---|---------|------|
| 1 | Supervisor получал 403 на все API-запросы | `routes_admin.py` → `require_role("admin", "supervisor")` |
| 2 | Нельзя создать supervisor через UI | `schemas.py` + `UserCreateModal.jsx` |
| 3 | Email не валидировался на бэке | `schemas.py` → `EmailStr` |
| 4 | `temporary_password` не возвращался в ответе | `schemas.py` + `service.py` |
| 5 | Нет лимита длины поиска | `schemas.py` + `routes_admin.py` → `max_length=200` |
| 6 | Нет аудит-лога admin-операций | `routes_admin.py` → `log_auth_event` с UUID цели |
| 8 | `credentials: 'include'` без CSRF-защиты | `client.js` — убрано |
| 10 | outerjoin без DISTINCT — дубли при нескольких ролях | `storage.py` → `_ROLE_PRIORITY` + коррелированный подзапрос |
| 11 | `phone` пустая строка вместо NULL | `storage.py` → `phone.strip() or None` |
| 12 | Фильтр `role` не валидировался | `schemas.py` → `Literal` |
| 13 | `PAGE_SIZE` не синхронизирован с хуком | `useAdminUsers.js` + `UsersPage.jsx` |
| 16 | Импорт `UserSession` внутри функции | `storage.py` → перенесён наверх |
| — | `full_name` пустая строка после `strip()` | `storage.py` → валидация после стрипа |
| — | `phone` не нормализован в `create_user` | `storage.py` → `phone.strip() or None` |
| — | Фильтр по роли сломан после рефакторинга JOIN | `storage.py` → `User.id.in_(subquery)` |

### В бэклоге

- #7 Самоудаление / удаление последнего админа
- #9 Soft-deleted email в admin-создании → реактивация
- #14 `DeleteConfirmDialog` инлайн-стили (намеренно)
- #17 Белый экран при загрузке роутов
- Аудит: `target_user_id` как отдельное поле + логирование неудач

### Новые ADR

- **ADR-006** — UUID цели в строке события аудита (временное решение)
- **ADR-007** — `_ROLE_PRIORITY` для детерминированного выбора роли

---

## Следующие приоритеты

1. **Показ удалённых пользователей** — небольшая задача, в бэклоге §🔵
2. **Admin Content** — CRUD статей и новостей (`articles`, `news`, `categories` в БД)
3. **Admin Tests** — управление тестами психодиагностики
4. **Appointments** — запись на консультации (самый сложный модуль)
5. **Личные кабинеты** — психолог, студент (большинство страниц — заглушки)

---

## Первые сообщения для следующих чатов

### Стратегический чат

```
Прочитай CLAUDE.md и docs/HANDOFFS/2026-05-21-admin-users-crud-complete.md.

Проект: MindCare — платформа психологической службы ДонГУ.
Admin Users CRUD полностью реализован и протестирован.

Следующий шаг на выбор:
1. Показ удалённых пользователей в AdminDashboard (небольшая задача)
2. Admin Content — CRUD статей и новостей
3. Что-то другое

Прочитай также:
- mindcare_web/ARCHITECTURE.md
- docs/BACKLOG.md

После прочтения — предложи план реализации выбранного шага.
Файлы не трогай, только обсуждение.
```

### Чат для работы с кодом

```
Это implementation-чат проекта MindCare.
Прочитай CLAUDE.md и docs/HANDOFFS/2026-05-21-admin-users-crud-complete.md.
Жди конкретные задачи на изменение кода.
Перед каждым изменением — план что и зачем меняешь, после моего OK — реализация.
```

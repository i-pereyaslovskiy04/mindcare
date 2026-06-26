# MindCare Web — Architecture Document

> Updated: 2026-06-26
> Stack: React 19 · React Router 7 · CSS Modules · CRA (Create React App)
> Purpose: University psychology center — public informational site with role-based dashboards and a full authentication flow.

---

## 1. Project Tree

```
mindcare_web/
├── package.json               proxy → http://localhost:8000
└── src/
    ├── index.js               DOM entry point
    ├── reportWebVitals.js
    ├── setupTests.js          ← jest-dom matchers (CRA stale App.test.js removed)
    │
    ├── app/                   ← shell: providers + routing
    │   ├── App.jsx
    │   ├── providers.jsx
    │   └── router.jsx
    │
    ├── api/                   ← ALL HTTP calls live here
    │   ├── client.js          ← transport: token injection + 401 retry
    │   ├── auth.api.js
    │   ├── users.api.js       ← /api/admin/users/* (CRUD пользователей)
    │   ├── tags.api.js        ← /api/admin/tags/* + /api/tags (UI: «Темы»)
    │   ├── categories.api.js  ← /api/admin/categories/* (UI: «Типы материалов»)
    │   ├── news.api.js
    │   ├── articles.api.js
    │   ├── materials.api.js
    │   ├── supervisor.api.js  ← /api/supervisor/* (students, psychologists, engagements)
    │   ├── appointments.api.js
    │   ├── media.api.js       ← /api/media/upload
    │   └── health.api.js      ← /health
    │
    ├── shared/
    │   └── lib/
    │       └── utils.js       ← getInitials() и другие общие утилиты
    │
    ├── data/                  ← dev/mock data only
    │   ├── news.mock.js
    │   └── materials.mock.js
    │
    ├── hooks/                 ← app-wide reusable hooks
    │   ├── useDebounce.js
    │   ├── useNews.js
    │   └── useMaterials.js
    │
    ├── features/
    │   ├── auth/
    │   │   ├── AuthContext.jsx
    │   │   ├── ui/
    │   │   │   ├── AuthModal.jsx + .module.css
    │   │   │   ├── LoginForm.jsx
    │   │   │   └── RegisterForm.jsx
    │   │   ├── pages/
    │   │   │   ├── LoginPage.jsx
    │   │   │   └── RegisterPage.jsx
    │   │   └── forgot-password/
    │   │       ├── ForgotPasswordModal.jsx
    │   │       ├── ForgotPasswordStepper.jsx
    │   │       ├── hooks/
    │   │       │   └── useForgotPassword.js
    │   │       ├── components/
    │   │       │   ├── OTPInput.jsx
    │   │       │   └── PasswordStrength.jsx
    │   │       └── steps/
    │   │           ├── StepEmail.jsx
    │   │           ├── StepOTP.jsx
    │   │           ├── StepNewPassword.jsx
    │   │           └── StepSuccess.jsx
    │   ├── news/
    │   │   └── components/
    │   │       ├── NewsSection.jsx + .module.css
    │   │       ├── FeaturedNews.jsx
    │   │       ├── NewsCardSmall.jsx
    │   │       └── NewsListItem.jsx
    │   ├── profile/
    │   │   └── pages/
    │   │       └── ProfilePage.jsx
    │   ├── supervisor/          ← модуль назначения психологов (роль: supervisor)
    │   │   ├── hooks/
    │   │   │   └── useStudents.js
    │   │   └── components/
    │   │       └── AssignModal.jsx + .module.css
    │   └── admin/             ← панель управления (role: admin)
    │       ├── AdminLayout.jsx + .module.css
    │       ├── users/
    │       │   ├── hooks/
    │       │   │   ├── useAdminUsers.js
    │       │   │   └── useUserForm.js
    │       │   ├── components/
    │       │   │   ├── UsersTable.jsx + .module.css
    │       │   │   ├── UsersFilters.jsx + .module.css
    │       │   │   ├── UserCreateModal.jsx
    │       │   │   ├── UserEditModal.jsx
    │       │   │   └── DeleteConfirmDialog.jsx
    │       │   └── pages/
    │       │       └── UsersPage.jsx
    │       ├── categories/      ← UI: «Типы материалов»
    │       │   ├── hooks/
    │       │   │   └── useAdminCategories.js
    │       │   ├── components/
    │       │   │   ├── CategoriesTable.jsx + .module.css
    │       │   │   └── CategoryFormModal.jsx + .module.css
    │       │   └── pages/
    │       │       └── CategoriesPage.jsx + .module.css
    │       ├── tags/            ← UI: «Темы»
    │       │   ├── hooks/
    │       │   │   └── useAdminTags.js
    │       │   ├── components/
    │       │   │   ├── TagsTable.jsx + .module.css
    │       │   │   └── TagFormModal.jsx + .module.css
    │       │   └── pages/
    │       │       └── TagsPage.jsx + .module.css
    │       ├── news/
    │       │   ├── hooks/useAdminNews.js
    │       │   ├── components/NewsFormModal.jsx + NewsTable.jsx
    │       │   └── pages/NewsPage.jsx
    │       └── articles/
    │           ├── hooks/useAdminArticles.js
    │           ├── components/ArticleFormModal.jsx + ArticlesTable.jsx
    │           └── pages/ArticlesPage.jsx
    │
    ├── components/            ← domain-agnostic UI primitives
    │   ├── Icon/
    │   │   └── Icon.jsx       ← общий SVG-компонент (name, size, stroke)
    │   ├── CabinetLayout/     ← общий layout для кабинетов psychologist и supervisor
    │   │   ├── CabinetLayout.jsx + .module.css
    │   │   └── CabinetSettingsPage.jsx + .module.css
    │   ├── Modal/
    │   │   ├── Modal.jsx
    │   │   └── Modal.module.css
    │   ├── CodeInput/
    │   │   └── CodeInput.jsx + .module.css
    │   ├── Navbar/
    │   │   ├── Navbar.jsx
    │   │   └── Navbar.module.css
    │   ├── Footer/
    │   │   ├── Footer.jsx
    │   │   └── Footer.module.css
    │   ├── Hero/
    │   │   ├── PageHero.jsx
    │   │   └── PageHero.module.css
    │   ├── CookieBanner/
    │   │   ├── CookieBanner.jsx
    │   │   └── CookieBanner.module.css
    │   ├── UI/                    ← shared UI primitives (see docs/UI_COMPONENTS_GUIDE.md)
    │   │   ├── Button/
    │   │   │   ├── Button.jsx + .module.css
    │   │   │   └── ButtonLink.jsx     ← router <Link> styled as Button
    │   │   ├── Badge/
    │   │   ├── Checkbox/
    │   │   ├── FilterChip/
    │   │   ├── Select/
    │   │   ├── MultiSelect/
    │   │   │   ├── MultiSelect.jsx
    │   │   │   └── multiSelect.module.css
    │   │   ├── DateInput/             ← date-only picker (custom popover, no native datetime-local)
    │   │   │   ├── DateInput.jsx + .module.css
    │   │   │   ├── dateHelpers.js     ← isoToDateOnly / dateOnlyToPublishedAtIso
    │   │   │   └── popoverPosition.js ← computePopoverPosition (flip up/down + viewport clamp)
    │   │   ├── Tag/
    │   │   ├── Toggle/
    │   │   ├── TiptapEditor/
    │   │   │   └── TiptapEditor.jsx + .module.css
    │   │   ├── ImageUpload/
    │   │   │   └── ImageUpload.jsx + .module.css
    │   │   └── ContentPreview/
    │   │       └── ContentPreview.jsx + .module.css
    │   └── icons/
    │       └── index.jsx      ← старый набор иконок (публичная часть сайта)
    │
    ├── pages/                 ← composition only, no business logic
    │   ├── home/
    │   │   ├── Home.jsx
    │   │   └── components/
    │   │       ├── Hero.jsx + .module.css
    │   │       └── QuickActions.jsx + .module.css
    │   ├── about/
    │   │   ├── About.jsx
    │   │   └── components/
    │   │       └── (AboutIntro, AboutMission, AboutApproach, AboutServicesPreview, AboutTrust, AboutMedia)
    │   ├── services/
    │   │   ├── Services.jsx + .module.css
    │   │   └── components/
    │   │       └── (ServicesSlider, ServiceCard, ProcessBlock, PrinciplesBlock)
    │   ├── news/
    │   │   ├── NewsPage.jsx
    │   │   ├── NewsItemPage.jsx + .module.css
    │   │   └── components/
    │   │       ├── NewsGrid.jsx
    │   │       └── Pagination.jsx
    │   ├── materials/
    │   │   ├── MaterialsPage.jsx + .module.css
    │   │   ├── MaterialsItemPage.jsx + .module.css
    │   │   └── components/
    │   │       └── (SearchBar, FiltersDropdown, FilterSheet, MaterialsGrid, MaterialCard)
    │   ├── health/
    │   │   └── HealthPage.jsx
    │   ├── not-found/
    │   │   ├── NotFound.jsx
    │   │   └── NotFound.module.css
    │   ├── client/
    │   │   └── ClientDashboard.jsx  ← Router Outlet-обёртка для /student/*
    │   ├── student/             ← кабинет студента (собственный layout с Sidebar)
    │   │   ├── StudentLayout.jsx
    │   │   ├── StudentHome.jsx
    │   │   ├── DiaryPage.jsx
    │   │   ├── components/
    │   │   │   ├── Sidebar/Sidebar.jsx + .module.css
    │   │   │   ├── MoodChart/MoodChart.jsx
    │   │   │   ├── StatCard/StatCard.jsx
    │   │   │   └── Diary/ (MoodSelector, DiaryEntryForm, DiaryHistoryList, DiaryEntryItem)
    │   │   ├── Tests/TestsPage.jsx
    │   │   ├── Materials/MaterialsPage.jsx + useStudentMaterials.js
    │   │   ├── Tasks/TasksPage.jsx + components/TaskItem.jsx
    │   │   ├── Chat/ChatPage.jsx + components/
    │   │   ├── Calendar/CalendarPage.jsx + components/ + utils/ (real appointments API)
    │   │   ├── GroupSessions/GroupSessionsPage.jsx
    │   │   └── Settings/SettingsPage.jsx
    │   ├── psychologist/        ← кабинет психолога (использует CabinetLayout)
    │   │   ├── PsychologistLayout.jsx
    │   │   └── PsychologistHome.jsx
    │   │   ├── PsychologistStudentsPage.jsx
    │   │   ├── PsychologistStudentCardPage.jsx
    │   │   ├── Appointments/ (AppointmentsPage, PsychologistCalendar, ScheduleTab)
    │   │   └── Chat/
    │   └── supervisor/          ← кабинет супервизора (использует CabinetLayout)
    │       ├── SupervisorLayout.jsx
    │       ├── SupervisorHome.jsx
    │       ├── EngagementsPage.jsx  ← назначения психологов
    │       ├── MeetingTypesPage.jsx
    │       ├── SchedulePage.jsx
    │       ├── BookingPage.jsx
    │       └── GroupSessionsPage.jsx
    │
    └── styles/
        ├── variables.css      ← CSS custom properties (colors, spacing)
        └── global.css         ← reset, typography, utility classes
```

---

## 2. Layer Rules (strict)

### Pages — только композиция

```
✅ компонуют UI секции
✅ вызывают hooks для получения данных
✅ открывают модальные окна
❌ не делают fetch напрямую
❌ не содержат фильтрацию/сортировку
❌ не импортируют из data/ напрямую
```

### Features — бизнес-логика

Каждый домен (`auth`, `news`, `admin`, `supervisor`) содержит компоненты, которые:
- знают о доменных концепциях (user, engagement, psychologist)
- могут вызывать hooks и Context
- не переиспользуются за пределами своего feature

### API слой — единственная точка HTTP

```
src/api/
  client.js           ← transport (token injection + 401 retry)
  auth.api.js
  users.api.js        ← getUsers, getUser, createUser, updateUser, deleteUser
  tags.api.js         ← getTags, createTag, updateTag, deleteTag, getTagsPublic
  categories.api.js   ← getAdminCategories, createCategory, updateCategory, deleteCategory
  news.api.js         ← getNews, getNewsById + admin CRUD
  articles.api.js     ← getArticles, getArticleById + admin CRUD
  materials.api.js    ← реэкспорт getArticles/getArticleById из articles.api.js
  supervisor.api.js   ← getSupervisorStudents, getSupervisorPsychologists,
                         getSupervisorEngagements, createEngagement,
                         transferEngagement, closeEngagement
  appointments.api.js
  media.api.js        ← uploadMedia
  health.api.js
```

До реализации соответствующего бэкенд-эндпоинта `*.api.js` может импортировать mock из `data/`. После подключения к API импорт удаляется. См. раздел 6 для полных правил работы с моками.

**Запрещено:** API в `services/`, API внутри `pages/`, API внутри `components/`

**Исключение — `features/auth/AuthContext.jsx`:** использует нативный `fetch()` напрямую (не через `apiFetch`). Это намеренно: `AuthContext` сам настраивает `client.js` через `configureClient()` и обрабатывает событие `auth:session-expired`. Использование `apiFetch` внутри `AuthContext` создало бы циклическую зависимость при 401-обработке. Все остальные модули используют только `apiFetch`.

### Components — domain-agnostic примитивы

```
✅ принимают всё через props
✅ без fetch, без Context (кроме AuthContext в Navbar)
✅ переиспользуются в любом feature или page
❌ без доменных концепций ("user", "news", "engagement")
```

**Icon** (`components/Icon/Icon.jsx`) — единственный общий SVG-компонент для иконок в кабинетах и adminпанели. Props: `name`, `size=18`, `stroke=1.5`. Не имеет CSS-модуля (чистый SVG).

**CabinetLayout** (`components/CabinetLayout/`) — общий layout для кабинетов psychologist и supervisor. Принимает `navSections` и `crumbLabels` как конфигурацию. Не используется в student cabinet.

### Shared — общие утилиты

```
src/shared/lib/utils.js
  getInitials(name)  ← единственная каноническая версия.
                        Используется в CabinetLayout, AdminLayout, CabinetSettingsPage.
```

Не размещать утилиты в `components/` или `hooks/` если они не связаны с React.

### Hooks — переиспользуемая логика

```
src/hooks/
  useDebounce.js     ← generic utility
  useNews.js         ← data fetching + pagination state
  useMaterials.js    ← filter/sort/pagination state (подключён к API)
```

Pages используют **только hooks**, никогда не делают fetch самостоятельно.

### Data — только для dev/mock

```
src/data/
  news.mock.js
  materials.mock.js
```

Импортируются исключительно из `api/*.api.js`. Все остальные слои работают через API.

---

## 3. Routing

**Файл:** `src/app/router.jsx`

| Route | Component | Guard |
|---|---|---|
| `/` | `Home` | Public |
| `/about` | `About` | Public |
| `/services` | `Services` | Public |
| `/news` | `NewsPage` | Public |
| `/news/:id` | `NewsItemPage` | Public |
| `/materials` | `MaterialsPage` | Public |
| `/materials/:id` | `MaterialsItemPage` | Public |
| `/health` | `HealthPage` | Public |
| `/login` | `LoginPage` | Public |
| `/register` | `RegisterPage` | Public |
| `/dashboard` | `DashboardRedirect` | Auth (редирект по роли) |
| `/profile` | `ProfilePage` | Auth |
| `/student` | `ClientDashboard` (Outlet) | Auth + role: student |
| `/student/diary` | `DiaryPage` | — (наследует от `/student`) |
| `/student/tests` | `TestsPage` | — |
| `/student/materials` | `StudentMaterialsPage` | — |
| `/student/tasks` | `TasksPage` | — |
| `/student/chat` | `ChatPage` | — |
| `/student/calendar` | `CalendarPage` | — |
| `/student/group-sessions` | `StudentGroupSessionsPage` | — |
| `/student/settings` | `SettingsPage` | — |
| `/psychologist` | `PsychologistLayout` (Outlet) | Auth + role: psychologist |
| `/psychologist/students` | `PsychologistStudentsPage` | — |
| `/psychologist/students/:studentId` | `PsychologistStudentCardPage` | — |
| `/psychologist/appointments` | `PsychologistAppointmentsPage` | — |
| `/psychologist/chat` | `PsychologistChatPage` | — |
| `/psychologist/settings` | `CabinetSettingsPage` | — |
| `/supervisor` | `SupervisorLayout` (Outlet) | Auth + role: supervisor |
| `/supervisor/engagements` | `EngagementsPage` | — |
| `/supervisor/meeting-types` | `MeetingTypesPage` | — |
| `/supervisor/schedule` | `SchedulePage` | — |
| `/supervisor/booking` | `BookingPage` | — |
| `/supervisor/group-sessions` | `GroupSessionsPage` | — |
| `/supervisor/settings` | `CabinetSettingsPage` | — |
| `/admin` | `AdminLayout` (Outlet) | Auth + role: admin |
| `/admin/users` | `UsersPage` | — (наследует от `/admin`) |
| `/admin/categories` | `CategoriesPage` | — (UI: «Типы материалов») |
| `/admin/tags` | `TagsPage` | — (UI: «Темы») |
| `/admin/news` | `AdminNewsPage` | — |
| `/admin/articles` | `AdminArticlesPage` | — |
| `*` | `NotFound` | Public |

**DashboardRedirect** — умный редирект по роли:

| Роль | Редирект |
|------|----------|
| `student` | `/student` |
| `psychologist` | `/psychologist` |
| `supervisor` | `/supervisor` |
| `admin` | `/admin/users` |

**Guards:**
- `PrivateRoute` — требует аутентификации, редирект на `/login`
- `RoleRoute` — требует указанную роль, редирект на `/profile` при несоответствии
- Пока auth восстанавливается — рендерит `null` (без белого экрана — в бэклоге)

---

## 4. Authentication

### Token Lifecycle

```
LoginForm → POST /api/auth/login
               │
               ▼
         AuthContext.login(token, user)
               │
               ├─▶ localStorage: access_token
               └─▶ setState({ user }) → App re-renders
```

### 401 Retry (api/client.js)

```
apiFetch() → 401
               │
               ▼
         logout() + dispatch auth:session-expired
               │
               ▼
         redirect → /login
```

### Session Restore

```
AuthProvider mount → read localStorage
  → token present: GET /api/auth/me → setState
  → token absent: user = null
```

### ProtectedRoute

```jsx
if (!user) return <Navigate to="/login" />;
if (roles && !roles.includes(user.role)) return <Navigate to="/profile" />;
```

---

## 5. Key Modules

### CabinetLayout

Общий layout, используемый кабинетами **psychologist** и **supervisor**.

```
CabinetLayout (components/CabinetLayout/)
├── Sidebar с navSections (конфигурируется каждым Layout)
├── Breadcrumbs через crumbLabels
├── Avatar с getInitials() из shared/lib/utils.js
└── <Outlet /> для вложенных маршрутов

PsychologistLayout → CabinetLayout (navSections = рабочие секции психолога)
SupervisorLayout   → CabinetLayout (navSections = секции супервизии)

CabinetSettingsPage — общая страница настроек, подключается в обоих кабинетах
  через /psychologist/settings и /supervisor/settings
```

Student cabinet **не использует** CabinetLayout — у него собственный `StudentLayout` со своим Sidebar.

### Modal System

```
Modal.jsx (primitive)
├── createPortal → document.body
├── Focus trap (Tab cycling)
├── Escape → onClose
├── Saves/restores focus
└── exposes focusFirst() via useImperativeHandle

AuthModal (zIndex=2000)         → <Modal> → LoginForm / RegisterForm
ForgotPasswordModal (zIndex=2100) → <Modal> → ForgotPasswordStepper
AssignModal                     → <Modal> → форма назначения психолога
```

### Forgot Password Flow

```
ForgotPasswordModal
└── ForgotPasswordStepper (state machine via useForgotPassword)
    ├── StepEmail    → forgotPassword(email)
    ├── StepOTP      → OTPInput + resend countdown
    ├── StepNewPassword → PasswordStrength meter
    └── StepSuccess
```

### Supervisor Engagements

Модуль управления связями студент ↔ психолог. Доступен только роли `supervisor`.

```
/supervisor/engagements
└── EngagementsPage (pages/supervisor/)
    ├── useStudents (features/supervisor/hooks/)
    │   └── getSupervisorStudents() → api/supervisor.api.js
    ├── таблица студентов (имя, email, текущий психолог, статус)
    ├── поиск с debounce 300ms
    ├── пагинация (серверная)
    └── AssignModal (features/supervisor/components/)
        ├── mode="assign"   → createEngagement()
        ├── mode="transfer" → transferEngagement()
        └── mode="close"    → closeEngagement()
```

**Три сценария в AssignModal:**
- `assign` — назначить психолога (engagement не существует)
- `transfer` — переназначить (смена психолога в активном engagement)
- `close` — закрыть связь (завершить engagement)

После успешного действия: `closeModal() → refetch()`.

Список психологов для выбора загружается через `getSupervisorPsychologists()` при открытии modal режима assign/transfer. Применяется `cancelled`-флаг для защиты от race condition при размонтировании.

### Materials Filter (SearchBar)

```
SearchBar
├── desktop: FiltersDropdown (absolute div, no portal)
└── mobile:  FilterSheet (createPortal bottom sheet)

Both share: tag multiselect + sort radio + clear
State lives in: useMaterials hook → MaterialsPage props → SearchBar
```

### Admin UI terminology

В пользовательском интерфейсе админки используются продуктовые названия:
- `/admin/categories` отображается как «Типы материалов»
- `/admin/tags` отображается как «Темы»

Технические имена API, модулей и моделей остаются `categories` и `tags`.
Не переименовывать файлы и URL ради UI-терминов.

---

## 6. Data Flow

```
User interaction
       ↓
Custom hook (useStudents, useAdminUsers, ...)
       ↓
api/<domain>.api.js
       ↓
api/client.js (token injection + 401 retry)
       ↓
FastAPI backend → PostgreSQL
       ↓
setState in hook → Page re-renders
```

**Правила работы с `data/` (моки):**

`data/` содержит mock-данные только для разработки UI компонентов в момент, когда соответствующий API-эндпоинт ещё не реализован на бэке.

Hook может временно импортировать из `data/` напрямую — но это всегда временное состояние.

**Как только бэк-эндпоинт готов:**

- Hook переводится на `api/<domain>.api.js`
- Прямой импорт из `data/` удаляется из hook

**Запрещено:** оставлять `try API → catch fallback to mock` как постоянный паттерн в production-коде.

**Все новые модули после 2026-05-20** реализуются сразу через API — без промежуточного этапа с моками.

---

## 6.1 Server-side filtering & pagination

**Правило:** Любой список из БД фильтруется, сортируется и пагинируется
**на сервере**, не на клиенте. Клиент отображает то что прислал бэк.

**Исключение:** статические списки (список факультетов, ролей, типов
консультаций) — отдаются целиком и могут фильтроваться на клиенте,
если их меньше 50 элементов.

---

### Единый формат запроса

```
GET /api/<resource>?page=1&size=20&search=...&<filters>
```

**Стандартные параметры:**

| Параметр | Тип | Описание | Дефолт |
|----------|-----|----------|--------|
| `page`   | int | Номер страницы, начиная с 1 | 1 |
| `size`   | int | Количество элементов на странице (макс. 100) | 20 |
| `search` | str | Подстрока для поиска (обычно по имени/email) | — |
| `sort`   | str | Поле сортировки (например, `created_at`) | зависит от ресурса |
| `order`  | str | `asc` или `desc` | `desc` |

---

### Единый формат ответа

```json
{
  "items": [...],
  "total": 142,
  "page": 1,
  "size": 20
}
```

---

### Hook contract для серверных списков

```js
const {
  items,           // массив текущей страницы (от бэка, без .filter)
  loading,         // флаг загрузки
  error,           // объект ошибки или null
  total,           // общее число (для пагинатора)
  page, setPage,   // текущая страница и сеттер
  query, setQuery, // поисковая строка
  filters, setFilters, // объект доменных фильтров: { role, is_active, ... }
  refetch          // ручной перезапрос
} = useResource();
```

**Внутри hook:**
- При изменении `page`, `query`, `filters` — делается новый запрос к API
- На `setQuery` навешен debounce 300ms
- При смене `query` или `filters` — `page` сбрасывается на 1
- Hook **не делает** локальной фильтрации над `items`

---

### Что запрещено

| Запрет | Почему |
|--------|--------|
| `items.filter(...)` в компонентах | Фильтрация — задача бэка |
| Загрузка списка одним запросом без `size` | Не масштабируется |
| Импорт из `data/` в новых hooks | См. раздел 6 |
| Хранить весь список в state и фильтровать его | То же самое |
| Свой формат пагинации в каждом эндпоинте | Усложняет фронт |

---

### Где это применяется

Все списки длиннее 50 элементов в управленческих разделах и личных кабинетах:
- Список юзеров (админ)
- Список записей на консультации (супервизор, психолог)
- Список результатов тестов (супервизор, связанный психолог)
- Журналы аудита (админ)
- Список своих записей (студент) — да, тоже через пагинацию, на случай 
  если у студента 50+ записей за годы учёбы

**Не применяется** к:
- Профилю (один объект, не список)
- Текущему юзеру `/api/users/me`
- Спискам в формах (выпадашки факультетов, ролей)

## 7. Component Layering

| Level | Location | Knows domain? | Has fetch? | Example |
|---|---|---|---|---|
| Shell | `app/` | No | No | `App.jsx`, `router.jsx` |
| Page | `pages/` | No | No | `MaterialsPage`, `EngagementsPage` |
| Feature | `features/<domain>/` | Yes | Via hooks | `AuthModal`, `AssignModal` |
| Primitive | `components/` | No | No | `Modal`, `Icon`, `CabinetLayout` |

**Правило:** если компонент вызывает `useAuth()`, делает API call или знает о доменной модели → он в `features/`, не в `components/`.

**CabinetLayout** — исключение: это primitive layout-компонент, который принимает всю конфигурацию через props (`navSections`, `crumbLabels`). Он не знает о конкретных ролях и маршрутах.

---

## 8. Open Issues

### 8.1 ~~useMaterials импортирует mock напрямую~~ — закрыто

`hooks/useMaterials.js` переведён на реальный API. `materials.api.js` реэкспортирует из `articles.api.js`.

**Осталось ограничение:** сортировка материалов в публичном UI всё ещё клиентская.

### 8.2 NewsListItem без CSS модуля

`features/news/components/NewsListItem.jsx` не имеет своего `.module.css`. Стили живут в `NewsSection.module.css`.

### 8.3 Дублирование в filter компонентах

`FiltersDropdown.jsx` и `FilterSheet.jsx` содержат одинаковые константы (`SORT_OPTIONS`) и SVG иконки.

### 8.4 LoginForm использует устаревший паттерн ошибок

`LoginForm.jsx` хранит ошибки полей как булевы значения. Это противоречит стандарту раздела 10 (единый `errors` со строками + `errors._form`).

### 8.5 Social login buttons — нефункциональные

`LoginForm` и `RegisterForm` рендерят кнопки Telegram / VK / Yandex без `onClick`. Dead UI.

### 8.6 Нет глобального ErrorBoundary

Любая render-ошибка крэшит всё приложение.

### 8.7 Кабинеты студента, психолога и супервизора — текущий статус

- `StudentHome` ещё остаётся частично витринным, но `/student/calendar`, `/student/chat`,
  `/student/group-sessions`, `/student/settings` уже подключены к real API.
- Кабинет психолога уже содержит студентов, карточку студента, чат, записи, календарь,
  групповые занятия и read-only расписание/разовые изменения.
- Кабинет супервизора уже содержит назначения, типы встреч, расписание, ручную запись
  registered/walk-in клиентов и групповые занятия.
- Оставшиеся заглушки/будущие разделы зависят от текущей навигации и должны проверяться по коду.

~~`ConsultantDashboard.jsx` и `DashboardLayout.jsx`~~ — удалены как мёртвый код.

### 8.8 `useAdminTags` не имеет `filters` в hook-контракте

`useAdminTags` возвращает контракт без `filters` и `setFilters` — намеренное отступление (теги фильтруются только по имени).

### 8.9 Кабинет студента использует собственный layout, не CabinetLayout

`StudentLayout.jsx` и `ClientDashboard.jsx` образуют собственную структуру, отличную от psychologist/supervisor. При будущем рефакторинге — рассмотреть унификацию.

---

## 9. Recommendations

### 9.1 Вынести SORT_OPTIONS и иконки из filter компонентов

Создать `pages/materials/components/_filterConstants.js`.

### 9.2 Co-locate NewsListItem styles

Создать `features/news/components/NewsListItem.module.css`.

### 9.3 Добавить ErrorBoundary

```jsx
// src/app/ErrorBoundary.jsx
class ErrorBoundary extends React.Component { ... }
```

### 9.4 Wire или удалить social login

Реализовать OAuth для Telegram/VK/Yandex, либо убрать кнопки.

### 9.5 Серверная сортировка материалов

Добавить серверные параметры `sort`/`order` в `GET /api/articles` и убрать клиентский `.reverse()`.

### 9.6 Lazy loading страниц

```jsx
const Home = lazy(() => import('../pages/home/Home'));
// + <Suspense fallback={<PageSkeleton />}>
```

### 9.7 ~~Список назначенных клиентов в кабинете психолога~~ — закрыто

Реализованы `/psychologist/students` и `/psychologist/students/:studentId`.

### 9.8 Отображение психолога у студента

Показать текущего назначенного психолога в `StudentHome` / `StudentSettings`.

---

## 10. Conventions

### Именование файлов

| Тип | Конвенция | Пример |
|---|---|---|
| React компонент | PascalCase | `AssignModal.jsx` |
| Hook | camelCase, префикс `use` | `useStudents.js` |
| API модуль | camelCase, суффикс `.api.js` | `supervisor.api.js` |
| CSS Module | camelCase, совпадает с компонентом | `AssignModal.module.css` |
| Mock данные | camelCase, суффикс `.mock.js` | `materials.mock.js` |
| Утилиты | camelCase | `utils.js` |

### Hook контракт

#### 1. Data-fetching (один объект или короткий список)

```js
return { data, loading, error, refetch }
// или
return { items, loading, error, refetch }
```

#### 2. Form

```js
return { values, errors, handleChange, handleSubmit }
```

#### 3. Server-side list (пагинация)

```js
return {
  items, loading, error, total,
  page, setPage,
  query, setQuery,
  filters, setFilters,
  refetch
}
```

#### 4. Infinite scroll (опционально)

```js
return { items, loading, error, hasMore, loadMore }
```

### CSS Modules

- Один `.module.css` на один компонент
- Классы в camelCase: `.cardTitle`, `.btnPrimary`
- Никаких глобальных селекторов внутри модуля

### Error handling в формах

```js
const [errors, setErrors] = useState({});
// { email: 'Некорректный формат', _form: 'Сервер недоступен' }
```

```jsx
{errors.email && <span className={styles.hint} role="alert">{errors.email}</span>}
{errors._form && <div className={styles.formError} role="alert">{errors._form}</div>}
```

### Порядок imports

```js
// 1. React + внешние
import { useState } from 'react';
import { Link } from 'react-router-dom';

// 2. Внутренние (features, components, api, hooks)
import { useStudents } from '../../features/supervisor/hooks/useStudents';
import Modal from '../../components/Modal/Modal';

// 3. Локальные (тот же или дочерний folder)
import styles from './EngagementsPage.module.css';
```

---

## 11. Dependencies

| Package | Version | Role |
|---|---|---|
| `react` | 19.2 | UI framework |
| `react-dom` | 19.2 | DOM renderer + `createPortal` |
| `react-router-dom` | 7.14.2 | Client-side routing |
| `react-scripts` | 5.0.1 | CRA build toolchain |
| `@tiptap/react` | 3.x | Rich-text editor (admin: articles, news) |
| `dompurify` | 3.x | HTML sanitization (ContentPreview) |
| `@testing-library/react` | 16.x | Component testing |

**Backend proxy:** `package.json` → `"proxy": "http://localhost:8000"`. Все `/api/*` запросы проксируются на FastAPI во время разработки.

# MindCare Web — Architecture Document

> Updated: 2026-05-02  
> Stack: React 19 · React Router 7 · CSS Modules · CRA (Create React App)  
> Purpose: University psychology center — public informational site with role-based dashboards and a full authentication flow.

---

## 1. Project Tree

```
mindcare_web/
├── package.json               proxy → http://localhost:8000
└── src/
    ├── index.js               DOM entry point
    ├── App.test.js
    ├── reportWebVitals.js
    ├── setupTests.js
    │
    ├── app/                   ← shell: providers + routing
    │   ├── App.jsx
    │   └── AppRoutes.jsx
    │
    ├── api/                   ← ALL HTTP calls live here
    │   ├── client.js          ← transport: token injection + 401 refresh
    │   ├── auth.api.js
    │   ├── news.api.js
    │   ├── materials.api.js
    │   └── appointments.api.js
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
    │   │   ├── authUtils.js
    │   │   ├── ui/
    │   │   │   ├── AuthModal.jsx
    │   │   │   ├── AuthModal.module.css
    │   │   │   ├── LoginForm.jsx
    │   │   │   └── RegisterForm.jsx
    │   │   └── forgot-password/
    │   │       ├── ForgotPasswordModal.jsx
    │   │       ├── ForgotPasswordStepper.jsx
    │   │       ├── hooks/
    │   │       │   └── useForgotPassword.js
    │   │       ├── components/
    │   │       │   ├── OTPInput.jsx
    │   │       │   └── PasswordStrength.jsx
    │   │       ├── steps/
    │   │       │   ├── StepEmail.jsx
    │   │       │   ├── StepOTP.jsx
    │   │       │   ├── StepNewPassword.jsx
    │   │       │   └── StepSuccess.jsx
    │   │       └── styles/
    │   │           └── forgot-password.module.css
    │   └── news/
    │       └── components/
    │           ├── NewsSection.jsx
    │           ├── NewsSection.module.css
    │           ├── FeaturedNews.jsx
    │           ├── NewsCardSmall.jsx
    │           └── NewsListItem.jsx
    │
    ├── components/            ← domain-agnostic UI primitives
    │   ├── Modal/
    │   │   ├── Modal.jsx
    │   │   └── Modal.module.css
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
    │   ├── layouts/
    │   │   ├── DashboardLayout.jsx
    │   │   └── DashboardLayout.module.css
    │   ├── UI/
    │   │   └── MultiSelect/
    │   │       ├── MultiSelect.jsx
    │   │       └── multiSelect.module.css
    │   └── icons/
    │       └── index.jsx
    │
    ├── pages/                 ← composition only, no business logic
    │   ├── home/
    │   │   ├── Home.jsx
    │   │   └── components/
    │   │       ├── Hero.jsx
    │   │       ├── Hero.module.css
    │   │       ├── QuickActions.jsx
    │   │       └── QuickActions.module.css
    │   ├── about/
    │   │   ├── About.jsx
    │   │   └── components/
    │   │       ├── AboutIntro.jsx + .module.css
    │   │       ├── AboutMission.jsx + .module.css
    │   │       ├── AboutApproach.jsx + .module.css
    │   │       ├── AboutServicesPreview.jsx + .module.css
    │   │       ├── AboutTrust.jsx + .module.css
    │   │       └── AboutMedia.jsx + .module.css
    │   ├── services/
    │   │   ├── Services.jsx
    │   │   ├── Services.module.css
    │   │   └── components/
    │   │       ├── ServicesSlider.jsx + .module.css
    │   │       ├── ServiceCard.jsx + .module.css
    │   │       ├── ProcessBlock.jsx + .module.css
    │   │       └── PrinciplesBlock.jsx + .module.css
    │   ├── news/
    │   │   ├── NewsPage.jsx
    │   │   ├── NewsItemPage.jsx
    │   │   ├── NewsItemPage.module.css
    │   │   └── components/
    │   │       ├── NewsGrid.jsx
    │   │       ├── NewsPage.module.css
    │   │       └── Pagination.jsx
    │   ├── materials/
    │   │   ├── MaterialsPage.jsx
    │   │   ├── MaterialsPage.module.css
    │   │   ├── MaterialsItemPage.jsx
    │   │   ├── MaterialsItemPage.module.css
    │   │   └── components/
    │   │       ├── SearchBar.jsx + .module.css
    │   │       ├── FiltersDropdown.jsx + .module.css
    │   │       ├── FilterSheet.jsx + .module.css
    │   │       ├── MaterialsGrid.jsx + .module.css
    │   │       └── MaterialCard.jsx + .module.css
    │   ├── client/
    │   │   └── ClientDashboard.jsx
    │   ├── consultant/
    │   │   └── ConsultantDashboard.jsx
    │   ├── admin/
    │   │   └── AdminDashboard.jsx
    │   └── not-found/
    │       ├── NotFound.jsx
    │       └── NotFound.module.css
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
✅ открывают модальные окна (isAuthOpen)
❌ не делают fetch напрямую
❌ не содержат фильтрацию/сортировку
❌ не импортируют из data/ напрямую
```

### Features — бизнес-логика

Каждый домен (`auth`, `news`, `materials`) содержит компоненты, которые:
- знают о доменных концепциях (user, news article, material)
- могут вызывать hooks и Context
- не переиспользуются за пределами своего feature

### API слой — единственная точка HTTP

```
src/api/
  client.js          ← transport
  auth.api.js        ← forgotPassword, resetPassword
  news.api.js        ← getNews, getNewsById
  materials.api.js   ← getMaterials, getMaterialById
  appointments.api.js
```

До реализации соответствующего бэкенд-эндпоинта *.api.js может импортировать mock из data/. После подключения к API импорт удаляется. См. раздел 6 для полных правил работы с моками.
**Запрещено:** API в `services/`, API внутри `pages/`, API внутри `components/`

### Components — domain-agnostic примитивы

```
✅ принимают всё через props
✅ без fetch, без Context (кроме AuthContext в Navbar)
✅ переиспользуются в любом feature или page
❌ без доменных концепций ("user", "news")
```

### Hooks — переиспользуемая логика

```
src/hooks/
  useDebounce.js     ← generic utility
  useNews.js         ← data fetching + pagination state
  useMaterials.js    ← filter/sort/pagination state
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

**Файл:** `src/app/AppRoutes.jsx`

| Route | Component | Guard |
|---|---|---|
| `/` | `Home` | Public |
| `/about` | `About` | Public |
| `/services` | `Services` | Public |
| `/news` | `NewsPage` | Public |
| `/news/:id` | `NewsItemPage` | Public |
| `/materials` | `MaterialsPage` | Public |
| `/materials/:id` | `MaterialsItemPage` | Public |
| `/student` | `ClientDashboard` | Auth + role: student |
| `/psychologist` | `ConsultantDashboard` | Auth + role: psychologist |
| `/admin` | `AdminDashboard` | Auth + role: admin |
| `*` | `NotFound` | Public |

`ProtectedRoute` HOC: если нет `user` → `<Navigate to="/" />`. Если роль не совпадает → `<Navigate to="/" />`.

---

## 4. Authentication

### Token Lifecycle

```
LoginForm → POST /api/auth/login
               │
               ▼
         AuthContext.login(token, user)
               │
               ├─▶ localStorage: access_token, refresh_token
               └─▶ setState({ user }) → App re-renders
```

### 401 Refresh (api/client.js)

```
apiFetch() → 401
               │
               ▼
         POST /api/auth/refresh
               │
       ┌───────┴───────┐
      200              401/error
       │                 │
  retry request    logout() + redirect /
```

### Session Restore

```
AuthProvider mount → read localStorage
  → token present: GET /api/auth/me → setState
  → token absent: user = null
```

### ProtectedRoute

```jsx
if (!user) return <Navigate to="/" />;
if (roles && !roles.includes(user.role)) return <Navigate to="/" />;
```

---

## 5. Key Modules

### Modal System

```
Modal.jsx (primitive)
├── createPortal → document.body
├── Focus trap (Tab cycling)
├── Escape → onClose
├── Saves/restores focus
└── exposes focusFirst() via useImperativeHandle

AuthModal (zIndex=2000)  →  <Modal>  →  LoginForm / RegisterForm
ForgotPasswordModal (zIndex=2100)  →  <Modal>  →  ForgotPasswordStepper
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

### Materials Filter (SearchBar)

```
SearchBar
├── desktop: FiltersDropdown (absolute div, no portal)
└── mobile:  FilterSheet (createPortal bottom sheet)

Both share: tag multiselect + sort radio + clear
State lives in: useMaterials hook → MaterialsPage props → SearchBar
```

### Dashboard Layout

```
DashboardLayout (components/layouts/)
├── Navbar
├── <main>{children}</main>
└── Footer

Used by: ClientDashboard, ConsultantDashboard, AdminDashboard
```

---

## 6. Data Flow

```
User interaction
       ↓
Custom hook (useNews, useMaterials, useAdminUsers, ...)
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

Hook может временно импортировать из `data/` напрямую — но это всегда временное состояние, помеченное в Open Issues этого документа.

**Как только бэк-эндпоинт готов:**

- Hook переводится на `api/<domain>.api.js`
- Прямой импорт из `data/` удаляется из hook
- Соответствующий пункт в Open Issues закрывается

**Запрещено:** оставлять `try API → catch fallback to mock` как постоянный паттерн в production-коде. Это маскирует проблемы интеграции и не даёт увидеть реальные ошибки API.

**Все новые модули после `2026-05-20`** (дата принятия этого правила) реализуются сразу через API — без промежуточного этапа с моками.

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

**Доменные фильтры** добавляются по необходимости конкретного эндпоинта:
- Юзеры: `role`, `is_active`
- Записи: `status`, `psychologist_id`, `date_from`, `date_to`
- Тесты: `is_active`, `category_id`

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

`total` — общее число элементов с учётом фильтров, не общее число 
в БД. Нужно для отображения «Стр. 1 из 8» и пагинатора.

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
- На `setQuery` навешен debounce 300ms (чтобы не дёргать API на каждой 
  клавише)
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

Все списки длиннее 50 элементов в админке и личных кабинетах:
- Список юзеров (админ)
- Список записей на консультации (админ, психолог)
- Список результатов тестов (админ, психолог)
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
| Shell | `app/` | No | No | `App.jsx`, `AppRoutes.jsx` |
| Page | `pages/` | No | No | `MaterialsPage`, `NewsPage` |
| Feature | `features/<domain>/` | Yes | Via hooks | `AuthModal`, `NewsSection` |
| Primitive | `components/` | No | No | `Modal`, `Navbar`, `PageHero` |

**Правило:** если компонент вызывает `useAuth()`, делает API call или знает о доменной модели → он в `features/`, не в `components/`.

---

## 8. Open Issues

### 8.1 useMaterials импортирует mock напрямую

`hooks/useMaterials.js` импортирует `MOCK_MATERIALS` из `data/` напрямую и 
выполняет фильтрацию/сортировку/пагинацию локально на клиенте.

**Статус:** временное решение, унаследованное из ранней разработки UI.

**Что нарушается:** правило из раздела 6 (data flow всегда через API) и 
правило из раздела 6.1 (фильтрация списков длиннее 50 элементов на сервере).

**План перехода:**
1. Реализовать на бэке `GET /api/materials` с параметрами `page`, `size`, 
   `search`, фильтрами по категориям и сортировкой. Ответ в формате 
   `{ items, total, page, size }`.
2. Обновить `useMaterials`: убрать импорт из `data/`, использовать 
   `getMaterials` из `api/materials.api.js`.
3. Удалить локальную фильтрацию из hook — всё делает бэк.
4. Закрыть этот пункт в Open Issues.

**Дедлайн:** до конца MVP (этап 1).


### 8.2 NewsListItem без CSS модуля

`features/news/components/NewsListItem.jsx` не имеет своего `.module.css`. Стили живут в `NewsSection.module.css`, создавая скрытую связь. Если компонент когда-либо переедет — стили потеряются.

### 8.3 Дублирование в filter компонентах

`FiltersDropdown.jsx` и `FilterSheet.jsx` содержат одинаковые константы (`SORT_OPTIONS`) и SVG иконки (`XIcon`, `CheckIcon`). Если фильтр опций изменится — нужно обновить два файла.

### 8.4 Social login buttons — нефункциональные

`LoginForm` и `RegisterForm` рендерят кнопки Telegram / VK / Yandex без `onClick`. Это dead UI, вводящий пользователей в заблуждение.

### 8.5 Нет глобального ErrorBoundary

Любая render-ошибка в `AppRoutes` крэшит всё приложение. `App.jsx` не оборачивает дерево в `ErrorBoundary`.

### 8.6 Dashboard pages — stubs

`ClientDashboard`, `ConsultantDashboard`, `AdminDashboard` отображают только приветствие. Реальный UI не реализован.

---

## 9. Recommendations

### 9.1 Вынести SORT_OPTIONS и иконки из filter компонентов

Создать `pages/materials/components/_filterConstants.js` с `SORT_OPTIONS`, `XIcon`, `CheckIcon`. Импортировать в `FiltersDropdown` и `FilterSheet`. Устраняет дублирование без добавления нового слоя.

### 9.2 Co-locate NewsListItem styles

Создать `features/news/components/NewsListItem.module.css`. Перенести соответствующие правила из `NewsSection.module.css`.

### 9.3 Добавить ErrorBoundary

```jsx
// src/app/ErrorBoundary.jsx
class ErrorBoundary extends React.Component { ... }

// src/app/App.jsx
<ErrorBoundary>
  <AuthProvider>
    <AppRoutes />
  </AuthProvider>
</ErrorBoundary>
```

### 9.4 Wire или удалить social login

Реализовать OAuth для Telegram/VK/Yandex, либо убрать кнопки. Не оставлять нефункциональный UI.

### 9.5 Подключить useMaterials к API

Когда бэкенд поддержит фильтрацию:
```js
// hooks/useMaterials.js
import { getMaterials } from '../api/materials.api';
// убрать прямой импорт из data/
```

### 9.6 Lazy loading страниц

```jsx
// app/AppRoutes.jsx
const Home = lazy(() => import('../pages/home/Home'));
// + <Suspense fallback={<PageSkeleton />}>
```

---

## 10. Conventions

### Именование файлов

| Тип | Конвенция | Пример |
|---|---|---|
| React компонент | PascalCase | `MaterialCard.jsx` |
| Hook | camelCase, префикс `use` | `useMaterials.js` |
| API модуль | camelCase, суффикс `.api.js` | `news.api.js` |
| CSS Module | camelCase, совпадает с компонентом | `MaterialCard.module.css` |
| Mock данные | camelCase, суффикс `.mock.js` | `materials.mock.js` |

### Hook контракт

В проекте используются три-четыре стандартных контракта для hooks. 
Каждый новый hook должен соответствовать одному из них.

#### 1. Data-fetching (один объект или короткий список)

Для запроса данных без пагинации — например, профиль юзера, текущий 
набор настроек, статичный справочник.

```js
return { items, loading, error, refetch }
```

или для одного объекта:

```js
return { data, loading, error, refetch }
```

---

#### 2. Form

Для управления состоянием формы.

```js
return { values, errors, handleChange, handleSubmit }
```

---

#### 3. Server-side list (пагинация админки и личных кабинетов)

Для списков с серверной фильтрацией и пагинацией. См. раздел 6.1.

```js
return { 
  items, loading, error, total,
  page, setPage,
  query, setQuery,
  filters, setFilters,
  refetch 
}
```

**Используется для:** списка юзеров в админке, списка записей на 
консультации, журнала аудита и т.д.

---

#### 4. Infinite scroll (опционально, для длинных лент)

Для бесконечных лент в публичной части — например, лента новостей.

```js
return { items, loading, error, hasMore, loadMore }
```

**Используется для:** новостной ленты, ленты публичных вопросов в Q&A.

**НЕ используется для:** админских списков. У админа должен быть 
классический пагинатор с возможностью прыгнуть на нужную страницу.

---

**Если задача не подходит ни под один контракт** — обсуждай с командой 
до создания нового. Лучше расширить существующий контракт, чем плодить 
их.

### CSS Modules

- Один `.module.css` на один компонент — никогда не шарить стили между двумя компонентами
- Классы в camelCase: `.cardTitle`, `.btnPrimary`
- Никаких глобальных селекторов внутри модуля

### Порядок imports

```js
// 1. React + внешние
import { useState } from 'react';
import { Link } from 'react-router-dom';

// 2. Внутренние (features, components, api, hooks)
import { useNews } from '../../hooks/useNews';
import Modal from '../../components/Modal/Modal';

// 3. Локальные (тот же или дочерний folder)
import styles from './NewsPage.module.css';
```

---

## 11. Dependencies

| Package | Version | Role |
|---|---|---|
| `react` | 19.2 | UI framework |
| `react-dom` | 19.2 | DOM renderer + `createPortal` |
| `react-router-dom` | 7.14.2 | Client-side routing |
| `react-scripts` | 5.0.1 | CRA build toolchain |
| `@testing-library/react` | — | Component testing |

**Backend proxy:** `package.json` → `"proxy": "http://localhost:8000"`. Все `/api/*` запросы проксируются на FastAPI сервер (порт 8000) во время разработки.

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

Каждый `*.api.js` импортирует mock из `data/` как fallback — это единственное место, где разрешён прямой импорт mock данных.

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
      │
      ▼
Custom hook (useNews, useMaterials)
      │
      ▼
api/<domain>.api.js          [try real API]
      │                              │
      │                    [catch → fallback to data/*.mock.js]
      ▼
api/client.js (token injection + 401 retry)
      │
      ▼
FastAPI backend → MySQL
      │
      ▼
setState in hook → Page re-renders
```

---

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

`hooks/useMaterials.js` импортирует `MOCK_MATERIALS` из `data/` напрямую и фильтрует локально. Это временное решение до появления реального бэкенд-эндпоинта для фильтрации. Когда бэкенд будет готов — hook должен делегировать фильтрацию в `api/materials.api.js`.

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

```js
// Data-fetching hook
return { items, loading, error, refetch }

// Form hook
return { values, errors, handleChange, handleSubmit }

// Filter/state hook
return { query, setQuery, visible, hasMore, loadMore }
```

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

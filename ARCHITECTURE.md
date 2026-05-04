# Frontend Architecture

## Структура `src/`

```
src/
├── api/
│   └── api.js              # Низкоуровневый fetch-клиент
├── services/
│   └── api.js              # Публичный API-слой (getNewsById и т.д.)
├── components/             # Только по-настоящему шаренные компоненты
│   ├── AuthModal/          # Модальное окно авторизации (LoginForm, RegisterForm)
│   ├── CookieBanner/
│   ├── Footer/
│   ├── Hero/               # PageHero.jsx — shared hero для всех подстраниц
│   ├── Navbar/
│   ├── News/               # NewsSection + FeaturedNews, NewsCardSmall, NewsListItem
│   └── icons/              # Shared SVG-иконки
├── features/
│   └── auth/               # Login + ForgotPassword (multi-step: email→OTP→password→success)
├── pages/                  # Page-module архитектура: каждый домен самодостаточен
│   ├── home/
│   │   ├── Home.jsx
│   │   └── components/     # Hero.jsx, QuickActions.jsx
│   ├── about/
│   │   ├── About.jsx
│   │   └── components/     # AboutIntro, AboutMission, AboutApproach,
│   │                       # AboutTrust, AboutMedia, AboutServicesPreview, AboutHero
│   ├── services/
│   │   ├── Services.jsx + Services.module.css
│   │   └── components/     # ServicesSlider, ServiceCard, ProcessBlock,
│   │                       # PrinciplesBlock, ServicesHero
│   ├── news/
│   │   ├── NewsPage.jsx
│   │   ├── NewsItemPage.jsx + NewsItemPage.module.css
│   │   └── components/     # NewsGrid, Pagination, NewsPage.module.css, mockNews.js
│   ├── materials/
│   │   ├── MaterialsPage.jsx + MaterialsPage.module.css
│   │   ├── MaterialsItemPage.jsx + MaterialsItemPage.module.css
│   │   └── components/     # MaterialsToolbar, FilterDropdown, MaterialsGrid,
│   │                       # MaterialCard, MaterialsHero, mockMaterials.js
│   └── not-found/
│       └── NotFound.jsx + NotFound.module.css
├── routes/
│   └── AppRoutes.jsx       # Единая точка маршрутизации
├── store/
│   └── store.js            # Заглушка глобального состояния
└── styles/
    ├── global.css          # Reset + базовые стили
    ├── variables.css       # CSS Custom Properties (токены)
    └── theme.js            # JS-экспорт токенов (при необходимости)
```

---

## Page-module архитектура

Каждый домен в `pages/` — самодостаточный модуль. Структура домена:

```
pages/<domain>/
  <Page>.jsx              # entry point, маршрутизируется из AppRoutes.jsx
  <Page>.module.css       # стили страницы (если есть)
  components/             # page-specific компоненты (только для этого домена)
    <Component>.jsx
    <Component>.module.css
    mock<Data>.js         # mock-данные домена (временно, до подключения API)
```

Один домен можно удалить или добавить, не затрагивая остальные части `src/`.

---

## Правило разделения компонентов

| Уровень | Путь | Когда использовать |
|---|---|---|
| **Shared** | `src/components/` | Компонент используется в **2+ доменах** |
| **Page-local** | `pages/<domain>/components/` | Компонент используется **только** в одном домене |

**Запрещено:**
- класть page-specific компонент в `src/components/`
- дублировать shared компонент внутри `pages/`

Текущие shared компоненты: `Navbar`, `Footer`, `PageHero`, `AuthModal`, `CookieBanner`, `NewsSection`, `FeaturedNews`, `NewsCardSmall`, `NewsListItem`, `icons/`.

---

## Принципы организации

**Co-location CSS.** Каждый компонент хранит стили рядом (`.module.css`). Глобальные стили — только в `styles/`.

**Feature slices.** Сложная бизнес-логика (ForgotPassword) живёт в `features/auth/` — не в `components/` и не в `pages/`.

**Mock → API.** Mock-данные (`mockMaterials.js`, `mockNews.js`) лежат в `components/` своего домена. Переход на реальный API — замена одного вызова в `services/api.js` без изменения компонентов.

---

## Поток данных

```
AppRoutes.jsx
    │
    ▼
Page (e.g. MaterialsPage)
    │  useState (search, category, sort, visibleCount)
    │  useMemo  (filtered items)
    ▼
Section/Grid (e.g. MaterialsGrid)
    │  props: items[]
    ▼
Card (e.g. MaterialCard)
    │  props: item
    │  <Link to="/materials/:id">
    ▼
MaterialsItemPage
    │  useParams → id
    │  MOCK_MATERIALS.find(id)   ← заменить на services/api.js
    ▼
Render article
```

---

## Design System

Токены определены в `styles/variables.css` как CSS Custom Properties:

| Категория | Переменные |
|---|---|
| Цвета | `--espresso`, `--coffee`, `--mocha`, `--sand`, `--cream`, `--text-main`, `--text-light` |
| Типографика | `--fs-h1`, `--fs-body`, `--fs-ui`, `--fs-sub`, `--fs-tag`, `--lh-h1`, `--lh-body` |
| Сетка | `--section-py`, `--container-px`, `--nav-border` |

Шрифты: **Nunito** (UI, body) + **Cormorant Garamond** (заголовки H1/H2).

---

## Routing

Все маршруты в одном файле `routes/AppRoutes.jsx` (React Router v7):

```
/                  → Home
/about             → About
/services          → Services
/news              → NewsPage
/news/:id          → NewsItemPage
/materials         → MaterialsPage
/materials/:id     → MaterialsItemPage
```

Динамические страницы (`/news/:id`, `/materials/:id`) — единый шаблон, данные подгружаются по `id`.

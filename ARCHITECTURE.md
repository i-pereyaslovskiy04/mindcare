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

## Принципы организации

**Domain grouping в pages/.** Страницы сгруппированы по доменам (`home/`, `news/`, `materials/` и т.д.). Каждый домен — папка с `.jsx` и `.module.css` рядом. Плоская структура не масштабируется при росте числа маршрутов.

**Co-location CSS.** Каждый компонент и страница хранит стили рядом (`.module.css`). Глобальные стили только в `styles/`.

**Feature slices.** Сложная бизнес-фича (ForgotPassword) живёт в `features/auth/` со своими хуками, шагами и стилями — не в `components/`.

**Mock → API.** Данные сейчас в `mockMaterials.js` / `mockNews.js`. Переход на API — замена одного вызова в `services/api.js` без изменения компонентов.

**Page-module.** Каждая страница — самодостаточный модуль: `pages/<domain>/Page.jsx` + `pages/<domain>/components/` для локальных секций. В `components/` остаётся только то, что используется в двух и более доменах.

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

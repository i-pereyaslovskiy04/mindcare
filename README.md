# MindCare

Психологический центр поддержки студентов. Монорепозиторий: React-frontend + FastAPI backend.

---

## Стек

| Слой | Технологии |
|---|---|
| Frontend | React 19, React Router v7, CSS Modules |
| Backend | Python 3, FastAPI |
| Стили | CSS Variables (design tokens), Nunito + Cormorant Garamond |
| Сборка | Create React App (react-scripts 5) |

---

## Структура репозитория

```
mindcare/
├── mindcare_api/          # FastAPI backend — порт 8000
│   └── app/
│       └── main.py        # Единственный файл приложения
├── mindcare_web/          # React frontend — порт 3000
│   └── src/
│       ├── api/           # Centralized fetch client
│       ├── components/    # Переиспользуемые UI-компоненты
│       ├── features/      # Feature slices (auth)
│       ├── pages/         # Страницы, сгруппированы по доменам (home/, about/, news/, …)
│       ├── routes/        # AppRoutes.jsx — React Router config
│       ├── store/         # Global state (заглушка)
│       └── styles/        # Design tokens, global.css
├── CLAUDE.md
└── README.md
```

---

## Запуск

### Backend

```bash
cd mindcare_api
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
# → http://localhost:8000
```

### Frontend

```bash
cd mindcare_web
npm install
npm start
# → http://localhost:3000
```

> Proxy в `mindcare_web/package.json` перенаправляет все `/api/...` запросы на `localhost:8000`.  
> Для полноценной разработки нужны оба сервера.

---

## Маршруты

| URL | Компонент |
|---|---|
| `/` | Home |
| `/about` | About |
| `/services` | Services |
| `/news` | NewsPage |
| `/news/:id` | NewsItemPage |
| `/materials` | MaterialsPage |
| `/materials/:id` | MaterialsItemPage |

---

## Компоненты (основные группы)

| Группа | Компоненты |
|---|---|
| **Layout** | Navbar, Footer |
| **Hero** | Hero (главная), PageHero (внутренние страницы) |
| **Materials** | MaterialsToolbar, FilterDropdown, MaterialsGrid, MaterialCard |
| **News** | NewsSection, FeaturedNews, NewsGrid, NewsCardSmall, NewsListItem, Pagination |
| **Services** | ServicesSlider, ServiceCard, PrinciplesBlock, ProcessBlock |
| **About** | AboutHero, AboutIntro, AboutMission, AboutApproach, AboutTrust, AboutMedia |
| **Auth** | AuthModal, LoginForm, RegisterForm |
| **Features/Auth** | ForgotPassword (4-step flow: email → OTP → password → success) |
| **Shared** | QuickActions, CookieBanner |

---

## Данные

На данный момент используются mock-данные в компонентах:

- `src/components/Materials/mockMaterials.js` — материалы
- `src/components/News/NewsPage/mockNews.js` — новости
- `src/services/api.js` — точка входа для будущих API-вызовов

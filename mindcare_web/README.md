# MindCare Web

React-приложение для MindCare. Структура организована для удобной разработки, масштабирования и поддержки SPA (Single Page Application).

---

## 📁 Структура проекта

mindcare_web/
├── public/
│   └── index.html
├── src/
│   ├── api/                     ← функции для работы с бэком
│   │   └── api.js               ← пример fetch-запроса
│   │
│   ├── assets/                  ← ресурсы
│   │   ├── fonts/
│   │   ├── images/
│   │   └── icons/
│   │
│   ├── components/              ← переиспользуемые UI-компоненты
│   │   └── UserCard/
│   │       ├── UserCard.jsx
│   │       └── UserCard.module.css
│   │
│   ├── features/                ← фичи приложения с локальной логикой
│   │   └── auth/
│   │       ├── Login.jsx
│   │       └── authSlice.js
│   │
│   ├── hooks/                   ← кастомные React-хуки
│   │   └── useAuth.js
│   │
│   ├── layouts/                 ← шаблоны страниц (Header, Sidebar)
│   │   └── MainLayout.jsx
│   │
│   ├── pages/                   ← страницы приложения
│   │   ├── Home/
│   │   │   ├── Home.jsx
│   │   │   └── Home.module.css
│   │   ├── UsersList/
│   │   │   ├── UsersList.jsx
│   │   │   └── UsersList.module.css
│   │   ├── UserDetails/
│   │   │   ├── UserDetails.jsx
│   │   │   └── UserDetails.module.css
│   │   └── NotFound/
│   │       ├── NotFound.jsx
│   │       └── NotFound.module.css
│   │
│   ├── routes/                  ← маршруты приложения
│   │   └── AppRoutes.jsx
│   │
│   ├── store/                   ← глобальное состояние (Redux, Zustand)
│   │   └── store.js
│   │
│   ├── styles/                  ← глобальные стили и темы
│   │   ├── global.css
│   │   └── theme.js
│   │
│   ├── utils/                   ← утилиты, хелперы
│   │   └── formatDate.js
│   │
│   ├── App.jsx                  ← главный компонент приложения
│   └── main.jsx                 ← точка входа React
│
├── .env                         ← переменные окружения (например REACT_APP_API_URL)
├── package.json
├── package-lock.json
└── README.md



---

## 🔹 Краткое описание папок

- **public/** — статические файлы, включая `index.html`  
- **src/api/** — функции для работы с бэкендом  
- **src/assets/** — шрифты, картинки, иконки  
- **src/components/** — переиспользуемые UI-компоненты  
- **src/features/** — бизнес-логика и состояние отдельных фич  
- **src/hooks/** — кастомные React-хуки  
- **src/layouts/** — шаблоны страниц (например MainLayout с Header/Sidebar)  
- **src/pages/** — отдельные страницы приложения  
- **src/routes/** — маршрутизация приложения  
- **src/store/** — глобальное состояние (Redux, Zustand и т.д.)  
- **src/styles/** — глобальные стили и темы  
- **src/utils/** — вспомогательные функции  

---

## 🚀 Быстрый старт (Windows)

### Backend (FastAPI)
```powershell
cd mindcare\mindcare_api
venv\Scripts\activate
uvicorn app.main:app --reload

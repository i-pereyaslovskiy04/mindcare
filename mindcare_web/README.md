# MindCare Project

React + FastAPI проект. Структура организована для удобной разработки и масштабирования.

---

## 📁 Структура проекта

```plaintext
mindcare/
├── mindcare_api/              # FastAPI backend
│   ├── app/
│   │   ├── main.py
│   │   └── ...                # остальные модули backend
│   ├── venv/                  # виртуальное окружение (игнорируется Git)
│   └── requirements.txt
├── mindcare_web/              # React frontend
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── api/
│   │   │   └── api.js
│   │   ├── assets/
│   │   │   ├── fonts/
│   │   │   ├── images/
│   │   │   └── icons/
│   │   ├── components/
│   │   │   └── UserCard/
│   │   │       ├── UserCard.jsx
│   │   │       └── UserCard.module.css
│   │   ├── features/
│   │   │   └── auth/
│   │   │       ├── Login.jsx
│   │   │       └── authSlice.js
│   │   ├── hooks/
│   │   │   └── useAuth.js
│   │   ├── layouts/
│   │   │   └── MainLayout.jsx
│   │   ├── pages/
│   │   │   ├── Home/
│   │   │   │   ├── Home.jsx
│   │   │   │   └── Home.module.css
│   │   │   ├── UsersList/
│   │   │   │   ├── UsersList.jsx
│   │   │   │   └── UsersList.module.css
│   │   │   ├── UserDetails/
│   │   │   │   ├── UserDetails.jsx
│   │   │   │   └── UserDetails.module.css
│   │   │   └── NotFound/
│   │   │       ├── NotFound.jsx
│   │   │       └── NotFound.module.css
│   │   ├── routes/
│   │   │   └── AppRoutes.jsx
│   │   ├── store/
│   │   │   └── store.js
│   │   ├── styles/
│   │   │   ├── global.css
│   │   │   └── theme.js
│   │   ├── utils/
│   │   │   └── formatDate.js
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── .env
│   ├── package.json
│   └── package-lock.json
├── .gitignore
└── start-all.bat

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

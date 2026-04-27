# MindCare — Project Summary

## Цель

Веб-платформа психологической поддержки студентов ДонГУ. Предоставляет доступ к материалам, новостям и сервисам центра, а также форму авторизации и запись на консультацию.

---

## Архитектура

```
React SPA  ──proxy──►  FastAPI
(port 3000)            (port 8000)
```

Monorepo: `mindcare_web/` (React 19 + CSS Modules) + `mindcare_api/` (Python FastAPI).  
Frontend использует mock-данные, готовые к подключению реального API.

---

## Ключевые модули

| Модуль | Назначение |
|---|---|
| **Pages** | 7 страниц: Home, About, Services, News, NewsItem, Materials, MaterialsItem |
| **Materials** | Фильтруемый каталог психологических материалов (статьи, гиды, вебинары, упражнения) |
| **News** | Лента новостей с пагинацией и страницей материала |
| **Auth** | Авторизация + 4-шаговый ForgotPassword flow (email → OTP → пароль → успех) |
| **Design System** | CSS Variables, шрифты Nunito + Cormorant Garamond, sand/espresso палитра |

---

## Статус

| Область | Состояние |
|---|---|
| UI / верстка | Активная разработка |
| Routing | Готов |
| Mock-данные | Готовы |
| API интеграция | Заглушка (`services/api.js`) |
| Global state | Заглушка (`store/store.js`) |
| Backend | Базовый FastAPI, без бизнес-логики |

# MindCare Web

Frontend-часть платформы психологической службы Донецкого государственного университета.

**Стек:** React 19 · React Router 7 · CSS Modules · CRA (Create React App)
**Порт:** 3000 (в dev режиме проксирует `/api/*` на backend порт 8000)

---

## Роли и кабинеты

| Роль | Маршрут | Статус |
|------|---------|--------|
| `student` | `/student/*` | Реализован (частично stub) |
| `psychologist` | `/psychologist/*` | Реализован (частично stub) |
| `supervisor` | `/supervisor/*` | Реализован |
| `admin` | `/admin/*` | Реализован |

После входа `/dashboard` автоматически перенаправляет пользователя в его кабинет по роли.

---

## Быстрый старт

```bash
# Установить зависимости
npm install

# Запустить dev-сервер (порт 3000)
npm start

# Продакшен-сборка
npm run build

# Запустить тесты
npm test
```

> Для работы с API нужен запущенный backend (`mindcare_api/`).
> Dev-сервер автоматически проксирует `/api/*` на `http://localhost:8000`.

---

## Структура проекта

```
src/
├── app/            — shell (App.jsx, router.jsx, providers.jsx)
├── api/            — ВСЕ HTTP-вызовы только здесь
├── shared/lib/     — общие утилиты (getInitials и т.д.)
├── hooks/          — переиспользуемые hooks
├── features/       — функциональные модули по доменам
│   ├── auth/       — авторизация, формы входа/регистрации
│   ├── supervisor/ — назначение психологов студентам
│   ├── admin/      — административная панель
│   ├── news/       — компоненты новостей
│   └── profile/    — страница профиля
├── components/     — domain-agnostic UI-примитивы
│   ├── Icon/       — общий SVG Icon-компонент
│   ├── CabinetLayout/ — общий layout для psychologist и supervisor кабинетов
│   ├── Modal/
│   └── UI/         — Button, ButtonLink, Checkbox, Toggle, FilterChip, Badge, Tag,
│                     Select, MultiSelect, DateInput, TiptapEditor, ImageUpload, ContentPreview
├── pages/          — только композиция страниц, никакого fetch
│   ├── home / about / services / news / materials
│   ├── student/    — кабинет студента (собственный layout)
│   ├── psychologist/ — кабинет психолога
│   └── supervisor/ — кабинет супервизора
└── styles/         — variables.css, global.css
```

Полная структура с описанием — [ARCHITECTURE.md](ARCHITECTURE.md).
Диаграммы — [DIAGRAM.md](DIAGRAM.md).

> **Shared UI:** перед созданием локального контрола свериться с `src/components/UI/`
> (правила — [../docs/UI_COMPONENTS_GUIDE.md](../docs/UI_COMPONENTS_GUIDE.md)).
> `DateInput` — общий компонент выбора **только даты** (value `YYYY-MM-DD`, кастомный
> popover, без нативного `datetime-local`/`date`); используется в admin news/articles.
> Для записи на приём нужен будущий `SlotPicker` (выбор слота времени), а не `DateInput`.

---

## Реализовано

**Публичная часть:**
- Главная страница, раздел «О нас», «Услуги»
- Лента новостей с пагинацией и страницами новостей
- Каталог материалов с фильтрацией, поиском и страницами материалов

**Авторизация:**
- Регистрация с OTP-подтверждением по email
- Вход / выход
- Восстановление пароля (OTP + новый пароль)
- Role-based routing (PrivateRoute / RoleRoute)

**Кабинет студента** (`/student/*`):
- Sidebar-навигация
- Главная, дневник настроения, тесты, материалы, задачи, чат, календарь, настройки
- Основные страницы в stub-состоянии (приветствие, mock-данные)

**Кабинет психолога** (`/psychologist/*`):
- Shared CabinetLayout с навигацией
- Главная и настройки
- Клиенты, сессии, чат — отключены (в планах)

**Кабинет супервизора** (`/supervisor/*`):
- Shared CabinetLayout с навигацией
- Главная, настройки
- Страница назначения психологов (`/supervisor/engagements`):
  - Список студентов с серверным поиском и пагинацией
  - Текущий психолог и статус связи
  - Назначить / переназначить / закрыть связь через AssignModal

**Административная панель** (`/admin/*`):
- Управление пользователями (CRUD, фильтры по роли/статусу)
- Управление типами материалов (categories)
- Управление темами (tags)
- Управление новостями (rich-text, обложка)
- Управление материалами/статьями (rich-text, категории, теги, обложка)

**Общие компоненты:**
- `components/Icon/Icon.jsx` — единый SVG Icon для всех кабинетов
- `shared/lib/utils.js` — getInitials и другие утилиты
- `components/CabinetLayout/` — shared layout для psychologist и supervisor

---

## В планах

- Список назначенных клиентов в кабинете психолога (`/psychologist/clients`)
- Отображение текущего психолога в кабинете студента
- Чат student ↔ psychologist
- Страницы сессий и отчётов в кабинете супервизора
- Страницы для психолога: сессии, чат с клиентами, материалы
- Реальные тесты с автоподсчётом результатов (вместо stub)
- Серверная сортировка материалов (сейчас клиентская)
- ErrorBoundary на уровне приложения
- Lazy loading страниц (код-сплиттинг)

---

## Архитектурные правила

- Все HTTP-запросы — только через `api/*.api.js`, никогда `fetch()` напрямую в компонентах
- Pages — только композиция, никакого fetch, никакой логики
- Серверная фильтрация и пагинация для всех списков из БД
- Один CSS Module на компонент, классы в camelCase
- Роли проверяются и на бэкенде (через `require_role`), frontend guards — UX, не security

Подробнее — [ARCHITECTURE.md](ARCHITECTURE.md).

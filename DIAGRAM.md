# Project Diagrams

## 1. Monorepo Overview

```
mindcare/
├── mindcare_web/   React 19 + CSS Modules   → :3000
└── mindcare_api/   Python FastAPI            → :8000
         ▲
         └── proxy: /api/* forwarded from :3000
```

---

## 2. Page → Component Map

```mermaid
graph TD
  Router["AppRoutes.jsx"]

  Router --> Home
  Router --> About
  Router --> Services
  Router --> NewsPage
  Router --> NewsItem["NewsItemPage /news/:id"]
  Router --> MaterialsPage
  Router --> MaterialsItem["MaterialsItemPage /materials/:id"]

  Home --> Hero
  Home --> QuickActions
  Home --> NewsSection
  Home --> ServicesPreview["AboutServicesPreview"]

  About --> AboutHero
  About --> AboutIntro
  About --> AboutMission
  About --> AboutApproach
  About --> AboutTrust
  About --> AboutMedia

  Services --> ServicesSlider
  ServicesSlider --> ServiceCard
  Services --> PrinciplesBlock
  Services --> ProcessBlock

  NewsPage --> NewsGrid
  NewsGrid --> NewsCardSmall
  NewsGrid --> Pagination

  NewsItem --> FeaturedLayout["article layout"]

  MaterialsPage --> MaterialsToolbar
  MaterialsToolbar --> FilterDropdown
  MaterialsPage --> MaterialsGrid
  MaterialsGrid --> MaterialCard

  MaterialsItem --> ArticleLayout["article layout"]
```

---

## 3. Data Flow — Materials

```mermaid
sequenceDiagram
  participant User
  participant MaterialsPage
  participant Toolbar as MaterialsToolbar
  participant Grid as MaterialsGrid
  participant ItemPage as MaterialsItemPage
  participant Mock as mockMaterials.js

  User->>MaterialsPage: открывает /materials
  MaterialsPage->>Mock: импорт MOCK_MATERIALS
  MaterialsPage->>Toolbar: search, category, sort
  User->>Toolbar: вводит фильтр
  Toolbar->>MaterialsPage: onSearch / onCategory / onSort
  MaterialsPage->>Grid: items[] (отфильтровано + усечено)
  Grid->>User: карточки
  User->>ItemPage: клик → /materials/:id
  ItemPage->>Mock: find(id)
  ItemPage->>User: статья (title, body[], quote)
```

---

## 4. Auth Flow — ForgotPassword

```mermaid
stateDiagram-v2
  [*] --> StepEmail : открыть модальное окно
  StepEmail --> StepOTP : email отправлен
  StepOTP --> StepNewPassword : OTP подтверждён
  StepNewPassword --> StepSuccess : пароль сохранён
  StepSuccess --> [*] : закрыть

  StepEmail --> StepEmail : ошибка валидации
  StepOTP --> StepOTP : неверный код
```

---

## 5. Component Hierarchy (text)

```
Navbar
  └── AuthModal
        ├── LoginForm
        └── RegisterForm

Page (any)
  ├── Navbar
  ├── PageHero  ← title, eyebrow, subtitle
  ├── <content sections>
  └── Footer

MaterialsPage
  ├── PageHero
  ├── MaterialsToolbar
  │     ├── search input
  │     ├── FilterDropdown (Категория)
  │     └── FilterDropdown (Сортировка)
  ├── MaterialsGrid
  │     └── MaterialCard[]  →  Link /materials/:id
  └── "Загрузить ещё" button

NewsPage
  ├── PageHero
  ├── NewsGrid
  │     ├── NewsCardSmall[]  →  Link /news/:id
  │     └── Pagination
  └── Footer
```

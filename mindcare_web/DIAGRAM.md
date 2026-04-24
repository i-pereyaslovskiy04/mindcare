# 📊 Архитектурная схема MindCare Frontend

## 🎯 Иерархия компонентов

```
App.js (импортирует стили)
└─ Home.jsx (сборка страницы)
   ├─ Navbar
   │  └─ Кнопка onOpenAuth
   ├─ Hero
   ├─ QuickActions
   │  └─ Кнопка onOpenAuth
   ├─ NewsSection
   │  ├─ FeaturedNews
   │  ├─ NewsCardSmall (×2)
   │  ├─ NewsListItem (×3)
   │  └─ Pagination
   ├─ Footer
   ├─ AuthModal (управляется из Home)
   │  ├─ LoginForm
   │  └─ RegisterForm
   └─ CookieBanner
```

## 🔄 Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                        Home.jsx                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ State:                                                │  │
│  │ • isAuthModalOpen: boolean                           │  │
│  │                                                       │  │
│  │ Methods:                                              │  │
│  │ • handleOpenAuth()  → setIsAuthModalOpen(true)        │  │
│  │ • handleCloseAuth() → setIsAuthModalOpen(false)       │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
├───────────────────────────┼──────────────────────────────────┤
│                           │                                  │
│  Navbar                   │        AuthModal                 │
│  (onOpenAuth)─────────────┴────────(isOpen,onClose)         │
│                                      │                       │
│  QuickActions                    ├────┴────┐                 │
│  (onOpenAuth)────────┐           │         │                 │
│                      └───────────→ LoginForm RegisterForm   │
│                                      │         │             │
│  NewsSection                         │    Валидация        │
│  (static)                            │         │             │
│                                      └────┬────┘             │
│  Footer                                   ↓                  │
│  (static)                          API call (api.js)        │
│                                                               │
│  CookieBanner                      localStorage             │
│  (localStorage)                     (cookies choice)        │
└─────────────────────────────────────────────────────────────┘
```

## 🎨 Стили (CSS Flow)

```
index.js
   ↓
App.js (imports)
   ├─ styles/variables.css    (Design tokens)
   └─ styles/global.css       (Reset + utilities)
      ↓
   Компоненты используют:
   ├─ var(--color-*) из variables.css
   ├─ styles.className из Component.module.css
   └─ container класс из global.css
```

## 📋 State Management

```
Home.jsx
│
├─ isAuthModalOpen: boolean
│  │
│  ├─ true  → показать AuthModal
│  └─ false → скрыть AuthModal
│
├─ AuthModal
│  │
│  ├─ activeTab: 'login' | 'register'
│  │  ├─ 'login'    → LoginForm активна
│  │  └─ 'register' → RegisterForm активна
│  │
│  ├─ LoginForm
│  │  ├─ email: string
│  │  ├─ password: string
│  │  └─ errors: { email?, password? }
│  │
│  └─ RegisterForm
│     ├─ name: string
│     ├─ email: string
│     ├─ password: string
│     ├─ confirmPassword: string
│     ├─ consent: boolean
│     ├─ passwordStrength: 0-3
│     └─ errors: { name?, email?, password?, confirmPassword? }
│
└─ CookieBanner
   ├─ isVisible: boolean
   ├─ isHiding: boolean
   └─ localStorage['mindcare_cookie_choice']: 'accepted'|'declined'
```

## 🔌 API Integration Points

```
src/services/api.js
│
├─ login(email, password)
│  └─ LoginForm.jsx → onSubmit
│
├─ register(name, email, password)
│  └─ RegisterForm.jsx → onSubmit
│
├─ getProfile()
│  └─ (future) Navbar.jsx → useEffect
│
├─ logout()
│  └─ (future) Navbar.jsx → onClick
│
├─ getNews(page, limit)
│  └─ (future) NewsSection.jsx → useEffect
│
├─ getPsychologists()
│  └─ (future) QuickActions.jsx → onClick
│
└─ bookAppointment(data)
   └─ (future) Modal for booking
```

## 🎯 Component Props Flow

```
Home.jsx
  │
  ├─ Navbar
  │  └─ Props: { onOpenAuth: () => void }
  │
  ├─ QuickActions
  │  └─ Props: { onOpenAuth: () => void }
  │
  ├─ NewsSection
  │  └─ Props: none (static)
  │     ├─ FeaturedNews: { news, className, style }
  │     ├─ NewsCardSmall: { news, className, style }
  │     └─ NewsListItem: { news, className, style }
  │
  ├─ Footer
  │  └─ Props: none (static)
  │
  ├─ AuthModal
  │  └─ Props: { isOpen: boolean, onClose: () => void }
  │     ├─ LoginForm: { onSuccess: () => void }
  │     └─ RegisterForm: { onSuccess: () => void }
  │
  └─ CookieBanner
     └─ Props: none (самостоятельный)
```

## 🚀 Lifecycle Events

```
App Load
  ↓
index.js → App.js (load styles)
  ↓
Home.jsx mounted
  ↓
  ├─ Navbar renders
  ├─ Hero renders
  ├─ QuickActions renders
  ├─ NewsSection renders (useEffect for IntersectionObserver)
  │  └─ Elements observer инициализируется
  ├─ Footer renders
  ├─ AuthModal renders (hidden)
  └─ CookieBanner renders + setTimeout(900ms)
     └─ CookieBanner appears

User Action: Click Navbar "Войти"
  ↓
Navbar onOpenAuth() → Home handleOpenAuth()
  ↓
isAuthModalOpen = true
  ↓
AuthModal opens with animation

User Action: Login
  ↓
LoginForm onSubmit
  ↓
Validation → API call (api.login)
  ↓
Success → onSuccess() → Home handleCloseAuth()
  ↓
isAuthModalOpen = false → AuthModal closes
```

## 📦 File Size Estimate

```
Components:
├─ Navbar.jsx + .module.css           ~140 lines
├─ Hero.jsx + .module.css             ~105 lines
├─ QuickActions.jsx + .module.css     ~145 lines
├─ News/
│  ├─ All .jsx files                  ~240 lines
│  └─ NewsSection.module.css          ~450 lines
├─ Footer.jsx + .module.css           ~230 lines
├─ AuthModal/
│  ├─ All .jsx files                  ~390 lines
│  └─ AuthModal.module.css            ~450 lines
└─ CookieBanner.jsx + .module.css     ~215 lines

Styles:
├─ variables.css                      ~80 lines
└─ global.css                         ~110 lines

Services & Pages:
├─ api.js                             ~150 lines
└─ Home.jsx                           ~30 lines

App Core:
├─ App.js                             ~10 lines
└─ index.js                           ~13 lines

TOTAL: ~2,800 lines of code (HTML + CSS + JS combined)
```

## 🔑 Ключевые решения

### 1. CSS Modules + Variables
```css
/* Изоляция стилей на компонент */
import styles from './Component.module.css';
/* Использование design tokens */
.container { background: var(--cream); }
```

### 2. Props для управления состоянием
```jsx
<Navbar onOpenAuth={handleOpenAuth} />
<AuthModal isOpen={isAuthModalOpen} onClose={handleCloseAuth} />
```

### 3. Валидация на клиенте + UI feedback
```jsx
className={errors.email ? styles.err : email && isEmail(email) ? styles.ok : ''}
```

### 4. localStorage для preferences
```jsx
localStorage.setItem('mindcare_cookie_choice', 'accepted');
```

### 5. IntersectionObserver для animations
```jsx
useEffect(() => {
  const observer = new IntersectionObserver(...);
  elements.forEach(el => observer.observe(el));
}, []);
```

---

## 🎯 Расширение на будущее

```
Текущее:
├─ Home page
└─ Auth forms

Future:
├─ Router (React Router v6)
│  ├─ /home
│  ├─ /news/:id
│  ├─ /psychologists
│  ├─ /profile
│  └─ /appointments
│
├─ State Management (Redux/Context)
│  ├─ authSlice (user, token, isAuthenticated)
│  ├─ newsSlice (news, loading, error)
│  └─ appointmentsSlice
│
├─ More Pages
│  ├─ NewsDetail.jsx
│  ├─ PsychologistsList.jsx
│  ├─ BookingPage.jsx
│  └─ ProfilePage.jsx
│
└─ More Features
   ├─ Dark mode toggle
   ├─ Multi-language support
   ├─ Search functionality
   └─ Advanced filtering
```

---

**Last Updated**: 2025  
**Status**: ✅ Complete & Ready for Production

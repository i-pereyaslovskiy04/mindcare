# MindCare Frontend — React Architecture

> Production-ready React application с чистой архитектурой и компонентным подходом

## 📋 Структура проекта

```
src/
├── components/                 # Переиспользуемые компоненты UI
│   ├── Navbar/                # Навигация
│   │   ├── Navbar.jsx
│   │   └── Navbar.module.css
│   ├── Hero/                  # Герой секция
│   │   ├── Hero.jsx
│   │   └── Hero.module.css
│   ├── QuickActions/          # Быстрые действия (3 карточки)
│   │   ├── QuickActions.jsx
│   │   └── QuickActions.module.css
│   ├── News/                  # Новости (многоуровневая структура)
│   │   ├── NewsSection.jsx    # Основной контейнер
│   │   ├── FeaturedNews.jsx   # Крупная новость
│   │   ├── NewsCardSmall.jsx  # Маленькие карточки
│   │   ├── NewsListItem.jsx   # Элемент списка
│   │   └── NewsSection.module.css
│   ├── Footer/                # Подвал с соцсетями
│   │   ├── Footer.jsx
│   │   └── Footer.module.css
│   ├── AuthModal/             # Модальное окно авторизации
│   │   ├── AuthModal.jsx      # Основной компонент
│   │   ├── LoginForm.jsx      # Форма входа с валидацией
│   │   ├── RegisterForm.jsx   # Форма регистрации с проверкой пароля
│   │   └── AuthModal.module.css
│   └── CookieBanner/          # Баннер cookies
│       ├── CookieBanner.jsx
│       └── CookieBanner.module.css
├── pages/                     # Page-level компоненты
│   └── Home.jsx              # Главная страница (сборка всех компонентов)
├── hooks/                     # Custom React hooks
│   └── useIntersectionObserver.js  # (подготовлено для будущих нужд)
├── services/                  # API и внешние сервисы
│   └── api.js                # Централизованный API клиент для FastAPI
├── styles/                    # Глобальные стили
│   ├── variables.css         # CSS переменные (цвета, типография, layout)
│   └── global.css            # Глобальные стили, reset, utilities
├── App.js                     # Главный компонент приложения
├── App.css                    # (устарело, используй компонентные стили)
├── index.js                   # Entry point
└── index.css                  # (устарело, используй global.css)
```

## 🎨 Архитектура стилей

### CSS Modules per Component
Каждый компонент имеет собственный `.module.css` файл:

```jsx
import styles from './MyComponent.module.css';

export default function MyComponent() {
  return <div className={styles.container}>...</div>;
}
```

### CSS Variables (Design Tokens)
Все цвета, размеры и типография определены в `src/styles/variables.css`:

```css
:root {
  --cream: #F5F0E8;
  --coffee: #8B6F47;
  --fs-h1: clamp(40px, 3.2vw, 64px);
  --ease-card: cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
```

### Global Styles
`src/styles/global.css` содержит:
- Типографию (шрифты, базовые стили)
- Reset и normalize
- Utilities (`.container`, `.section-wrap`, и т.д.)

## 🔧 Компоненты

### Navbar
- Логотип с выделением
- Навигационные ссылки
- Кнопка входа с иконкой
- **Props**: `onOpenAuth` — callback для открытия модального окна

### Hero
- Героический фон с градиентом
- Адаптивный текст
- Декоративные точки (dots)
- **Статик компонент** (не требует props)

### QuickActions
- 3 интерактивные карточки
- Иконки (календарь, звезда, юзер)
- **Props**: `onOpenAuth` — для карточки "Личный кабинет"

### NewsSection (Сложная структура)
Содержит:
- **FeaturedNews** — Крупная новость с hover эффектами
- **NewsCardSmall** × 2 — Маленькие карточки в колонке
- **NewsListItem** × 3 — Список новостей
- **Pagination** — Пагинация

**Особенности**:
- IntersectionObserver для анимации появления
- Разные иконки для разных типов новостей
- Полная поддержка keyboard navigation (Enter, Space)

### Footer
- Логотип и описание
- Навигационные ссылки
- 3 социальные сети (VK, Telegram, Yandex)
- Легальные ссылки и копирайт

### AuthModal (Самый сложный)

#### Структура:
```
AuthModal (родитель)
├── LoginForm (активна если tab === 'login')
│   ├── Social buttons (Telegram, VK, Yandex)
│   ├── Email field (с валидацией)
│   ├── Password field
│   ├── "Забыли пароль?" ссылка
│   └── Submit button
└── RegisterForm (активна если tab === 'register')
    ├── Social buttons
    ├── Name field (мин. 2 символа)
    ├── Email field
    ├── Password field (с индикатором силы)
    │   ├── Strength bars (слабый/средний/надёжный)
    │   └── Strength label
    ├── Confirm password field
    ├── Consent checkbox (политика)
    └── Submit button
```

#### Валидация:
- **Email**: Regex `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`
- **Password**: Минимум 8 символов
- **Strength**: Учитывает длину, заглавные буквы, цифры, спец. символы
- **Все поля обязательны**

#### Поведение:
- Клавиша Escape закрывает модаль
- Клик вне карточки закрывает
- Анимация появления/исчезновения
- После успешной отправки: симуляция (1.2-1.4 сек) → успех → закрытие

### CookieBanner
- Появляется через 900мс после загрузки
- Сохраняет выбор в localStorage
- Не показывается повторно
- Гладкая анимация появления/исчезновения

## 🚀 Использование компонентов

### Базовая страница (Home.jsx)

```jsx
import { useState } from 'react';
import Navbar from '../components/Navbar/Navbar';
import AuthModal from '../components/AuthModal/AuthModal';
import Footer from '../components/Footer/Footer';

export default function Home() {
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthModalOpen(true)} />
      {/* ... остальные компоненты */}
      <AuthModal isOpen={isAuthModalOpen} onClose={() => setIsAuthModalOpen(false)} />
    </>
  );
}
```

## 🔌 API Integration

Все API вызовы централизованы в `src/services/api.js`:

```javascript
// Примеры
await login(email, password);           // POST /api/login
await register(name, email, password);  // POST /api/register
await getProfile();                     // GET /api/profile
await logout();                         // POST /api/logout
await getNews(page, limit);            // GET /api/news?page=X&limit=Y
await bookAppointment(data);           // POST /api/appointments
await getPsychologists();              // GET /api/psychologists
```

**Базовый URL** берется из переменной окружения:
```
REACT_APP_API_URL=http://localhost:8000/api
```

Или использует прокси из `package.json`:
```json
"proxy": "http://localhost:8000"
```

## 🎨 Стили и Кастомизация

### Добавление нового компонента

1. **Создайте папку**:
   ```
   src/components/MyComponent/
   ```

2. **Создайте JSX файл**:
   ```jsx
   import styles from './MyComponent.module.css';

   export default function MyComponent({ prop1, prop2 }) {
     return <div className={styles.container}>...</div>;
   }
   ```

3. **Создайте CSS module**:
   ```css
   .container {
     background: var(--cream);
     padding: var(--container-px);
     border-radius: 12px;
     transition: background 0.15s ease;
   }

   .container:hover {
     background: var(--sand);
   }
   ```

4. **Используйте в других компонентах**:
   ```jsx
   import MyComponent from '../components/MyComponent/MyComponent';

   export default function Page() {
     return <MyComponent prop1="value" />;
   }
   ```

### CSS Переменные (Design System)

**Цвета** (в `variables.css`):
```css
--cream: #F5F0E8;        /* Фон */
--warm-white: #FAF7F2;   /* Теплый белый */
--latte: #C9B99A;        /* Светло-коричневый */
--coffee: #8B6F47;       /* Коричневый */
--espresso: #4A3728;     /* Темный коричневый */
```

**Типография**:
```css
--fs-h1: clamp(40px, 3.2vw, 64px);  /* Адаптивный размер */
--lh-h1: 1.12;                      /* Line height */
--ls-nav: 0.03em;                   /* Letter spacing */
```

**Layout**:
```css
--container-max: 1320px;        /* Макс ширина */
--container-px: clamp(16px, 4vw, 80px);  /* Адаптивные отступы */
--grid-gap: clamp(12px, 1.2vw, 18px);    /* Зазор сетки */
```

## 📱 Responsive Design

Все компоненты адаптивны с использованием:
- **CSS Grid** для макетов
- **Clamp()** для адаптивных размеров
- **Media queries** для больших изменений

```css
@media (max-width: 1024px) {
  .newsGrid {
    grid-template-columns: 1fr;  /* От 2 колонок к 1 */
  }
}

@media (max-width: 768px) {
  .socialBtns {
    justify-content: center;
    gap: 10px;
  }
}
```

## ♿ Accessibility

Все компоненты соблюдают WCAG 2.1:
- Семантические HTML теги (`<button>`, `<nav>`, `<section>`, `<footer>`)
- `aria-*` атрибуты для модалей, лейблов, иконок
- Keyboard navigation (Tab, Enter, Space, Escape)
- Контраст цветов соответствует стандартам
- Фокусные стили (`:focus-visible`)

Пример:
```jsx
<button
  className={styles.authClose}
  onClick={onClose}
  aria-label="Закрыть"
  type="button"
>
  <CloseIcon />
</button>
```

## 🧪 Тестирование

### Для компонентов используйте Jest + React Testing Library:

```javascript
import { render, screen } from '@testing-library/react';
import Navbar from './Navbar';

test('renders navbar with navigation links', () => {
  render(<Navbar onOpenAuth={() => {}} />);
  expect(screen.getByText('Главная')).toBeInTheDocument();
});
```

## 🚀 Развертывание

### Production build:
```bash
npm run build
```

Будет создана папка `build/` с оптимизированным кодом.

### С Docker:
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

## 📝 Лучшие практики

### ✅ Делайте так:
- Используйте CSS Modules для изоляции стилей
- Разделяйте логику и представление
- Пишите компоненты как функции
- Используйте мемоизацию где нужно (`React.memo`, `useMemo`)
- Документируйте пропсы в JSDoc

### ❌ Не делайте так:
- Не используйте inline стили
- Не миксуйте CSS и CSS-in-JS
- Не создавайте огромные компоненты (>300 строк)
- Не забывайте про accessibility
- Не коммитьте console.log и дебаг-код

## 🔗 Интеграция с Backend (FastAPI)

Приложение готово к интеграции с FastAPI через `src/services/api.js`.

### Требуемые endpoint'ы:

```
POST   /api/login              — Вход
POST   /api/register           — Регистрация
POST   /api/logout             — Выход
GET    /api/profile            — Профиль юзера
POST   /api/forgot-password    — Забыл пароль
POST   /api/reset-password     — Восстановить пароль
GET    /api/news               — Список новостей
GET    /api/news/:id           — Одна новость
GET    /api/psychologists      — Список психологов
POST   /api/appointments       — Забронировать прием
GET    /api/psychologists/:id/available-slots — Доступные времена
```

Все endpoint'ы должны возвращать JSON.

## 📚 Дополнительные ресурсы

- [React Documentation](https://react.dev)
- [CSS Modules](https://github.com/css-modules/css-modules)
- [WCAG Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [Clamp() функция](https://developer.mozilla.org/en-US/docs/Web/CSS/clamp)

---

**Автор**: Senior Frontend Developer | Дата: 2025  
**Версия**: 1.0.0 (Production Ready)

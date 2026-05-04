# MindCare Frontend — Руководство по запуску

## ⚡ Быстрый старт

### 1. Установка зависимостей

```bash
cd mindcare_web
npm install
```

### 2. Запуск dev-сервера

```bash
npm start
```

Приложение откроется на `http://localhost:3000`

### 3. Запуск backend'а (FastAPI)

В отдельном терминале:

```bash
cd mindcare_api
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend будет доступен на `http://localhost:8000`

**Frontend автоматически будет проксировать запросы на backend** благодаря настройке в `package.json`:

```json
"proxy": "http://localhost:8000"
```

## 🧪 Тестирование

### Запуск тестов

```bash
npm test
```

### Тестирование отдельного файла

```bash
npm test -- --testPathPattern=App.test.js
```

### Запуск с coverage

```bash
npm test -- --coverage
```

## 🎯 Проверка компонентов

### Navbar
- [x] Логотип отображается
- [x] Ссылки навигации кликабельны
- [x] Кнопка пользователя открывает AuthModal

### Hero
- [x] Градиент фон применяется
- [x] Текст адаптивный (clamp)
- [x] Точки видны

### QuickActions
- [x] 3 карточки отображаются
- [x] Иконки загружаются
- [x] Hover эффекты работают

### News
- [x] Крупная новость отображается
- [x] Маленькие карточки в колонке
- [x] Список новостей 3 items
- [x] Пагинация видна
- [x] Анимация работает (IntersectionObserver)
- [x] Hover эффекты на всех карточках

### AuthModal
- [x] Открывается при нажатии на кнопку входа
- [x] Закрывается на Escape
- [x] Закрывается при клике вне модали
- [x] Табы переключаются правильно
- [x] **Login форма**: Email и Password валидируются
- [x] **Register форма**: 
  - Email валидируется
  - Пароль проверяет минимум 8 символов
  - Strength indicator работает
  - Пароли совпадают
  - Checkbox consent обязателен

### CookieBanner
- [x] Появляется через 900мс
- [x] Выбор сохраняется в localStorage
- [x] Не появляется повторно

### Footer
- [x] Логотип и описание
- [x] Ссылки на соцсети
- [x] Копирайт и легальные ссылки

## 🎨 Проверка стилей

### Цвета
Все цвета должны соответствовать переменным в `src/styles/variables.css`

### Адаптивность
```bash
# Используй DevTools для проверки
1. Откой DevTools (F12)
2. Переключись в Responsive Mode (Ctrl+Shift+M)
3. Проверь разные экраны (480px, 768px, 1024px, 1440px)
```

### Анимации
- Hover эффекты плавные (0.15s - 0.35s)
- Модаль открывается с масштабированием
- Новости появляются с translateY + fade

## 🔗 API тестирование

### Проверь що backend работает

```bash
# В браузере или Postman
http://localhost:8000/docs
```

Это откроет Swagger UI с документацией всех endpoint'ов

### Пример запроса

```javascript
// В консоли браузера
fetch('/api/hello')
  .then(r => r.json())
  .then(d => console.log(d))
```

## 📦 Build для продакшена

```bash
npm run build
```

Будет создана папка `build/` с оптимизированным кодом.

### Проверь что всё работает:

```bash
# Локальная проверка build
npm install -g serve
serve -s build
```

Откроет приложение на `http://localhost:3000`

## 🚀 Развертывание на сервер

### Vercel (рекомендуется)

```bash
npm install -g vercel
vercel
```

### Netlify

1. Создай `netlify.toml`:
```toml
[[redirects]]
  from = "/api/*"
  to = "http://localhost:8000/api/:splat"
  status = 200
```

2. Deploy:
```bash
npm run build
# Залей папку build/ на Netlify
```

### Docker

1. Создай `Dockerfile`:
```dockerfile
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:18-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/build ./build
EXPOSE 3000
CMD ["serve", "-s", "build"]
```

2. Build и run:
```bash
docker build -t mindcare-web .
docker run -p 3000:3000 mindcare-web
```

## 🐛 Debugging

### React DevTools

Установи расширение для браузера: [React DevTools](https://react-devtools.io)

### Логирование

```javascript
// Добавь в любой компонент
console.log('Component mounted', props);

// Для трассировки стейта
const [count, setCount] = useState(0);
console.log('Count updated to:', count);
```

### Network tab

1. Открой DevTools → Network
2. Выполни действие (например, логин)
3. Проверь запрос: метод, статус, response

### Console errors

Все ошибки и предупреждения появляются в Console.

Обрати внимание на:
- Red errors - критические
- Yellow warnings - можно игнорировать
- Blue info - информационные

## ⚙️ Переменные окружения

### .env файл

Создай `mindcare_web/.env`:

```env
REACT_APP_API_URL=http://localhost:8000/api
REACT_APP_ENV=development
REACT_APP_VERSION=1.0.0
```

### Доступ в коде

```javascript
const apiUrl = process.env.REACT_APP_API_URL;
const isDev = process.env.REACT_APP_ENV === 'development';
```

## 📊 Performance

### Lighthouse

1. Открой DevTools
2. Перейди на вкладку Lighthouse
3. Нажми "Analyze page load"

Стремись к:
- Performance: > 80
- Accessibility: > 90
- Best Practices: > 90
- SEO: > 90

### Bundle size

```bash
npm install -g webpack-bundle-analyzer
npm run build
# Если добавишь плагин в конфиг CRA
```

## 🎯 Контрольный список перед продакшеном

- [ ] Все компоненты тестированы
- [ ] Нет console.log/debugger в коде
- [ ] Все API запросы обработаны
- [ ] Ошибки отображаются пользователю
- [ ] Responsive дизайн проверен
- [ ] Keyboard navigation работает
- [ ] Accessibility OK (lighthouse > 90)
- [ ] Performance OK (lighthouse > 80)
- [ ] SEO OK (мета теги, структура)
- [ ] HTTPS настроен
- [ ] CORS настроен на backend'е

## 📞 Поддержка

При возникновении проблем:

1. **Проверь консоль браузера** (F12 → Console)
2. **Проверь Network tab** - есть ли ошибки запросов
3. **Перезагрузи страницу** (Ctrl+F5)
4. **Очисти node_modules и переустанови**:
   ```bash
   rm -rf node_modules package-lock.json
   npm install
   ```

---

**Версия документа**: 1.0.0  
**Последнее обновление**: 2025

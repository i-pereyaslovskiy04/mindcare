# Handoff (2026-10-14): единая шапка кабинетов — CabinetHeader и кнопка «Оформление»

Решение — **ADR-031**. Frontend-only: backend, API, БД, миграции, audit REGISTRY
не менялись. Правила — `mindcare_web/CLAUDE.md` (блок «Шапка кабинетов»),
устройство — `mindcare_web/ARCHITECTURE.md` (раздел CabinetHeader).

## Главное

- **Одна шапка** `components/CabinetHeader/` у CabinetLayout (student,
  psychologist, supervisor) и AdminLayout. Справа строго:
  [CabinetSwitcher, только 601–980px] → Поиск → Уведомления → Оформление → Выход.
  Layout'ы не объединялись: brand, sidebar и навигация остались в своих файлах
  (mobile drawer — общий, см. «Mobile shell» ниже).
- **Brand — ссылка** на корень кабинета: `/student`, `/psychologist`,
  `/supervisor`, `/admin` (index-редирект на `/admin/users`). Работает и
  монограмма «ПД» (Психология ДонГУ, вместо прежней «М») в icon-rail <=980px, и brand в mobile drawer (клик закрывает drawer).
  Home-иконка на публичный `/` удалена.
- **Крошки** — `nav` «Навигационная цепочка» + `ol`: «Главная» — ссылка,
  текущая — текст с `aria-current="page"`. Подписи только из явной
  конфигурации (`breadcrumbs.js` → `resolveBreadcrumbs`); `dynamicCrumbs[].parent`
  даёт промежуточный уровень: «Главная / Мои студенты / Карточка студента»,
  «Главная / Тесты / Тест» (психолог, супервизор, админ). Вложенная страница
  без подписи показывает ближайший известный раздел ссылкой. <=600px
  промежуточные уровни скрыты.
- **Заглушки честные:** поиск — `<input type="search" disabled>` без формы,
  подсказка «Поиск будет доступен позже», скрыт <=980px; колокольчик —
  `aria-disabled`, «Уведомления — скоро», без красной точки (на mobile виден).
  Кнопка-конверт удалена (у «Сообщений» свой счётчик в навигации).
- **«Оформление» — одна кнопка** вместо «глаза» и палитры. Панель: секция
  «Оформление» (режим + палитра — `ThemeToggle compact`), разделитель, секция
  «Версия для слабовидящих» с **существующим** `A11yToggle` (новый вариант
  отображения `block` + колбэк `onToggle`; `enable`/`disable` прежние). После
  переключения версии панель закрывается, фокус — на кнопку; `A11yPanel`
  по-прежнему под шапкой.
- **`hc` убрана из обычного списка тем** (и в шапке, и в Navbar — список один).
  Палитра осталась в ThemeContext/токенах/профиле и включается по
  `prefers-contrast: more`; если активна — пункт виден выбранным.

## Изменённые файлы

| Файл | Что |
|---|---|
| `components/CabinetHeader/CabinetHeader.jsx` + `.module.css` | новая шапка; `className`, `cabinetRole`, `breadcrumbs`, hamburger (`onMenuOpen`, `menuOpen`, `menuId`, `menuButtonRef`) |
| `components/CabinetDrawer/CabinetDrawer.jsx` + `.module.css` | общий mobile drawer (фокус, Tab по кругу, Escape, backdrop) |
| `pages/student/StudentHome.module.css` | карточки действий — одна колонка уже на <=768px |
| `components/CabinetHeader/breadcrumbs.js` | `resolveBreadcrumbs({ pathname, homePath, crumbLabels, dynamicCrumbs })` |
| `components/CabinetLayout/CabinetLayout.jsx` + `.module.css` | brand → `Link`, topbar → CabinetHeader; стили шапки удалены, остались отступы `.topbar` и `.mobileMenuButton` |
| `features/admin/AdminLayout.jsx` + `.module.css` | то же; `DYNAMIC_CRUMBS` для `/admin/tests/…` |
| `features/theme/ThemeToggle.jsx` + `.module.css` | compact: `label`, `extraSection`, секции, палитры — `button aria-pressed`, фокус в панель, Tab по кругу, позиция по реальной ширине панели; `hc` скрыта, если не активна |
| `features/a11y/A11yToggle.jsx` + `.module.css` | вариант `block` и `onToggle` (логика не менялась) |
| `pages/psychologist/PsychologistLayout.jsx`, `pages/supervisor/SupervisorLayout.jsx` | `parent` в `DYNAMIC_CRUMBS` |

Тесты: новый `CabinetHeader.test.jsx` (шапка + `resolveBreadcrumbs`);
обновлены `CabinetLayout.test.jsx`, `AdminLayout.test.jsx`,
`ThemeToggle.test.jsx`, `A11y.test.jsx`.

Осознанно изменённые прежние тесты: `AdminLayout` «На главную → /» (home-иконки
больше нет — проверяется brand → `/admin`); `ThemeToggle` — 5 палитр → 4 (hc),
выбор hc из списка → активная hc видна выбранной; compact-палитры — `button`
вместо `option` с `mouseDown`.

## Не делалось

Глобальный поиск, центр уведомлений/API, Messenger, роли, маршруты, sidebar,
логика темы и A11y, A11yPanel, пересборка
`guides/*.docx`/`*.pdf`. Follow-up'ы — `docs/BACKLOG.md`, «Шапка кабинетов —
продолжение».

## Проверить руками (manual smoke)

>980px, 601–980px (icon-rail), <=600px (drawer у всех кабинетов и админки),
390–480px: шапка в одну линию, общая линия под brand и шапкой не рвётся,
выход и «Оформление» видны всегда; панель «Оформление» не уходит за край
экрана; переключение версии для слабовидящих из панели и обратно; brand и
«Главная» ведут на корень кабинета; в тёмной теме и в версии для
слабовидящих (ссылки там подчёркиваются — это и brand, и крошки).

## Mobile shell (дополнение, 2026-10-14)

ADR-031, «Дополнение (mobile shell)». Frontend-only.

- **Admin = та же модель, что кабинеты:** >980px полный sidebar, 601–980px
  rail 72px «ПД», <=600px sidebar скрыт, hamburger в шапке открывает drawer
  «Меню панели управления» с той же разметкой sidebar (`sidebarInner`:
  brand → `/admin`, пользователь + CabinetSwitcher, `ADMIN_NAV_GROUPS`,
  footer). Правила rail ограничены `.sidebar`. Отступы шапки админки на
  <=600/<=480px (были под rail) убраны — действует правило <=980px.
- **`CabinetDrawer`** — общий drawer: фокус на «Закрыть меню», Tab по кругу,
  Escape/backdrop/пункт/brand закрывают, фокус — обратно на hamburger.
- **Шапка на <=600px:** hamburger → крошки → Уведомления → Оформление → Выход;
  колокольчик больше не скрывается, CabinetSwitcher — только в drawer. Ширина
  крошек: 360px — ~134px (кабинеты) / ~148px (admin), 390px — ~164 / ~178px;
  «Оформление» остаётся в шапке.
- **601 → 600:** `StudentHome .actionCardsGrid` уходила в одну колонку только на
  <=600px (viewport), а на 601px рядом с rail контенту остаётся ~497px → две
  колонки по ~230px. Одна колонка теперь на <=768px (с 769px rail-контент
  ≥665px → две колонки ≥325px). Другие страницы не трогались.

# MindCare Web — Frontend Diagrams

> Updated: 2026-06-08
> Все диаграммы описывают только frontend (`mindcare_web/src`).
> Backend — внешний API, взаимодействие через `api/client.js`.

---

## 1. Роли и маршруты

```mermaid
flowchart TD
    U([Пользователь]) --> PUB[Публичные страницы\n/ /about /services\n/news /materials]
    U --> LOGIN[/login /register]

    LOGIN --> AUTH{Аутентификация}

    AUTH -->|role: student| STU[/student/*]
    AUTH -->|role: psychologist| PSY[/psychologist/*]
    AUTH -->|role: supervisor| SUP[/supervisor/*]
    AUTH -->|role: admin| ADM[/admin/*]
    AUTH -->|любая роль| PROF[/profile]
    AUTH -->|редирект| DASH[/dashboard → DashboardRedirect]
    DASH --> STU
    DASH --> PSY
    DASH --> SUP
    DASH --> ADM

    STU --> STU1[/student — главная]
    STU --> STU2[/student/diary]
    STU --> STU3[/student/tests]
    STU --> STU4[/student/materials]
    STU --> STU5[/student/tasks]
    STU --> STU6[/student/chat]
    STU --> STU7[/student/calendar]
    STU --> STU8[/student/settings]

    PSY --> PSY1[/psychologist — главная]
    PSY --> PSY2[/psychologist/settings]

    SUP --> SUP1[/supervisor — главная]
    SUP --> SUP2[/supervisor/engagements ✅]
    SUP --> SUP3[/supervisor/settings]

    ADM --> ADM1[/admin/users]
    ADM --> ADM2[/admin/categories]
    ADM --> ADM3[/admin/tags]
    ADM --> ADM4[/admin/news]
    ADM --> ADM5[/admin/articles]
```

---

## 2. Структура frontend

```mermaid
graph TD
    SRC[src/]

    SRC --> APP[app/\nApp.jsx\nrouter.jsx\nproviders.jsx]
    SRC --> API[api/\nclient.js\nauth / users / tags\ncategories / news\narticles / materials\nsupervisor / media / health]
    SRC --> SHARED[shared/lib/\nutils.js\ngetInitials]
    SRC --> HOOKS[hooks/\nuseDebounce\nuseNews\nuseMaterials]
    SRC --> DATA[data/\n*.mock.js]

    SRC --> FEAT[features/]
    FEAT --> FAUTH[auth/\nAuthContext\nLoginForm\nRegisterForm\nForgotPassword]
    FEAT --> FSUPER[supervisor/\nhooks/useStudents\ncomponents/AssignModal]
    FEAT --> FADMIN[admin/\nAdminLayout\nusers / categories\ntags / news / articles]
    FEAT --> FPROFILE[profile/\nProfilePage]
    FEAT --> FNEWS[news/\nNewsSection\nFeaturedNews]

    SRC --> COMP[components/]
    COMP --> ICON[Icon/\nIcon.jsx]
    COMP --> CAB[CabinetLayout/\nCabinetLayout.jsx\nCabinetSettingsPage.jsx]
    COMP --> MODAL[Modal/\nModal.jsx]
    COMP --> UI[UI/\nMultiSelect\nTiptapEditor\nImageUpload\nContentPreview]
    COMP --> NAV[Navbar / Footer\nHero / CookieBanner]

    SRC --> PAGES[pages/]
    PAGES --> PPUB[Публичные\nhome / about / services\nnews / materials]
    PAGES --> PSTUD[student/\nStudentLayout\nStudentHome\nDiary / Tests\nMaterials / Tasks\nChat / Calendar\nSettings]
    PAGES --> PPSY[psychologist/\nPsychologistLayout\nPsychologistHome]
    PAGES --> PSUP[supervisor/\nSupervisorLayout\nSupervisorHome\nEngagementsPage]
    PAGES --> PCLIENT[client/\nClientDashboard\nОутер-обёртка /student]
```

---

## 3. Layout-архитектура кабинетов

```mermaid
graph TD
    CAB[CabinetLayout\ncomponents/CabinetLayout/]

    PLAYOUT[PsychologistLayout\npages/psychologist/] -->|использует| CAB
    SLAYOUT[SupervisorLayout\npages/supervisor/] -->|использует| CAB

    CAB --> SETTPAGE[CabinetSettingsPage\nобщая страница настроек]
    PLAYOUT -->|/psychologist/settings| SETTPAGE
    SLAYOUT -->|/supervisor/settings| SETTPAGE

    STULAYOUT[StudentLayout\npages/student/] -.->|не использует CabinetLayout| X[собственный Sidebar]

    CAB --> GETINIT[getInitials\nshared/lib/utils.js]
    CAB --> ICONC[Icon\ncomponents/Icon/Icon.jsx]
```

---

## 4. Auth flow

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant F as LoginForm
    participant AC as AuthContext
    participant API as api/client.js
    participant BE as FastAPI Backend

    U->>F: email + password
    F->>AC: login(email, password)
    AC->>BE: POST /api/auth/login
    BE-->>AC: { token, user }
    AC->>AC: localStorage.setItem(token)
    AC->>AC: setState({ user })
    AC-->>F: success
    F->>U: redirect → /dashboard

    note over AC,BE: При каждом запросе
    API->>BE: GET /api/... + Bearer token
    BE-->>API: 401 (истёкшая сессия)
    API->>AC: dispatch auth:session-expired
    AC->>AC: logout()
    AC->>U: redirect → /login
```

---

## 5. Supervisor engagements frontend flow

```mermaid
sequenceDiagram
    participant S as Supervisor
    participant EP as EngagementsPage
    participant US as useStudents hook
    participant SAPI as supervisor.api.js
    participant AM as AssignModal
    participant BE as FastAPI Backend

    S->>EP: открывает /supervisor/engagements
    EP->>US: mount → fetchStudents(page=1, query='')
    US->>SAPI: getSupervisorStudents({ page, size, search })
    SAPI->>BE: GET /api/supervisor/students?page=1&size=20
    BE-->>SAPI: { items: [...], total: N }
    SAPI-->>US: data
    US-->>EP: { items, total, loading: false }
    EP->>S: таблица студентов

    S->>EP: вводит текст в поиск
    EP->>US: setQuery(text)
    US->>US: debounce 300ms → setPage(1)
    US->>SAPI: getSupervisorStudents({ search: text })
    SAPI->>BE: GET /api/supervisor/students?search=...
    BE-->>SAPI: { items: [...], total: M }
    US-->>EP: обновлённый список

    S->>EP: нажимает «Назначить» на строке студента
    EP->>AM: openModal('assign', student)
    AM->>SAPI: getSupervisorPsychologists({ size: 200 })
    SAPI->>BE: GET /api/supervisor/psychologists
    BE-->>AM: { items: [психологи] }
    AM->>S: форма выбора психолога

    S->>AM: выбирает психолога + submit
    AM->>EP: onConfirm({ selectedPsyId, primaryConcern })
    EP->>SAPI: createEngagement({ client_id, psychologist_id })
    SAPI->>BE: POST /api/supervisor/engagements
    BE-->>EP: engagement создан
    EP->>EP: closeModal() + refetch()
    EP->>S: таблица обновлена
```

---

## 6. Data flow (общий)

```mermaid
graph LR
    UI[Компонент / Page] -->|вызывает| HOOK[Custom Hook]
    HOOK -->|вызывает| APIFN[api/*.api.js]
    APIFN -->|через| CLIENT[api/client.js\ntoken + 401 retry]
    CLIENT -->|HTTP| BE[FastAPI Backend]
    BE -->|JSON| CLIENT
    CLIENT -->|Promise| APIFN
    APIFN -->|Promise| HOOK
    HOOK -->|setState| UI
```

---

## 7. Supervisor API functions (frontend)

```mermaid
graph TD
    SAPI[supervisor.api.js]

    SAPI --> GS[getSupervisorStudents\nGET /api/supervisor/students\npage, size, search]
    SAPI --> GP[getSupervisorPsychologists\nGET /api/supervisor/psychologists\npage, size, search]
    SAPI --> GE[getSupervisorEngagements\nGET /api/supervisor/engagements\nstatus, student_search, psychologist_search]
    SAPI --> CE[createEngagement\nPOST /api/supervisor/engagements\nclient_id, psychologist_id, primary_concern]
    SAPI --> TE[transferEngagement\nPATCH /api/supervisor/engagements/:id/transfer\nnew_psychologist_id, transfer_reason]
    SAPI --> CLE[closeEngagement\nPATCH /api/supervisor/engagements/:id/close\nreason]
```

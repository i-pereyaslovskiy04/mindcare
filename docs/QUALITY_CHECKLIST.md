# MindCare Quality Checklist

Практический чек-лист перед каждым PR. Не подменяет CLAUDE.md — дополняет его
конкретными командами и запретами.

---

## 1. Scope discipline

- Один PR — одна логическая задача.
- Не смешивать backend migrations и frontend UI cleanup в одном PR.
- Не смешивать auth/session changes и cosmetic UI changes.
- Не смешивать Alembic/DB changes и React component migration.
- Не смешивать role policy changes и unrelated bug fixes.

Если задача — read-only аудит, обязательно указывать в промпте:

```text
Режим READ-ONLY.
Не менять код.
Не создавать файлы.
Не редактировать JSX/CSS/Python/MD/JSON.
Только анализ и финальный отчёт.
```

---

## 2. Required checks before PR

### Frontend

```bash
cd mindcare_web
npm run build
npm run lint
```

`npm run build` — обязателен всегда.
`npm run lint` — обязателен при любых изменениях `.js`/`.jsx`.
`--max-warnings 0` — новые warnings не допускаются.

### Backend

Если менялся Python-код:

```bash
cd mindcare_api
python -m compileall app scripts -q
pytest tests/ -v
```

Или из корня проекта: `.\test.ps1` (compileall + все backend-тесты).
Текущий ожидаемый статус: **138 passed**.

### Alembic

Запускать только когда задача касается БД-моделей или миграций:

```bash
cd mindcare_api
alembic upgrade head
alembic current
```

Не запускать Alembic в рамках read-only аудита или frontend-только PR.

---

## 3. UI governance

Перед созданием любого нового локального UI-контрола проверить:

```text
mindcare_web/src/components/UI
```

### Обязательные shared-компоненты

| Компонент | Использовать для |
|-----------|-----------------|
| `Button` | Все action-кнопки: сохранить, отменить, удалить, загрузить ещё, применить |
| `ButtonLink` | React Router навигационные ссылки в виде кнопки (`<Link>` со стилями Button). Не делать `Button + navigate()` для обычной навигации |
| `Checkbox` | Настоящие form-checkbox: согласие, active/inactive, published/unpublished |
| `Toggle` | On/off переключатели: уведомления, настройки |
| `FilterChip` | Интерактивные фильтры с active/inactive состоянием |
| `Badge` | Display-only статусы, роли и состояния: опубликовано, черновик, активен, заблокирован |
| `Tag` | Display-only теги контента: тема материала, тег новости, категория статьи |
| `Select` / `MultiSelect` | Выбор одного или нескольких значений |

### Запрещено без явного обоснования

- Создавать локальные `.btn*`, `.checkbox*`, `.toggle*`, `.chip*`, `.badge*`, `.tag*` если подходит shared-компонент.
- Использовать `button` для display-only элементов — использовать `span`.
- Использовать `span/div` для интерактивных элементов — использовать `button/input`.

### Допустимые feature-specific исключения

Следующие элементы намеренно остаются feature-specific:

- Calendar time slots / time picker
- Calendar format chips
- `CabinetLayout` nav badges / `navBadgeSoon`
- `CabinetLayout` notification dot
- `SearchBar` count overlay / removable chips
- `TaskItem` badges
- Chat controls (до отдельного Chat MVP решения)
- `DiaryEntryForm` emotion chips
- `FeaturedNews` newsTagOverlay
- `ContentPreview` category/tag
- `StudentHome` period chips / dark-card buttons
- `MultiSelect` selected tags внутри shared `MultiSelect`

Если элемент числится как feature-specific в `docs/UI_TECH_DEBT.md` — не мигрировать без отдельного решения.

---

## 4. Role policy

Актуальная модель доступа (зафиксирована в ADR-015):

| Роль | Кабинет | Область |
|------|---------|---------|
| `admin` | `/admin/*` | Пользователи, контент, новости, материалы, категории, теги |
| `supervisor` | `/supervisor/*` | Назначения студент ↔ психолог |
| `psychologist` | `/psychologist/*` | Свои студенты и сессии |
| `student` | `/student/*` | Личный кабинет |

**Supervisor не является content manager.**
Supervisor не должен роутиться в `/admin/*`.
Расширение прав supervisor требует отдельного ADR и изменения backend `require_role`.

---

## 5. Backend / Alembic rules

- Изменения SQLAlchemy-моделей должны сопровождаться Alembic-миграцией.
- Ручной SQL без Alembic запрещён, кроме явно согласованных emergency-операций.
- Перед создание миграции убедиться, что модели соответствуют желаемой схеме.
- Partial unique index `ux_therapy_engagements_active_client` должен учитываться в Alembic.
- `Base.metadata.create_all()` — не использовать (удалён; схема только через `alembic upgrade head`).
- Не вызывать `alembic.command.upgrade()` из FastAPI lifespan — deadlock.

---

## 6. Config / env rules

- Production/staging настройки — в `.env`, не захардкожены в коде.
- `.env.example` содержит все обязательные переменные.
- `.env` не коммитится (покрыт `.gitignore`).
- `ALLOWED_ORIGINS` — список frontend origins через запятую.
- `DATABASE_URL` не захардкожен в коде.

---

## 7. Logout / auth rules

- Использовать общий `useLogout` из `AuthContext`.
- Не создавать локальные logout flows.
- Logout UI внутри кабинетов — только в topbar layout (`CabinetLayout`, `AdminLayout`).
- Не дублировать logout-кнопки на settings pages.
- Изменения auth/session/token cleanup — отдельным PR.

---

## 8. Tables / pagination rules

- Table action buttons — shared `Button`.
- Статусы в таблицах — shared `Badge`.
- Теги в таблицах — shared `Tag`.
- Pagination: текущие реализации в admin news/articles/categories используют `Button variant="secondary" size="sm"`.
- Новые pagination-блоки — через те же shared `Button`, не через bare `<button>`.
- Выделенный shared `Pagination` — отдельный будущий этап, не в рамках inline-правок.

---

## 9. Documentation / ADR rules

- Архитектурные решения — в `docs/DECISIONS.md` в формате `ADR-NNN`.
- Изменение role policy требует ADR.
- Изменение модели доступа — отдельный этап с ADR.
- Не менять политику доступа молча внутри UI/backend PR.

---

## 10. Do not do in one PR

- Не начинать Chat MVP вместе с logout/roles cleanup.
- Не смешивать Alembic и UI cleanup.
- Не делать массовый CSS cleanup без предварительного visual check.
- Не запускать `eslint --fix` без отдельного разрешения.
- Не мигрировать все UI-компоненты за один PR.
- Не менять startup/seed и auth/session в одном PR.
- Не добавлять supervisor в admin routes без ADR.
- Не удалять `.env` без отдельного подтверждения.

---

## 11. Testing strategy / Стратегия тестирования

Проект не имеет полного покрытия тестами — это MVP, покрытие добавляется поэтапно.

### Правила добавления тестов

- Новые **auth/security/backend-critical** изменения должны сопровождаться минимум unit-тестами.
- Для **endpoint/session/permissions/encryption** flows — желательно API/integration tests.
- **Legacy-код** покрывается тестами при изменении, не раньше.
- Если тесты не добавлены — в финальном отчёте **явно объяснить причину**.
- Тесты не заменяют manual smoke для пользовательских сценариев.
- "Тесты прошли" ≠ "всё работает" — только покрытые зоны гарантированы.

### Уровни тестов

| Уровень | Что тестирует | Текущий статус |
|---------|---------------|----------------|
| **Unit** | Service/helper business logic, без реальной БД | 97 тестов: change_password (13), encryption (21), normalization (16), smtp_transport (21), rate_limit (18), session_security (8) |
| **API/Integration** | Route → deps → service → storage → DB (нужен dev PostgreSQL на alembic head) | 41 тест: email_normalization_api (11), rate_limit_api (10), session_token_hashing (9), legal_basis_api (11) |
| **Manual smoke** | Пользовательские сценарии | Обязателен при UI/UX-sensitive изменениях |
| **E2E** | Полный browser flow | Позже, когда UI стабилизируется |

Итого: **138 passed** (`.\test.ps1`).

### Обязательные проверки перед PR

**Backend (вручную):**

```bash
cd mindcare_api
.venv\Scripts\python.exe -m compileall app -q
.venv\Scripts\python.exe -m pytest tests/ -v
```

**Frontend (при изменениях .js/.jsx):**

```bash
cd mindcare_web
npm run lint
npm run build
```

**Через скрипты в корне проекта:**

```powershell
.\test.ps1    # compileall + все backend-тесты (без запуска проекта)
.\start.ps1   # backend-тесты, затем запуск проекта
```

`start.ps1` всегда запускает `test.ps1` перед стартом серверов — проект не стартует если тесты упали.
`test.ps1` используется для ручной проверки в любой момент без запуска серверов.

### Manual smoke — пример для смены пароля

1. Войти в кабинет (студент / психолог / супервизор).
2. Перейти в Settings → Безопасность → сменить пароль.
3. Убедиться, что произошёл автоматический выход и открылась AuthModal с сообщением «Пароль изменён. Войдите снова.»
4. Ввести **старый** пароль → получить «Неверный email или пароль».
5. Ввести **новый** пароль → успешный вход.

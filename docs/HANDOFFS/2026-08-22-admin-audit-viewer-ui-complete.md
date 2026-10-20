# Stage 8 UI — страница администратора «Журнал действий» (`/admin/audit`)

**Дата:** 2026-08-22
**Область:** только frontend (`mindcare_web/`) + связанная frontend-документация
**Backend:** не изменялся. Опирается на завершённый Stage 8 API —
`docs/HANDOFFS/2026-08-21-admin-audit-viewer-api-complete.md`, ADR-023.

---

## 1. Зачем

Stage 8 (backend) дал четыре read-only эндпоинта под `require_role("admin")`, но
прочитать журналы можно было только через curl или psql. Администратор не видел,
кто менял роли, кто читал заметки сессий, какие были неудачные входы —
построенный audit-контур оставался неоперабельным для того, ради кого делался.

Этот этап закрывает разрыв: интерфейс поверх уже готового и уже проверенного
контракта. Ни одна проверка доступа, ни одно правило проекции на фронт не
переносились — frontend не является границей доступа и ничего не решает сам.

---

## 2. Что сделано

Route `/admin/audit` внутри существующего admin `RoleRoute`, пункт «Журнал
действий» в группе «Система» sidebar'а, три вкладки:

| Вкладка | Журнал | Endpoint |
|---|---|---|
| Действия | `audit_log` | `GET /api/admin/audit/events` |
| Входы и безопасность | `auth_log` | `GET /api/admin/audit/auth-events` |
| Изменённые поля | `data_change_log` | `GET /api/admin/audit/data-changes` |

Справочник значений — `GET /api/admin/audit/options`.

**Журналы не объединяются в одну ленту** — ровно по тем же причинам, по которым
их не объединяет backend: разные контракты, разные безопасные DTO, отсутствие
надёжного correlation_id между `audit_log` и `data_change_log`.

---

## 3. Изменённые и новые файлы

**Новые (`mindcare_web/src/`):**

```
api/audit.api.js
features/admin/audit/
  lib/auditLabels.js · auditFormatters.js · auditFilters.js
  hooks/useAdminAuditLogs.js · useAuditOptions.js · useAuditActorSearch.js
  components/AuditTabs.jsx · AuditFilters.jsx · AuditActorPicker.jsx
             AuditTableShell.jsx · AuditEventsTable.jsx · AuthEventsTable.jsx
             DataChangesTable.jsx · AuditDetailsModal.jsx · AuditPagination.jsx
             rowKey.js
  pages/AuditLogsPage.jsx
(+ .module.css для AuditTabs, AuditFilters, AuditActorPicker, AuditTableShell,
   AuditDetailsModal, AuditPagination, AuditLogsPage)
```

**Изменённые:** `app/router.jsx`, `features/admin/AdminLayout.jsx`
(по одной строке в каждом), `app/router.test.jsx`,
`features/admin/AdminLayout.test.jsx`.

**Документация:** `mindcare_web/ARCHITECTURE.md` (§1 дерево, §3 маршруты,
§5 новый раздел «Admin Audit Viewer»), `docs/UI_TECH_DEBT.md` (три записи),
этот handoff. Backend-handoff от 2026-08-21 не переписывался.

---

## 4. Ключевые инварианты

### 4.1 Фильтры хранятся ПО ЖУРНАЛАМ

`lib/auditFilters.js`: состояние — `{ common, bySource }`, а не один плоский
объект. Причина конкретная: наборы допустимых значений у журналов **разные**.
`actor_kind=system` достижим для `audit_log` и недостижим для `auth_log` и
`data_change_log`; у `auth_log` фильтра роли нет вовсе. Общий объект при
переключении вкладки унёс бы чужое значение и получил 422.

`setFilters(patch)` маршрутизирует каждый ключ: общий срез → `common`, ключ
текущего журнала → его срез, неизвестный ключ отбрасывается (в dev — `warn`).
Отправить чужой ключ физически невозможно, а `api/audit.api.js` держит второй
allowlist на каждый endpoint.

### 4.2 Целочисленный идентификатор требует явного типа цели

Backend отвергает 422 и «id без типа», и пару «пользователь + id»: иначе
перебором целых чисел восстанавливалось бы отображение `users.id → UUID`. UI это
повторяет: поле точного идентификатора `disabled`, пока не выбран
не-пользовательский тип объекта / не-`users` таблица, и очищается при смене типа.
Значение отправляется только если это целое в `[1, 2147483647]`.

### 4.3 Пагинация ограничена окном выборки

`(page-1)*size + size ≤ max_result_window` ограничивает **достижимую страницу**, а
не только глубину: при `size=20` максимум `page=5000`. Обычный
`ceil(total/size)` при `total = 250 000` предложил бы страницу 5001 и
гарантированно получил 422. Поэтому

```js
totalPages = max(1, min(ceil(total/size), floor(maxResultWindow/size)))
```

и при срабатывании ограничения показывается пояснение «Доступны первые 100 000
записей — сузьте период или фильтры».

### 4.4 Выбранный участник принадлежит hook'у, а не picker'у

`AuditActorPicker` полностью controlled (`value` + `resetKey`). Если бы он держал
выбор у себя, «Сбросить фильтры» сняло бы `actor_uuid`, а подпись выбранного
человека осталась бы висеть на экране. `selectActor` атомарно ставит и
безопасную проекцию, и `actor_uuid`; `clearActor` и `resetFilters` идут одним
путём и меняют `actorResetKey`, по которому picker чистит строку поиска и выдачу.

Поиск использует admin users API, который отдаёт **полный** email. Проекция
делается сразу на выходе из API — в состояние попадают только
`{uuid, fullName, emailMasked, isDeleted}`; внутреннего `id` и полного адреса в
состоянии страницы журнала нет вообще. Маскирование повторяет правило backend
`mask_email`. Наружу уходит только `actor_uuid`; строка поиска нигде не
сохраняется.

### 4.5 Справочник и список — независимые состояния

Ошибка `/options` не подменяет ошибку списка и наоборот. При недоступном
справочнике таблица работает на базовых фильтрах (период, порядок, участник,
страница), registry-зависимые селекты отключаются, показывается отдельная кнопка
«Загрузить справочник заново». Лимиты берутся из `FALLBACK_LIMITS`; авторитетом
остаётся backend.

Справочник передаётся `useAdminAuditLogs` явным аргументом
(`{ options, limits }`) и читается внутри эффекта из ref — его загрузка не
вызывает второй запрос списка.

### 4.6 Закрытый рендеринг

Компоненты достают из DTO только разрешённые поля. `details` обходится по
закрытой карте `DETAIL_KEY_ORDER`, неизвестный ключ не показывается. Подписи
берутся из закрытых карт `lib/auditLabels.js`; неизвестный код получает
нейтральное «Неизвестное или историческое событие» — **никакого**
`replaceAll('_', ' ')`, иначе будущее backend-событие утекло бы в UI без ревью
подписи. Модалка строится из уже загруженной строки и не делает запроса.

Отсутствуют: `JSON.stringify` строки, `Object.entries` по ответу, spread в DOM,
`dangerouslySetInnerHTML`, copy-all, export, polling, raw-data viewer, запись в
`localStorage`/`sessionStorage`, синхронизация состояния с query string.

### 4.7 Время

Все метки журналов — `Europe/Moscow` независимо от TZ браузера, через
`Intl.DateTimeFormat` с `timeZone` (никогда не ручной `+3h`). В таблице — дата и
время с секундами, в подробностях — то же плюс явная подпись «МСК». Невалидная
метка → «—», без исключения.

### 4.8 BIGINT

`entry_id` приходит строкой и остаётся строкой. React-ключ строки —
`source:entry_id:occurred_at`.

---

## 5. Доступность

- вкладки — полный tablist: нативные `button` с `role="tab"`, `aria-selected`,
  `aria-controls`/`aria-labelledby`, стрелки, Home/End, roving `tabIndex`;
- combobox участника — `role="combobox"` на `input` с подписью,
  `aria-expanded`, `aria-controls`, `aria-autocomplete`, `aria-activedescendant`;
  список `role="listbox"`, элементы `role="option"`; ArrowUp/ArrowDown/Enter/Escape;
  после сброса фокус возвращается в поле;
- таблицы — `<caption>` (visually hidden), `<th scope="col">`, горизонтальный
  скролл внутри своего контейнера; строка целиком не кликабельна, подробности
  открывает отдельная icon-кнопка с содержательным `aria-label`;
- модалка — shared `Modal` (Escape, focus-trap, возврат фокуса);
- все кнопки `type="button"`, декоративные иконки `aria-hidden`, `Badge` —
  `<span>`;
- цвета только из токенов, ни одного нового hex/rgba; `npm run test:contrast`
  проходит (204 проверки, 0 нарушений).

---

## 6. Shared UI и feature-specific

**Переиспользованы:** `Button`, `Select`, `DateInput`, `Badge`, `Checkbox`,
`components/Modal/Modal`, `Icon`, `hooks/useDebounce`, `shared/lib/roles`
(`ROLE_LABELS`/`ROLE_BADGE_TONES`), `api/client.js` (`apiFetch`),
`api/users.api.js` (`getUsers`).

**Feature-specific** (обоснования — в `docs/UI_TECH_DEBT.md`): `AuditTabs`
(shared Tabs нет), `AuditActorPicker` (серверного асинхронного combobox нет),
таблицы + `AuditPagination` (shared DataTable/Pagination нет, у журналов свои
требования к разметке и к пределу страниц).

---

## 7. Проверки

| Проверка | Результат |
|---|---|
| targeted Jest (15 файлов feature + router + AdminLayout) | **287 passed** |
| `npm test -- --watchAll=false` | **1056 passed, 80 suites** |
| `npm run lint` | чисто (`--max-warnings 0`) |
| `npm run build` | Compiled successfully (+14.19 kB js, +1.59 kB css gzip) |
| `npm run test:contrast` | 204 проверки, 0 нарушений |
| `git diff --check` | чисто (только преднастроечные CRLF-предупреждения) |

Отдельно покрыто тестами: переход «Действия(`actor_kind=system`)» →
«Входы»/«Изменённые поля» не уносит недопустимое значение; `success=false` и
`include_access_events` сериализуются (истинностная проверка потеряла бы их);
поздний ответ не перезаписывает свежий ни в списке, ни в поиске участника;
все 25 пар таблица/поле `CHANGE_REGISTRY` имеют подпись и одноимённые поля
разных таблиц не подменяют друг друга; BIGINT `entry_id` не теряет точность;
synthetic-строка с 17 «канареечными» полями (`full_email`, `ip_address`,
`user_agent`, `session_id`, `request_url`, `description`, raw `metadata`,
`password`, `token`, `traceback`, SQL, `old_values`/`new_values`, plaintext
content, `mfa_method`, `failure_reason`) не появляется в DOM ни таблицы, ни
модалки.

Во всех фикстурах — только синтетические данные.

---

## 8. Что намеренно не сделано

- **`target_user_uuid` как фильтр** — второй user-picker («цель») выходил за
  запрошенный объём. Backend его поддерживает; добавляется отдельной задачей.
- **Синхронизация состояния с query string** — решение владельца задачи:
  остальные admin-страницы фильтры в URL не пишут, и так исключается риск
  случайно оставить в истории браузера UUID участника или период.
- **Категория событий не фильтрует выдачу** — API принимает ровно один точный
  код, поэтому категория только сокращает список опций. Под селектом стоит
  поясняющая подпись, чтобы это не читалось как молчаливый no-op.
- **Рефакторинг чужих admin-страниц** — локальный `Pagination` в `UsersPage` и
  `UsersTable` не трогались.
- Backend, миграции, package-файлы, `npm install`, auth/session storage, seed и
  RBAC не изменялись. Commit/push не выполнялись.

---

## 9. Открытые вопросы

- **Ручной smoke не выполнялся** — нужен прогон в браузере с живым backend:
  три вкладки бьют в три разных endpoint'а, «Обновить» не сбрасывает фильтры,
  модалка не порождает запрос, responsive на icon-rail (≤980px) и узком экране,
  режим ГОСТ.
- Shared `Tabs` и `AsyncCombobox` — кандидаты на вынос при втором потребителе.
- Deep paging за пределами `max_result_window` требует cursor pagination на
  backend (уже в `docs/BACKLOG.md`); UI сейчас честно сообщает об ограничении.
- Карты подписей в `lib/auditLabels.js` — снимок registry на 2026-08-22
  (87 + 7 событий). Новое backend-событие без подписи роняет
  `auditLabels.test.js`, а не утекает в интерфейс сырым кодом; при расширении
  registry карту нужно дополнять в той же задаче.

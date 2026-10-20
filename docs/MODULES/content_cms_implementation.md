# CMS редактируемого контента витрины — реализация и инструкция

> **Статус (2026-08-28): паттерн реализован дважды.**
> `banner_slides` — слайды баннера Hero (2026-08-27, коммит `91a3f04`);
> `service_cards` — карточки услуг страницы `/services` (2026-08-28).
> Ниже — фактическая общая архитектура, различия двух реализаций и
> пошаговая инструкция «как добавить третий модуль».

Пофичные handoff'ы: `docs/HANDOFFS/2026-08-27-hero-banner-cms-complete.md`,
`docs/HANDOFFS/2026-08-28-service-cards-cms-complete.md`.

---

## 1. Что это и когда применять

Паттерн решает один повторяющийся класс задач: **текстово-визуальный блок
публичной витрины, вшитый в JSX, который должен редактироваться
admin/supervisor без коммита.**

Признаки задачи, для которой паттерн подходит:

- контент — плоский список однотипных блоков (слайд, карточка, пункт);
- редактируют штатные роли (admin + supervisor), не автор-пользователь;
- читает — анонимный посетитель публичной страницы;
- нет связей с другими сущностями (никаких входящих FK), нет модерации,
  нет версионирования, нет привязки к автору.

**Когда НЕ применять:** контент с автором и жизненным циклом публикации
(`articles`/`news` — там soft delete, `published_at`, теги, категории),
пользовательский контент (`diary_entries`, `questions_answers`) и всё, на
что могут ссылаться другие таблицы.

---

## 2. Общая архитектура

### 2.1 Backend — 5 файлов + миграция + 5 audit-событий

```
app/<module>/
  __init__.py            пустой (без него модуль не импортируется)
  schemas.py             4 Pydantic-схемы
  storage.py             весь SQLAlchemy + запись audit
  service.py             транзакции, без FastAPI/HTTP
  routes_supervisor.py   CRUD, admin+supervisor
  routes_public.py       чтение активных, без auth
```

Разделение ответственности — стандартное для проекта (`mindcare_api/CLAUDE.md`),
с одной особенностью: **audit пишется в `storage.py`**, рядом с мутацией и в
той же сессии, а не в service — иначе success-событие могло бы разойтись с
фактом изменения строки.

**Четыре схемы, а не две:**

| Схема | Роль |
|---|---|
| `<X>Create` | вход POST; обязательные поля обязательны |
| `<X>Update` | вход PATCH; **все** поля `Optional` |
| `<X>Read` | ответ admin/supervisor: `id`, `uuid`, все поля, `image_url`, timestamps |
| `Public<X>Read` | ответ публичного эндпоинта: **только отображаемые поля** |

`Public<X>Read` не наследуется от `<X>Read` намеренно: наследование сделало
бы утечку служебного поля в публичный ответ вопросом невнимательности при
следующей правке. Ограничение состава проверяется тестом на точный набор
ключей ответа.

### 2.2 Транзакция и audit

```python
# service.py — владелец транзакции
with SessionLocal() as db:
    obj = storage.get_<x>(id, db)
    if obj is None:
        raise <X>Error("...", status_code=404)
    actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
    result = storage.update_<x>(obj, updates, db, actor=actor, context=ctx)
    db.commit()          # единственный commit
```

`storage` только стейджит (`db.add`/`setattr`/`db.flush`) и вызывает
`record_event(...)`; `commit`/`rollback` принадлежат вызывающему — audit-строка
и мутация фиксируются одним commit, частичного состояния не бывает.

Перед любой мутацией — fail-closed guard:

```python
def _require_actor(actor, context) -> None:
    """audit требует подтверждённый user-actor + context (строит service)."""
    if (not isinstance(actor, Actor) or actor.kind != "user"
        or not isinstance(actor.user_id, int) or isinstance(actor.user_id, bool)
        or actor.user_id <= 0 or not isinstance(actor.role, str) or not actor.role
        or not isinstance(context, RequestContext)):
        raise RuntimeError("<module> audit requires authenticated user actor context")
```

Смысл: модуль физически не может записать изменение без опознанного автора —
даже если кто-то вызовет storage напрямую из скрипта.

### 2.3 Пять событий, а не одно на все изменения

```python
_audit_ok("<x>_created",     {"supervisor", "admin"}, "<x>"),
_audit_ok("<x>_updated",     {"supervisor", "admin"}, "<x>"),
_audit_ok("<x>_activated",   {"supervisor", "admin"}, "<x>"),
_audit_ok("<x>_deactivated", {"supervisor", "admin"}, "<x>"),
_audit_ok("<x>_deleted",     {"supervisor", "admin"}, "<x>"),
```

`is_active` — семантически значимый переход («блок исчез с сайта» / «появился
обратно»), поэтому вынесен в отдельные события и не тонет в generic
`updated`. Следствия, зафиксированные тестами:

- **combined PATCH** (обычные поля + `is_active`) пишет **две** непересекающиеся
  строки: `updated` и `activated`/`deactivated`;
- **identical PATCH** (нет реального diff ни в одном поле) — полный no-op: без
  мутации ORM, без сдвига `updated_at`, без audit-строки;
- реактивация — это `activated`, а **не** повторный `created`.

Реализация в `storage.update_<x>` — раздельный подсчёт `non_status_diff` и
`is_active_changed` до применения изменений.

### 2.4 Удаление — физическое

`DELETE` удаляет строку (`db.delete`), а не проставляет `deleted_at`. Обосновано
для этого класса таблиц: **входящих FK нет**, поэтому удаление не оставляет
висящих ссылок — в отличие от `categories`/`meeting_types`, где выбран soft
delete через `is_active` (ADR-014). Обратимое «временно скрыть» здесь и так
есть — это `is_active`. `record_event("<x>_deleted")` пишется **до**
`db.delete`, пока `id` ещё доступен; на фронте действие подтверждается диалогом.

### 2.5 Frontend — 4 файла

```
api/<module>.api.js                 тонкие обёртки над apiFetch
pages/<page>/components/use<X>.js   публичный хук: { items, loading }
pages/supervisor/<X>Page.jsx        CRUD-страница (admin + supervisor)
pages/supervisor/<X>Page.module.css
```

Публичный хук — минимальный: загрузка при монтировании, `catch` молча (витрина
не показывает посетителю ошибку загрузки — она показывает fallback), флаг
`cancelled` против гонки ответов.

**Fallback в коде обязателен.** Компонент-потребитель держит константу с теми
же данными, что залиты сидом:

```js
const items = (!loading && fetched.length > 0) ? fetched : DEFAULT_ITEMS;
```

Показывается, пока идёт запрос, при недоступном API и при пустой выборке
(чистая БД после деплоя, все строки отключены). Осознанное дублирование
«код + БД»: страница-витрина никогда не должна показывать пустое место.

CRUD-страница — один компонент на оба кабинета, роль приходит пропом
`cabinetRole` и влияет **только на текстовую метку**; доступ обеспечивают
`RoleRoute` (на layout) и `require_role` (на роутере) — фронт границей доступа
не является.

### 2.6 Доступ

```python
router = APIRouter(
    prefix="/supervisor/<module>",
    dependencies=[Depends(require_role("admin", "supervisor"))],
)
```

Роутер-level guard (нельзя забыть на новом эндпоинте) + в каждом write-хендлере
`resolve_role_or_403(current_user, allowed={"admin","supervisor"},
preferred="supervisor")` — он нужен не для доступа, а чтобы получить **точную
acting-роль** для `audit.actor.role`. Путь `/api/supervisor/*`, а не
`/api/admin/*`, даже при доступе admin — по ADR-015.

### 2.7 Картинка — переиспользование media, без нового загрузчика

Своего файлового хранилища у модуля нет. Схемы принимают `image_uuid`
(строка), `storage._resolve_image()` резолвит его в FK `image_id` через
`media_files` (только `is_active`), а на выход отдаёт `image_url` + `image_uuid`.
Невалидный/несуществующий UUID → `None`, а не 422: картинка опциональна.

FK — `ON DELETE SET NULL`: удаление файла из медиатеки не должно удалять
контентный блок.

На фронте — существующий `ImageUpload` (`value = {uuid, url} | null`,
`onChange`), заливка через `POST /api/media/upload`. В payload уходит только
`image_uuid`; `url` сервер подставляет сам.

---

## 3. Две реализации: что общее, что разное

| | `banner_slides` | `service_cards` |
|---|---|---|
| Потребитель | `Hero.jsx` (4 публичные страницы) | `ServicesSlider.jsx` → `ServiceCard.jsx` |
| Страницы | несколько, поле `placement` (`home`/`services`/`about`/`materials`) | одна, поля `placement` нет |
| Обязательные поля | `title` | `title`, `description` |
| Опциональный текст | `label`, `highlight`, `sub` | — |
| Список пунктов | нет | `benefits` — JSONB `list[str]` |
| Картинка | опциональна | опциональна |
| CTA | `link_url` → «Подробнее» | `link_url` → «Записаться» |
| Явный `null` на NOT NULL в PATCH | **не отклоняется** (известный пробел) | **422 до мутации** |
| Миграции | две (`0531e37e2f95` + `72bfade01121` добавила `link_url`) | одна (`d14143842079`, сразу все поля) |
| Frontend-тесты CMS-страницы | нет | нет |

**`placement`** (только у слайдов) — обычный `String(50)`, допустимые значения
задаёт `Literal` в схемах. Новая страница-получатель = правка кода, **без
миграции схемы**; data-миграция нужна лишь тогда, когда у страницы уже есть
статичный текст для переноса (§4.1). Заводить `placement` «на будущее» в новом
модуле не нужно: у карточек услуг единственная страница, и поле было бы
преждевременной абстракцией.

На 2026-08-28 у слайдов четыре страницы — `home`, `services`, `about`,
`materials`; статичных баннеров на публичных страницах не осталось.

**Подключение ещё одной страницы к существующему модулю** (6 шагов, все —
правка кода; порядок неважен, но пропуск любого даёт тихую деградацию, а не
ошибку):

1. значение в `Literal` (`app/banner_slides/schemas.py::BannerPlacement`);
2. опция в `PLACEMENT_OPTIONS` (`BannerSlidesPage.jsx`) — она же питает фильтр
   списка, select формы и сортировку списка по странице;
3. `DEFAULT_SLIDES_BY_PLACEMENT` в `Hero.jsx` — иначе страница с пустой
   выборкой покажет fallback главной;
4. `ARIA_LABEL_BY_PLACEMENT` там же — иначе баннер представится скринридеру
   «Баннер главной страницы»;
5. `<Hero placement="…" />` на самой странице вместо статичного блока;
6. комментарий-перечисление в модели (`content.py`) — он единственное место,
   где значения видны при чтении схемы БД.

Шаги 3 и 4 — именно те, что теряются при копировании: код собирается и тесты
проходят, а дефект виден только на живой странице.

**`benefits` как JSONB** (только у карточек) — выбран вместо отдельной таблицы
(не нужна ни фильтрация, ни сортировка внутри списка) и вместо `TEXT` с
разделителем (десериализация была бы на совести каждого читателя). psycopg2
мапит колонку в `list[str]` без ручной сериализации. В форме редактируется как
textarea, конвертация — только на границе отправки:

```js
benefits: benefitsText.split('\n').map(s => s.trim()).filter(Boolean)   // → payload
benefitsText: (item.benefits || []).join('\n')                          // ← открытие формы
```

**NOT NULL guard** (только у карточек, §4.1 их handoff'а) — `<X>Update` не
может запретить `null` на уровне Pydantic (все поля `Optional`, иначе схема не
отличала бы «не трогать» от «стереть»), поэтому service отсекает явный `null`
на NOT NULL-поля **до** открытия транзакции:

```python
_NOT_NULLABLE_FIELDS = {"title", "description", "benefits", "display_order", "is_active"}
for f in _NOT_NULLABLE_FIELDS:
    if f in updates and updates[f] is None:
        raise <X>Error(f"Поле «{f}» не может быть пустым.", status_code=422)
```

Без него был бы 500 на constraint violation. В `banner_slides` этого guard'а
нет — известный пробел, не переносился, чтобы не трогать чужой модуль вне
объёма задачи. **В новом модуле guard делать сразу.**

---

## 4. Перенос вшитого контента: сид в миграции

Оба модуля переносили существующий хардкод из JSX. Правило одно: **`op.bulk_insert`
в `upgrade()` той же миграции, что создаёт таблицу.** Не в `seed.py`.

Причина: `seed.py` идемпотентно досоздаёт справочные данные при каждом старте.
Контент витрины редактируемый — если админ удалил блок, seed не должен
возвращать его при следующем рестарте. `bulk_insert` в `upgrade()` выполняется
ровно один раз.

Тексты при переносе **не редактируются** — после миграции сайт визуально
идентичен состоянию до неё; это проверяемое свойство, и оно теряется, если
попутно «немного улучшить формулировки».

Данные при этом остаются и в коде — как fallback (§2.5). Дублирование
осознанное и отмечено комментарием в обоих местах.

### 4.1 Отдельная data-миграция (перенос без создания таблицы)

Если контент подключается к **уже существующему** модулю — например, ещё одна
страница для `banner_slides`, — таблицы создавать не нужно, а перенести текст
всё равно надо. Тогда это самостоятельная ревизия, состоящая только из
`bulk_insert` (пример: `27b44fcf4865_seed_about_materials_banner_slides`).

Особенность такой ревизии — **`downgrade()` не может «удалить последние N
вставленных строк»**: между накатом и откатом админ мог добавить свои записи
того же вида. Удалять нужно по устойчивому признаку переносимого набора
(у слайдов это `placement`):

```python
op.execute(
    sa.text("DELETE FROM banner_slides WHERE placement IN :placements")
    .bindparams(sa.bindparam("placements", _PLACEMENTS, expanding=True))
)
```

Такой `downgrade` удалит и пользовательские строки этих страниц — это
корректно (страница возвращается к статичному виду), но должно быть явно
описано в docstring ревизии, а не подразумеваться. Roundtrip
`upgrade → downgrade → upgrade` стоит прогнать на dev-БД: `expanding`
bindparam — нечастый приём, ошибка в нём проявится только при откате.

> **ЛЮБАЯ новая ревизия — включая чисто data-миграцию — двигает alembic head,
> а значит требует правки `CURRENT_HEAD` в
> `tests/test_audit_created_index_model.py`.** Константа не имеет отношения ни
> к audit, ни к содержимому миграции: тест проверяет, что head ровно один и
> он ожидаемый. Забыть легко именно на data-миграции («я же не менял схему»),
> и падение приходит в конце 20-минутного полного прогона, в файле, который
> с задачей никак не связан. Это тот же класс ловушки, что и счётчики
> REGISTRY (§6).

**Соответствие полей проверять глазами.** Статичный компонент и модель слайда
описывают текст по-разному: у `PageHero` было `eyebrow/title/sub`, у слайда —
`label/title/highlight/sub`. Двухстрочный заголовок с жёстким `<br />`
естественно ложится в пару `title` + `highlight`, но `highlight` в `Hero`
рендерится курсивом акцентным цветом — то есть перенос «один в один по
смыслу» меняет вид. Это решение уровня владельца задачи, а не механическая
подстановка: либо принять акцент, либо положить весь заголовок в `title` и
потерять жёсткий перенос строки.

---

## 5. Как добавить третий модуль — чек-лист

**Backend:**

1. Модель в `app/db/models/content.py` (рядом с `BannerSlide`/`ServiceCard`) —
   `id`, `uuid`, контентные поля, `image_id` (FK `media_files`, ON DELETE SET
   NULL), `link_url`, `display_order`, `is_active`, `created_at`, `updated_at`.
   Экспорт в `app/db/models/__init__.py` (импорт + `__all__`).
2. Миграция: `create_table` + `bulk_insert` переносимого контента.
   `down_revision` — **перепроверить `alembic heads` прямо перед созданием
   файла**, а не брать из документации.
3. `app/<module>/` — 5 файлов + пустой `__init__.py`. Копировать структуру
   `app/service_cards/` (в ней есть NOT NULL guard; в `banner_slides` его нет).
4. `app/main.py` — импорт обоих роутеров (`# noqa: E402`) + два
   `app.include_router(..., prefix="/api")`.
5. `app/audit/registry.py` — 5 событий `_audit_ok(...)` с `entity_type="<x>"`.
6. **Синхронизировать счётчики REGISTRY** — см. §6, это самый пропускаемый шаг.
7. Тесты: unit по схемам + integration по образцу
   `tests/integration/test_supervisor_service_cards_api.py` (24 теста:
   роли · валидация · NOT NULL guard · CRUD+картинка · round-trip списка ·
   4 сценария audit-семантики · публичный allowlist полей · удаление).
8. `mindcare_api/CLAUDE.md`: строка в таблице миграций (новый head), строка в
   «Ключевые таблицы», счётчики событий.

**Frontend:**

9. `api/<module>.api.js`, публичный хук `use<X>.js`.
10. Компонент-потребитель: подключить хук, переименовать хардкод-массив в
    `DEFAULT_*` и оставить как fallback. Если список приходит из **публичной**
    схемы (без `id`) — ключ React брать не по `card.id` (он `undefined`), а по
    индексу: порядок стабилен, backend сортирует по `display_order`.
    Если у компонента есть эффект, зависящий от длины списка (стрелки
    слайдера, пагинация) — добавить `items.length` в его зависимости, иначе он
    не пересчитается после асинхронной подгрузки.
11. `pages/supervisor/<X>Page.{jsx,module.css}` — копия `ServiceCardsPage`.
12. `app/router.jsx` — импорт + два роута (`/admin/...` и `/supervisor/...`) с
    `cabinetRole`.
13. Навигация: `features/admin/AdminLayout.jsx` — пункт в группе «Контент»
    (`CRUMB_LABELS` там строится автоматически); `pages/supervisor/
    SupervisorLayout.jsx` — пункт **и отдельно** строка в `CRUMB_LABELS`
    (этот layout не автогенерирует). Имя иконки сверять со списком `case` в
    `src/components/Icon/Icon.jsx`: у неизвестного имени `default` возвращает
    `null`, иконка молча исчезает без ошибки и предупреждения. Проверка:
    ```bash
    grep -rhoE 'Icon name="[a-z-]+"' src --include="*.jsx" | sed 's/.*"\(.*\)"/\1/' | sort -u > /tmp/used
    grep -oE "case '[a-z0-9-]+'" src/components/Icon/Icon.jsx | sed "s/case '//;s/'//" | sort -u > /tmp/declared
    comm -23 /tmp/used /tmp/declared     # пусто = все иконки существуют
    ```

**Проверка:**

14. `python -m compileall`, `alembic upgrade head`, `pytest tests/` **полностью**
    (не только новые файлы — см. §6), `npm run lint`, `npm run build`,
    `npm test -- --watchAll=false`, `npm run test:contrast` (если тронуты цвета).
15. Демо-стенд не подхватывает изменения сам: `alembic upgrade head` на его БД
    → `systemctl restart mindcare-demo.service`. Без рестарта фронт получает
    HTML SPA-фолбэка вместо JSON и падает с `JSON.parse: unexpected character`.

---

## 6. Ловушка: добавление audit-событий ломает тесты в чужих файлах

Пять новых событий сдвигают глобальные счётчики REGISTRY (при добавлении
`service_cards`: `99 → 104`, `AUDIT_LOG 92 → 97`). Эти числа захардкожены
**в 12 файлах**, и `grep "== <старое число>"` находит не все:

| Как выражено | Файлы |
|---|---|
| `len(REGISTRY) == N` | `test_audit_registry.py` (2 места), `test_appointments_audit_unit.py`, `test_appointments_failure_audit_unit.py`, `test_content_test_consent_audit_unit.py`, `test_data_change_denylist_unit.py` (2 места), `test_group_audit_unit.py`, `test_maintenance_audit_unit.py`, `test_schedule_audit_unit.py` |
| кортеж `(7, 92, 99)` | `test_audit_logs_viewed_event_unit.py` |
| `len(audit_events) == 92` через ответ `/admin/audit/options` | `integration/test_admin_audit_api.py`, `test_audit_admin_options_unit.py` |
| константа `CURRENT_HEAD` (номер последней миграции, не событий) | `test_audit_created_index_model.py` |

Плюс список имён событий в `_EXPECTED_AUDIT_LOG_EVENTS`
(`test_audit_registry.py`) и счётчики в `mindcare_api/CLAUDE.md`.

Последние три строки таблицы grep'ом по старому числу событий **не находятся**.
Единственный надёжный способ — полный `pytest tests/` до коммита.

---

## 7. Известные пробелы

- **NOT NULL PATCH guard отсутствует в `banner_slides`** — явный `null` на
  `title` даст 500 вместо 422. В `service_cards` закрыто.
- **Frontend-тестов на CMS-страницы нет** ни у одного из двух модулей
  (`BannerSlidesPage`, `ServiceCardsPage`, публичные хуки, api-слой). Backend
  покрыт полностью. Асимметрия осознанная, но при третьем модуле стоит
  пересмотреть — паттерн уже устоялся, тест на конвертацию textarea↔массив и
  на fallback был бы дешёвым.
- **`ServiceCardsPage.module.css` — копия `BannerSlidesPage.module.css`.**
  Третий модуль означает третью копию; на этом шаге таблицу/модалку/confirm-
  диалог стоит вынести в shared, а не копировать снова.
- **Alt-текст картинок не редактируется** — изображения в обоих модулях
  декоративные (`aria-hidden`). Содержательная картинка потребует отдельного
  поля и пересмотра `aria-hidden`.

# Карточки услуг (`/services`) как CMS — модуль `service_cards`

**Дата:** 2026-08-28
**Область:** backend (`mindcare_api/`) + frontend (`mindcare_web/`)
**Общий паттерн обоих CMS-модулей и инструкция «как добавить третий»:**
`docs/MODULES/content_cms_implementation.md`.

**Опирается на:** Hero CMS (`banner_slides`, основная работа 2026-08-27,
коммит `91a3f04`) — `service_cards` полностью зеркалит его архитектуру;
см. `2026-08-27-hero-banner-cms-complete.md`. Расхождения banner↔cards
описаны явно везде, где они есть. Решение по decorative-затемнению картинки
карточки — отдельная заметка
`2026-08-28-decorative-overlay-dark-theme-color-tokens-note.md`.

---

## 1. Зачем

Карточки услуг на `/services` были захардкожены в JSX (`ServicesSlider.jsx`,
константа `SERVICES`) — редактировать текст, добавлять/убирать услугу или
менять порядок мог только разработчик через коммит. Кнопка «Записаться» на
карточке к тому же ничего не делала (не было ни `href`, ни `onClick`).

Задача переносит карточки в БД и даёт admin+supervisor полноценный CRUD —
по образцу уже готового баннера Hero, чтобы не изобретать вторую архитектуру
для той же задачи «редактируемый контент главных страниц».

---

## 2. Что сделано

Новый backend-модуль `app/service_cards/` — полное зеркало `banner_slides` с
тремя содержательными отличиями:

| | `banner_slides` | `service_cards` |
|---|---|---|
| Страница-получатель | несколько (`placement`: home/services) | одна (`/services`), поля `placement` нет вообще |
| Список пунктов | нет | `benefits` — JSONB-массив строк, редактируется как textarea (по строке на пункт) |
| PATCH на NOT NULL-поле | явный `null` не отклоняется отдельно (латентный пробел) | **явный `null` на `title`/`description`/`benefits`/`display_order`/`is_active` → 422 до мутации** |
| `description` | опциональна (`sub`) | обязательна |

Общее с баннером (без изменений в подходе): `image_id` — опциональная
картинка через `ImageUpload`/`media_files`; `link_url` — опциональная ссылка
кнопки («Записаться» не рендерится без неё, как CTA в `Hero.jsx`);
`display_order`/`is_active`; физическое (не soft) удаление — у таблицы нет
входящих FK; `is_active` пишет отдельные audit-события `activated`/
`deactivated`, не смешиваясь с generic `updated`; identical PATCH — no-op без
мутации/audit/сдвига `updated_at`.

Исходные 5 карточек (бывший хардкод `SERVICES`) перенесены в БД дословно
начальной миграцией `d14143842079` — те же тексты, что раньше были в JSX.
`ServicesSlider.jsx` держит их же как `DEFAULT_SERVICE_CARDS` — frontend-
fallback на случай пустой/недоступной таблицы, по тому же принципу, что
`DEFAULT_SLIDES_BY_PLACEMENT` в `Hero.jsx`.

Admin/supervisor получили отдельный пункт меню «Карточки услуг»
(`/admin/service-cards`, `/supervisor/service-cards`) — не объединён с
«Баннер», это разные сущности с разной формой редактирования.

---

## 3. Изменённые и новые файлы

**Backend, новые:**
```
app/service_cards/
  __init__.py · schemas.py · storage.py · service.py
  routes_public.py · routes_supervisor.py
alembic/versions/d14143842079_add_service_cards.py
tests/test_service_cards_schema_unit.py               (17 тестов)
tests/integration/test_supervisor_service_cards_api.py (24 теста)
```

**Backend, изменённые:**
```
app/db/models/content.py       — класс ServiceCard, импорт JSONB
app/db/models/__init__.py      — экспорт ServiceCard
app/main.py                    — регистрация двух роутеров
app/audit/registry.py          — 5 событий service_card_*
CLAUDE.md                      — счётчики REGISTRY, таблица миграций,
                                  таблица «Ключевые таблицы»
```

**Backend, задетые побочным эффектом добавления событий в REGISTRY (см. §4.2):**
```
tests/test_audit_registry.py · test_appointments_audit_unit.py
tests/test_appointments_failure_audit_unit.py · test_audit_logs_viewed_event_unit.py
tests/test_content_test_consent_audit_unit.py · test_data_change_denylist_unit.py
tests/test_group_audit_unit.py · test_maintenance_audit_unit.py
tests/test_schedule_audit_unit.py · integration/test_admin_audit_api.py
tests/test_audit_admin_options_unit.py · test_audit_created_index_model.py
```

**Frontend, новые:**
```
api/serviceCards.api.js
pages/services/components/useServiceCards.js
pages/supervisor/ServiceCardsPage.jsx
pages/supervisor/ServiceCardsPage.module.css
```

**Frontend, изменённые:**
```
pages/services/components/ServiceCard.jsx        — картинка, benefits-гвард, CTA-ссылка
pages/services/components/ServiceCard.module.css — .hasImage, .cardBtn как <a>
pages/services/components/ServicesSlider.jsx      — API-хук + fallback, фикс стрелок
app/router.jsx                                     — 2 роута service-cards
features/admin/AdminLayout.jsx                     — пункт «Карточки услуг»
pages/supervisor/SupervisorLayout.jsx              — пункт + crumb
```

---

## 4. Ключевые инварианты

### 4.1 NOT NULL guard в PATCH — новое по сравнению с banner_slides

`ServiceCardUpdate` в Pydantic не запрещает `null` на `title`/`description`/
`benefits` (все поля `Optional[...]`, иначе схема не отличала бы «не трогать»
от «стереть» — тот же принцип, что и у баннера с `link_url`). Но эти три поля
(плюс `display_order`/`is_active`) в БД — NOT NULL, и слепой `setattr(card,
"title", None)` дал бы 500 на constraint violation вместо осмысленного
ответа клиенту.

`service.update_service_card` проверяет `_NOT_NULLABLE_FIELDS` ДО открытия
транзакции и открытия сессии — явный `null` на любое из них даёт `422`
раньше любой мутации, без audit-строки. У `banner_slides.title` та же
теоретическая дыра есть и сегодня (не исправлялась — чужой модуль вне
объёма этой задачи), задокументирована как известный пробел в
`mindcare_api/CLAUDE.md` рядом с правилом «не отправлять явный null для NOT
NULL-поля».

### 4.2 Регистрация нового audit-события задевает больше файлов, чем ожидается — 12, не 9

Первый прогон backend-набора после добавления 5 `service_card_*` событий
(99→104, `AUDIT_LOG` 92→97) упал на **трёх** местах, которые не попали под
`grep "== 99"` при планировании: `tests/integration/test_admin_audit_api.py`
и `tests/test_audit_admin_options_unit.py` сравнивали `audit_events` c
захардкоженным `92` напрямую (не через общий `REGISTRY`-счётчик), а
`tests/test_audit_created_index_model.py` держит отдельную константу
`CURRENT_HEAD` для проверки единственности alembic-head — она не про
количество событий вообще, а про номер последней миграции, и тоже требует
правки при каждой новой ветке миграций.

**Практический вывод на будущее:** при добавлении нового набора audit-событий
недостаточно grep'нуть `== <N>` по всему `tests/` — нужно ещё явно
проверить: (а) любые прямые сравнения с числом событий помимо
`len(REGISTRY)` (например через `/admin/audit/options` response), (б)
`CURRENT_HEAD`-подобные константы в тестах, привязанные к последней
alembic-ревизии. Полный прогон `pytest tests/` — единственный надёжный
способ поймать оба класса до коммита.

### 4.3 `benefits` — JSONB, не M:N и не денормализованная строка

Список пунктов хранится как `JSONB` (`default=list`), а не отдельной
таблицей `service_card_benefits` (не нужна ни фильтрация, ни сортировка
внутри списка) и не как `TEXT` с ручным разделителем (десериализация была
бы на совести каждого читателя). `_card_to_dict` отдаёт `card.benefits or
[]` — psycopg2 сам мапит JSONB-колонку в Python `list[str]`, round-trip
проверен отдельным integration-тестом (`test_benefits_round_trip_preserves_order`)
на сохранение порядка.

Форма админки хранит сырой текст textarea в `form.benefitsText`, конвертация
в массив — только на границе отправки:
`benefitsText.split('\n').map(s => s.trim()).filter(Boolean)`. При открытии
на редактирование — обратное преобразование `(item.benefits || []).join('\n')`.

### 4.4 Демо/dev-процесс не подхватывает новый код и схему сам собой

FastAPI при старте **не** применяет миграции — только логирует WARNING, если
БД отстаёт от head (см. `mindcare_api/CLAUDE.md`). В процессе этой задачи
демо-стенд (`mindcare-demo.service`) сначала отдавал `JSON.parse:
unexpected character…` на новые `/api/service-cards` и `/admin/service-cards`
— процесс работал со старым кодом (не видел `app/service_cards/`), а SPA
fallback-роут возвращал `index.html` вместо 404 на несуществующий API-путь,
из-за чего фронт получал HTML вместо JSON.

Порядок, который реально нужен после такой правки: `alembic upgrade head` на
БД демо-стенда (та же `DATABASE_URL`, что использует сервис — не
`TEST_DATABASE_URL`) → `systemctl restart mindcare-demo.service`. Оба шага
выполнены; `journalctl` подтвердил `Schema is up to date (revision:
d14143842079)` и чистый рестарт. Проблема воспроизводилась ещё раз сразу
после первого рестарта (устаревший кэш статики SPA в браузере) — после
повторной проверки пользователем подтверждено, что `/services` и обе
admin/supervisor страницы работают штатно.

---

## 5. Доступность

- Кнопка «Записаться» стала `<a href>` вместо мёртвой `<button>` без
  обработчика — семантически корректнее (это переход, а не действие на
  странице) и рендерится только когда есть `link_url` (нет «висящей»
  недоступной кнопки).
- Список преимуществ (`<ul>`) не рендерится вовсе при пустом `benefits` —
  не оставляет пустой `<ul>` без `<li>`.
- Цвета — только токены (`--espresso-rgb` в `.cardBtn`) кроме одного
  задокументированного фиксированного decorative rgba (см. отдельный
  handoff по цветовым токенам).

---

## 6. Shared UI и feature-specific

**Переиспользовано:** `Button`, `Badge`, `Checkbox`, `ImageUpload`,
`components/Modal/Modal`, `Icon`, `shared/lib/roles` (`ROLE_LABELS`),
`api/client.js` (`apiFetch`) — тот же набор, что и у `BannerSlidesPage.jsx`,
без нового локального UI-контрола.

**Feature-specific:** структура `ServiceCardsPage.module.css` — прямая
адаптация `BannerSlidesPage.module.css` (общая таблица/модалка/confirm-
dialog система); не выносилась в shared, т.к. и баннер её не выносил —
рефакторинг общего паттерна двух похожих admin-страниц не входил в объём.

---

## 7. Проверки

| Проверка | Результат |
|---|---|
| Backend `python -m compileall` | чисто |
| `alembic upgrade head` (dev БД) | применена, 5 строк сида подтверждены |
| Backend unit — `test_service_cards_schema_unit.py` | 17 passed |
| Backend integration — `test_supervisor_service_cards_api.py` | 24 теста, в общем прогоне |
| Backend полный набор — `pytest tests/` (изолированная БД) | **2744 passed, 69 skipped, 0 failed** (после починки §4.2) |
| Frontend `npm run lint` | чисто |
| Frontend `npm run build` | Compiled successfully (+1.63 kB js, +621 B css gzip) |
| Frontend `npm test -- --watchAll=false` | 1075 passed, 81 suites |
| `npm run test:contrast` | 254 проверки, 0 нарушений |
| Демо-стенд (`mindcare-demo.service`) | перезапущен, схема на `d14143842079`, `/services` и `/api/service-cards` — 200 |
| **End-to-end на живом стенде** | подтверждено фактическим использованием: supervisor создал через админку карточку «Наши новости» с загруженной картинкой (`image_id=4`), ссылкой `/news`, двумя пунктами `benefits` и `display_order=-1` (встала первой в слайдере) |
| **Audit на живом стенде** | 4 строки по `entity_id=6`: ровно один `service_card_created` + три `service_card_updated` (по числу правок), `user_role=supervisor`, `outcome=success`; ложных и дублирующих событий нет |

---

## 8. Что намеренно не сделано

- **Новых frontend-тестов на CMS-модуль не добавлено** (`ServiceCardsPage`,
  `useServiceCards`, `serviceCards.api.js`) — следуем прецеденту:
  `banner_slides` не имеет ни одного frontend-теста на свою CMS-часть с
  момента внедрения (только `Hero.test.jsx` про сам компонент-потребитель).
  Осознанная асимметрия с backend (там полное unit+integration покрытие) —
  не молчаливый пропуск.
- **`placement` для карточек услуг не заведён** — единственная страница-
  получатель, поле было бы преждевременной абстракцией под гипотетическое
  будущее использование карточек на другой странице.
- **`banner_slides.title` NOT NULL PATCH guard не добавлен** (см. §4.1) —
  тот же осознанный выбор: не трогать чужой модуль ради симметрии.
- Backend auth/session/RBAC, seed, package-файлы — не изменялись.
  Commit/push не выполнялись.

---

## 9. Открытые вопросы

Ни одного блокирующего. Ручной smoke на живом демо-стенде выполнен
(см. §7), проблема с `JSON.parse` (SPA-фолбэк вместо JSON, пока бэкенд-процесс
работал со старым кодом) закрыта рестартом сервиса.

Замечания на будущее, не требующие действий сейчас:

- **`display_order` допускает отрицательные значения** — supervisor
  воспользовался `-1`, чтобы поставить карточку первой, и это сработало
  корректно (сортировка `order_by(display_order, id)`). Атрибут `min={0}` у
  поля формы — только подсказка спиннера, нативной валидацией форма не
  пользуется; backend ограничений на знак не имеет. Поведение полезное, но
  не задокументировано в UI — при желании стоит убрать `min={0}` или
  подписать поле.
- **Иконка «плюс» на кнопке «Добавить»** не рендерилась (в `Icon.jsx`
  отсутствовал `case 'plus'`, `default` возвращает `null`). Обнаружено при
  самопроверке и исправлено — правка чинит разом 7 мест в 5 файлах, включая
  предсуществующие `MeetingTypesPage`, `GroupSessionsPage`, `SchedulePage`,
  `SettingsPage`, `BannerSlidesPage`.

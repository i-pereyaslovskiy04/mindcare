# Баннер-слайдер Hero — CMS: перенос вшитых слайдов в БД, картинки на слайдах

**Дата:** 2026-08-27 (основная работа, коммит `91a3f04`) · доработки 2026-08-28 (§4)
**Область:** frontend (`mindcare_web/`) + backend (`mindcare_api/`)
**Общий паттерн обоих CMS-модулей и инструкция «как добавить третий»:**
`docs/MODULES/content_cms_implementation.md`.

**Смежные документы:** `2026-08-28-service-cards-cms-complete.md` (карточки
услуг — тот же паттерн CMS, применённый повторно),
`2026-08-28-decorative-overlay-dark-theme-color-tokens-note.md` (решение по
decorative-затемнению карточки, отличное от принятого здесь).

Документ описывает баннер целиком: изначальный перенос вшитых в JSX слайдов
в БД, механику картинок на слайдах и две доработки, сделанные 2026-08-28.

---

## 1. Зачем

Слайды баннера главной страницы были захардкожены в `Hero.jsx` (массив из
трёх объектов прямо в JSX) — сменить текст или порядок мог только
разработчик через коммит. На `/services` при этом стоял отдельный статичный
`PageHero` со своим текстом — вторая реализация той же сущности, которую
тоже правили только кодом.

Задача: перенести содержимое в БД, дать admin+supervisor CRUD и сделать
`Hero` переиспользуемым для нескольких страниц вместо копий-компонентов.

---

## 2. Перенос вшитых слайдов в БД

### 2.1 Что именно перенесено

Миграция `0531e37e2f95_add_banner_slides` создаёт таблицу `banner_slides`
и **тем же файлом** (`op.bulk_insert`) заливает 4 слайда, дословно
перенесённых из кода:

| # | Источник в коде | `placement` | `display_order` |
|---|---|---|---|
| 1 | `Hero.jsx`, слайд «Забота о вашей / душевной гармонии» | `home` | 0 |
| 2 | `Hero.jsx`, слайд «Ты не один / на своём пути» | `home` | 1 |
| 3 | `Hero.jsx`, слайд «Сделай первый / шаг к себе» | `home` | 2 |
| 4 | `Services.jsx`, статичный `PageHero` («Центр психологической помощи ДонГУ») | `services` | 0 |

Тексты не редактировались при переносе — визуально сайт после миграции
идентичен состоянию до неё. Четвёртая строка — это бывший `PageHero`
страницы услуг: его собственный компонент с `/services` убран, вместо него
тот же `Hero` с `placement="services"`.

### 2.2 Почему сид лежит в самой миграции, а не в `seed.py`

Это разовый перенос конкретного существующего контента, а не справочные
данные, которые должны существовать в любой свежей БД. `seed.py`
идемпотентно досоздаёт роли/разрешения при каждом старте; слайды же —
редактируемый пользователем контент: если админ удалит слайд, seed не
должен возвращать его обратно при следующем рестарте. `bulk_insert` в
`upgrade()` выполняется ровно один раз.

### 2.3 Fallback в коде остаётся — осознанно

`Hero.jsx` сохраняет `DEFAULT_SLIDES_BY_PLACEMENT` с теми же текстами:

```js
const slides = (!slidesLoading && fetchedSlides.length > 0)
  ? fetchedSlides
  : defaultSlides;
```

Показывается, пока идёт запрос, при недоступном API и когда в таблице нет
ни одной активной строки этого `placement` (например, сразу после деплоя на
чистую БД или если админ отключил все слайды). Это осознанное дублирование
данных «код + БД»: страница-витрина никогда не должна показывать пустое
место. Тот же принцип позже повторён в `ServicesSlider.jsx`
(`DEFAULT_SERVICE_CARDS`).

### 2.4 `placement` — одна страница = одно значение, расширяется без миграции

Колонка `placement` — обычный `String(50)`, допустимые значения задаёт
`app/banner_slides/schemas.py::BannerPlacement` (`Literal["home",
"services"]`). Добавление новой страницы-получателя — правка кода (значение
в `Literal` + опция в admin-select), **без миграции схемы**. Backend
валидирует значение и на запись, и на публичном чтении (неизвестный
`placement` → 422, а не молчаливо пустой список).

---

## 3. Картинки на слайдах

Опциональная фоновая картинка слайда (`image_id` → FK `media_files`,
загрузка существующим `ImageUpload`) — не просто `background-image`, а три
связанных решения:

### 3.1 Слой картинки — снаружи текстовой колонки

`.heroSlideBg` — `position:absolute; inset:0` **на уровне `.hero`**, а не
внутри `.heroInner`. Причина конкретная: `.heroInner` ограничен шириной
текстовой колонки (~700px), и картинка, вложенная в него, была бы обрезана
по ней вместо полноширинного фона. Кросс-фейд между слайдами — по `opacity`
(0.6s), тем же временем и той же логикой, что у `.heroSlide`, чтобы текст и
фон переключались синхронно.

Путь к файлу приходит из БД и подставляется инлайн CSS-переменной:

```jsx
style={{ '--slide-image': `url("${slide.image_url}")` }}
```

Фоновые слои рендерятся только для слайдов, у которых картинка есть
(`slides.map((slide, i) => slide.image_url && (...))`) — слайд без картинки
не создаёт пустой `div`.

### 3.2 Подложка под текстом — только при наличии картинки

Класс `.hasImage` на `.heroSlide` добавляет полупрозрачную подложку под
текстовым блоком. Он навешивается условно (`slide.image_url ?
styles.hasImage : ''`): без картинки текущий вид баннера не должен меняться
вообще, а поверх произвольного фото читаемость текста иначе зависела бы от
случайного содержимого снимка.

### 3.3 Токен `--hero-bg-rgb` — и исправленный им предсуществующий баг

Затемняющий градиент и подложка используют `rgba(var(--hero-bg-rgb), a)`.
Изначально там был `var(--scrim)` — и это **ломало тёмные, hc- и
a11y-темы**: `--scrim` в тёмных темах всегда чёрный и никак не связан с
`--hero-fg`, а `--hero-fg` в этих темах сам «переворачивается» в тёмный.
Текст на чёрной подложке сливался с ней именно там, где подложка была
нужнее всего.

Введён производный токен `--hero-bg-rgb`, объявленный в базовом `:root`
(`coffee-light.css` — дефолтная тема, от которой наследуются остальные):

```css
--hero-bg:     var(--espresso);
--hero-bg-rgb: var(--espresso-rgb);   /* rgb-версия для полупрозрачных подложек */
--hero-fg:     var(--text-on-dark);
```

`--hero-bg` и `--hero-fg` выводятся из одной пары токенов, поэтому контраст
между ними гарантирован в любой теме: где фон героя переворачивается в
светлый, текст переворачивается в тёмный вместе с ним.

**Про каскад — важно для будущих правок.** `--hero-bg-rgb` физически
объявлен только в четырёх файлах (`coffee-light.css`, `hc-light.css`,
`hc-dark.css`, `a11y.css`), и это **не** значит, что в остальных палитрах
он не работает. `coffee-light.css` — базовый `:root`, остальные палитры
переопределяют токены через `:root[data-theme="…"]`, а `var(--espresso-rgb)`
резолвится лениво, в момент подстановки, по значению текущей темы. То есть
`dongu-dark` получает `--hero-bg-rgb` = свой `--espresso-rgb` (227, 236,
247) автоматически. `hc-*` и `a11y` переопределяют токен явно, потому что
там hero-подложка выводится не из `--espresso`, а из собственных
`--a11y-bg`/фиксированных значений схемы.

### 3.4 CTA-ссылка

Отдельная миграция `72bfade01121_add_banner_slide_link` добавила
`link_url` (`String(2048)`) — опциональную ссылку кнопки «Подробнее».
Свободная строка, не строгий URL-тип: допускает и внутренние относительные
пути (`/services`), и внешние абсолютные ссылки. Кнопка не рендерится, если
`link_url` не задан. У неактивного слайда CTA получает `tabIndex={-1}` —
слайд скрыт по `opacity`/`pointer-events`, но без этого его ссылка всё
равно осталась бы в Tab-обходе.

---

## 4. Доработки 2026-08-28

### 4.1 Сортировка списка по странице (`BannerSlidesPage.jsx`)

Список слайдов в админке показывался в порядке backend (`display_order,
id`), из-за чего слайды `home` и `services` перемежались в одной таблице.
Добавлены `PLACEMENT_ORDER` (индекс страницы в `PLACEMENT_OPTIONS`) и
компаратор `byPlacement`: сначала по позиции страницы (Главная → Услуги),
при совпадении — по `display_order`. Сортировка клиентская, поверх уже
загруженного списка и поверх любого активного фильтра.

Backend не менялся — `get_banner_slides` по-прежнему `order_by(display_order,
id)`. Группировка по странице нужна только для читаемости таблицы админки и
не влияет на порядок показа слайдов на самом сайте.

### 4.2 Скрытие управления при одном слайде (`Hero.jsx`)

Обе стрелки и блок точек-индикатора обёрнуты в `{slides.length > 1 && …}` —
при одном слайде не рендерятся вовсе (условный рендер, не
`display:none`: недостижимые элементы не остаются ни в DOM, ни в Tab-обходе).
Автопрокрутка и раньше не запускалась на одном слайде (`slides.length <= 1`
в `start()`) — теперь элементы управления скрыты согласованно с этим
поведением, а не бездействуют, оставаясь видимыми. Наиболее заметно на
`/services`, где активный слайд ровно один.

---

## 5. Схема и API (справочно)

```
banner_slides: id · uuid · label · title(NOT NULL) · highlight · sub
               image_id (FK media_files, ON DELETE SET NULL) · link_url
               placement(NOT NULL, default 'home') · display_order · is_active
               created_at · updated_at
```

| Метод | Путь | Доступ |
|---|---|---|
| `GET` | `/api/banner-slides?placement=home` | без auth, только активные |
| `GET` | `/api/supervisor/banner-slides?include_inactive=&placement=` | admin+supervisor |
| `POST` / `PATCH` / `DELETE` | `/api/supervisor/banner-slides[/{id}]` | admin+supervisor |

Публичная схема (`PublicBannerSlideRead`) отдаёт только
`label/title/highlight/sub/image_url/link_url` — без `id`, `uuid`,
`placement`, `is_active`, `display_order`.

Audit: 5 событий `banner_slide_created/updated/activated/deactivated/deleted`.
`is_active` выделен в отдельные `activated`/`deactivated` и не смешивается с
generic `updated` (combined PATCH пишет две раздельные строки); identical
PATCH — no-op без мутации, audit и сдвига `updated_at`. Удаление физическое
(у таблицы нет входящих FK), с подтверждением в админке.

---

## 6. Файлы

**Базовый перенос (коммит `91a3f04`, 2026-08-27):**
```
mindcare_api/app/banner_slides/{__init__,schemas,storage,service,
                                routes_public,routes_supervisor}.py
mindcare_api/alembic/versions/0531e37e2f95_add_banner_slides.py   (+ сид 4 слайдов)
mindcare_api/alembic/versions/72bfade01121_add_banner_slide_link.py
mindcare_api/tests/test_banner_slides_schema_unit.py
mindcare_api/tests/integration/test_supervisor_banner_slides_api.py
mindcare_web/src/api/bannerSlides.api.js
mindcare_web/src/pages/home/components/{Hero.jsx,Hero.module.css,useHeroSlides.js}
mindcare_web/src/pages/supervisor/BannerSlidesPage.{jsx,module.css}
mindcare_web/src/pages/services/Services.jsx        (PageHero → Hero placement="services")
mindcare_web/src/styles/tokens/{coffee-light,hc-light,hc-dark,a11y,hc-rules}.css
```

**Доработки 2026-08-28:**
```
mindcare_web/src/pages/home/components/Hero.jsx        — условный рендер стрелок/точек
mindcare_web/src/pages/home/components/Hero.test.jsx   — новый тест + правка существующего
mindcare_web/src/pages/supervisor/BannerSlidesPage.jsx — PLACEMENT_ORDER + byPlacement
```

---

## 7. Тесты и проверки

`Hero.test.jsx` (18 тестов после доработок): автопрокрутка и пауза по
hover/focus раздельно, `prefers-reduced-motion`, fallback при загрузке и при
пустой БД, синхронность фонового слоя картинки с `activeIndex`, класс
`hasImage`, CTA и его `tabIndex` у неактивного слайда, `placement` →
`useHeroSlides` + aria-label. Добавлено 2026-08-28:

- поправлен тест `placement передаётся в useHeroSlides…` — fallback для
  `services` состоит из одного слайда, значит точки-индикаторы теперь не
  рендерятся (`toHaveLength(0)` вместо `1`);
- добавлен `один слайд — стрелки и точки-индикаторы не рендерятся`.

Для `BannerSlidesPage.jsx` frontend-теста нет — CRUD-страница баннера не
покрыта тестами с момента внедрения (осознанная асимметрия с backend, где
покрытие полное: `test_banner_slides_schema_unit.py` + 456-строчный
integration-набор).

| Проверка | Результат |
|---|---|
| `npm test -- --testPathPattern=Hero.test.jsx` | 18 passed (было 16) |
| Полный `npm test -- --watchAll=false` | 1075 passed, 81 suites |
| `npm run lint` | чисто |
| `npm run build` | Compiled successfully |
| `npm run test:contrast` | 254 проверки, 0 нарушений |

---

## 8. Что намеренно не сделано

- **Сортировка списка не перенесена на backend** — презентационная задача
  уровня одной таблицы админки; серверный параметр ради единственного
  потребителя не заводился.
- **`banner_slides.title` NOT NULL PATCH guard** — явный `null` в PATCH на
  NOT NULL-поле здесь по-прежнему не отклоняется отдельной проверкой (даст
  500 на constraint violation вместо 422). В `service_cards` такой guard
  добавлен сразу; в баннер не переносился — отдельная правка вне объёма
  доработок. Зафиксировано как известный пробел.
- **Alt-текст картинки слайда** — фоновый слой декоративный
  (`aria-hidden="true"`), поля для alt в CMS нет. Если картинка когда-нибудь
  станет содержательной (а не фоном под текстом), потребуется отдельное поле
  и пересмотр `aria-hidden`.

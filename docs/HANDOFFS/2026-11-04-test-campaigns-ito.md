# Handoff — тестовые кампании по публичной ссылке (ИТО Собчик)

**Дата:** 2026-11-04. **Ветка:** `mindcare_vb`. **ADR-036.** **Миграция:**
`a3e7c1f9d5b2` (head). **REGISTRY:** 141 → 151 (AUDIT_LOG 134 → 144). **Новая
зависимость:** `openpyxl`. Коммит не выполнялся.

Спецификация и решения заказчика — `docs/MODULES/test-campaigns-ito-spec.md`.

## 1. Что получил заказчик

Центр психологии создаёт **кампанию** и раздаёт студентам **одну ссылку на
всех**. Студент без регистрации заполняет анкету (ФИО, факультет из каталога,
специальность, возраст, пол), принимает согласие и отвечает на 91 утверждение
ИТО. Результат ему не показывается. Супервизор скачивает xlsx в формате
`Пример_Собчик.xlsx` + «Достоверность», «Тип», «Дата прохождения».

## 2. Ключ и интерпретация (решения заказчика)

- Ключ — методичка Собчик (стр. 10–13) **с исправлением опечатки**: в II
  «Спонтанность» вопрос **49** (в книге 40, который также в VIII). Совпадает с
  `ИТО (ключ).xls`. Каждый вопрос 2–90 — ровно в одной шкале; 1 и 91 — вне шкал.
- Уровни I–VIII: 0–2 / 3–4 / 5–7 / 8–9. Недостоверно: L > 5 или F > 5.
- Типы — документ заказчика `ИТО Собчик_шкалы_типы.docx`: все шкалы типа ≥ 8;
  несколько — через «; »; **при недостоверном результате тип выводится с
  пометкой «(недостоверно)»** (иначе тип с F ≥ 8 не присваивался бы никогда).
- Текст 91 утверждения — методичка, OCR-ошибки исправлены по опроснику
  (вопросы 13, 14, 39, 74, 87).

## 3. Этапы

| Этап | Что | Где |
|---|---|---|
| 1 | Схема: `tests.scoring_profile`/`campaign_only`, `test_campaigns`, `campaign_responses`, `campaign_response_scales`, `campaign_response_answers` | `alembic/versions/a3e7c1f9d5b2_add_test_campaigns.py`, `app/db/models/test_campaigns.py` |
| 2 | Профиль ИТО, seed, скрытие теста из каталога и `/api/tests`, запрет правки в конструкторе (409), `has_results` учитывает ответы кампаний | `app/tests/profiles/`, `scripts/seed_ito_sobchik.py`, `app/tests/storage.py` |
| 3 | Публичный API + согласие `campaign_consent` v1 + `campaign_response_submitted` (анонимный актор) | `app/campaigns/routes_public.py`, `storage.py`, `app/db/seed.py` |
| 4 | API супервизора, xlsx, удаление, 8 событий | `app/campaigns/routes_supervisor.py`, `storage_supervisor.py`, `export.py` |
| 5 | Frontend: `/test/:token` (до 2026-11-05 — `/c/:token`, работает), `/supervisor/campaigns` | `api/campaigns.api.js`, `features/campaigns/`, `pages/campaign/`, `pages/supervisor/CampaignsPage.jsx` |

Попутно: `scripts/isolated_test_db.py` ловит SIGTERM/SIGHUP и удаляет
временную БД (раньше она оставалась при остановке прогона); закреплённый head
в `tests/test_audit_created_index_model.py` обновлён.

## 4. Безопасность и ФЗ-152

- Ответы кампаний — **отдельные таблицы**; `test_results` не тронут: история
  студента, Этап E и карточка клиента их структурно не видят.
- ФИО и токен ссылки — только `enc:v1:` (CHECK). Поиск по SHA-256 токена.
- IP/UA — только в `consent_records` (`user_id = NULL`), как при регистрации.
- GET анкеты не отдаёт `value_score`/`config`/шкалы (ключ не раскрыт).
- `NoStoreRoute` на обоих роутерах: no-store, 422 без значений полей.
- Чтение ФИО (страница участников) и выгрузка — fail-closed аудит до отдачи.
- Удаление ответа/кампании — **физическое** (исключение из soft delete),
  вместе с записями согласия, одной транзакцией с ATOMIC-событием.
- xlsx: текст пишется строкой — ввод «=…» не становится формулой.
- Доступ — только `supervisor`, impersonation закрыт; admin без роли
  supervisor ответов не видит.
- Черновик анкеты (с ФИО) — `sessionStorage` вкладки участника до отправки
  или закрытия вкладки (утверждено владельцем 2026-11-04).

## 5. Деплой (обязательно, по порядку)

```bash
cd mindcare_api
.venv/bin/pip install -r requirements.txt        # openpyxl
.venv/bin/alembic upgrade head                   # a3e7c1f9d5b2
# перезапуск API: seed создаёт согласие campaign_consent v1
.venv/bin/python scripts/seed_ito_sobchik.py --dry-run
.venv/bin/python scripts/seed_ito_sobchik.py     # тест ИТО (campaign_only)
cd ../mindcare_web && npm run build
```

Проверить `FRONTEND_PUBLIC_URL` окружения: без него ссылка в кабинете
собирается из адреса браузера супервизора.

## 6. Тесты

- Backend: полный прогон после этапа 4 — **4901 passed, 0 failed**; после
  этапа 5 повторены тесты кампаний (64 passed). Новые:
  `tests/test_ito_sobchik_profile.py`,
  `tests/integration/test_test_campaigns_schema.py`,
  `test_test_campaigns_migration.py` (gated, `MINDCARE_MIGRATION_ROUNDTRIP=1`
  **только вместе с** `-k test_campaigns_migration`),
  `test_ito_campaign_test_integration.py`, `test_campaign_public_api.py`,
  `test_campaign_supervisor_api.py`; сигналы раннера — в
  `tests/test_isolated_test_db.py`.
- Frontend: 2645 passed (190 suites), lint и build — без ошибок. Новые:
  `api/campaigns.api.test.js`, `features/campaigns/lib/draft.test.js`,
  `ui/PublicCampaign.test.jsx`, `ui/CampaignCard.test.jsx`.
- **Ручной браузерный smoke не выполнялся.**

## 6a. Первичная обработка (дополнение того же дня)

- `app/campaigns/analytics.py` — уровни, достоверность, типы, фильтры, сводка
  (средние, мин/макс, распределение уровней, частоты типов, по факультетам и
  полу); один расчёт для экрана и xlsx.
- xlsx: «Результаты» (образец заказчика, баллы залиты по уровню), «Уровни»,
  «Сводка», «Ответы».
- `GET /api/supervisor/campaigns/{uuid}/results` (фильтры на сервере,
  fail-closed `campaign_results_read`, REGISTRY 151).
- Кабинет: кнопка «Результаты» в карточке кампании — фильтры, итоги, таблицы
  по шкалам/типам/группам, участники с цветом уровня.
- Тесты: `tests/test_campaign_analytics.py`, 4 integration-теста `/results` в
  `test_campaign_supervisor_api.py`, `ui/CampaignResults.test.jsx`.
  Backend (кампании/аудит/реестр) — 1490 passed; frontend — 2652 passed;
  lint, build — без ошибок. Демо-стенд пересобран и перезапущен.

## 6b. ЧПУ ссылки (2026-11-05)

- Ссылка: `https://<FRONTEND_PUBLIC_URL>/test/ito-ekonomfak-2026-k7m2xq` — slug
  из названия (транслит) + 6 случайных символов (`app/campaigns/tokens.py`).
  «Сменить ссылку» меняет только хвост. Старые `/c/<токен>` работают.
- Прод: `FRONTEND_PUBLIC_URL=https://mindcare.donnu.ru` (deploy/README.md).
- «Результаты»: таблицы «По полу» и «По факультетам» раздельно (раньше пол
  терялся в конце общей таблицы).
- Тесты: `tests/test_campaign_tokens.py` (24), интеграция кампаний — 145 passed;
  frontend `features/campaigns` — 24 passed, lint чистый.

## 6c. Переименование (2026-11-06)

- «Переименовать» в карточке кампании → `PATCH /api/supervisor/campaigns/{uuid}`
  `{title}`. Адрес ссылки не меняется; участники видят новое название.
- Событие `test_campaign_renamed` (REGISTRY 151 → 152, AUDIT_LOG 145),
  снимок registry перегенерирован, подпись — «Кампания тестирования переименована».
- Тесты: `test_rename_keeps_link`, `test_rename_validation_and_404`,
  `test_rename_forbidden_for_other_staff`; frontend `CampaignCard.test.jsx` (+3),
  `campaigns.api.test.js` (+1).

## 7. Открыто

- Ручной smoke: прохождение с телефона, sticky-прогресс под шапкой сайта,
  фокус на первой ошибке в Select, создание кампании, копирование ссылки, xlsx.
- Rate limit — по `request.client.host`, uvicorn без `--proxy-headers`: за
  прокси это общий потолок на поток (600 чтений / 300 отправок за 10 мин);
  лимитер в памяти процесса. См. BACKLOG.
- «Дублировать» методику ИТО разрешено: копия — обычный тест (флаги не
  копируются) и после публикации попадёт в каталог студента.
- Окно подтверждения в разделе кампаний переиспользует
  `features/assignments/ui/ConfirmDialog` (межфичевый импорт).

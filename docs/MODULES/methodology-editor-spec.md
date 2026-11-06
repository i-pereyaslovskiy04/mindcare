# ТЗ: общий редактор методик, версии и импорт из xlsx

> Статус: **утверждено владельцем 2026-11-06**, реализация по этапам (§8).
> Решение — **ADR-037**. Предыдущий контур — ADR-036 и
> `docs/MODULES/test-campaigns-ito-spec.md`.

## 1. Задача

- Методики (вопросы, варианты, ключ, уровни, достоверность, типы) создаются и
  правятся на сайте, без кода и seed-скриптов.
- Методику можно загрузить из файла xlsx по шаблону.
- Одна методика работает и в каталоге тестов студента, и в тестировании по
  ссылке.
- Правка методики, по которой уже есть ответы, — через новую версию.
- Психолог готовит методику, супервизор или администратор публикует.

## 2. Что уже есть и что добавляется

| Часть методики | Где хранится сейчас | После |
|---|---|---|
| Вопросы, варианты | `questions`, `options` | без изменений |
| Ключ (шкала вопроса, баллы вариантов) | `questions.config.scale`, `options.value_score` | без изменений |
| Пороги интерпретации по шкалам | `test_interpretations` | без изменений (текст студенту) |
| Подписи и порядок шкал, основные шкалы | код `ito_sobchik.py` | `tests.scoring_rules.scales` |
| Общие уровни основных шкал | код | `scoring_rules.levels` |
| Достоверность | код | `scoring_rules.validity` |
| Типы | код | `scoring_rules.types` |
| Инструкция | код | `scoring_rules.instruction` |

## 3. Схема `scoring_rules` (`ScoringRulesV1`)

```json
{
  "version": 1,
  "instruction": "Прочитайте каждое утверждение…",
  "scales": [
    {"code": "L", "label": "L Ложь", "main": false},
    {"code": "F", "label": "F Аггравация", "main": false},
    {"code": "IV", "label": "IV Ригидность", "main": true}
  ],
  "levels": [
    {"code": "low", "label": "Гипоэмотивность…", "min": 0, "max": 2},
    {"code": "norm", "label": "Норма", "min": 3, "max": 4},
    {"code": "accent", "label": "Акцентуированные черты", "min": 5, "max": 7},
    {"code": "maladaptive", "label": "Дезадаптирующие свойства", "min": 8, "max": 9}
  ],
  "validity": {
    "scales": [{"code": "L", "max_valid": 5}, {"code": "F", "max_valid": 5}],
    "invalid_mark": "недостоверно"
  },
  "types": {
    "threshold": 8,
    "items": [{"name": "Социально активный, ранимый", "scales": ["I", "VI"]}]
  }
}
```

**Правила схемы** (pydantic, `extra=forbid`, ошибки → 422):
- `code` шкалы: 1–20 символов `[0-9A-Za-zА-Яа-яЁё_]`, уникальны. `label`: 1–100. Шкал не больше 50.
- `levels`: код `[a-z0-9_]{1,30}` уникален, `min ≤ max`, диапазоны не пересекаются, не больше 10.
- `validity.scales[].code` и `types.items[].scales[]` ссылаются на объявленные шкалы.
- Название типа: 1–255 символов, не больше 50 типов.
- `instruction` ≤ 2000. Управляющие символы запрещены во всех строках.
- Всё необязательно, кроме `version` и `scales`. Пустой блок — функция не считается.

**Проверки против вопросов** (`analyze_test`, предупреждение в черновике, 422 при отправке на проверку и публикации):
- каждая шкала вопросов (`config.scale`) объявлена в `scales` и наоборот;
- уровни покрывают диапазон каждой основной шкалы (`score_bounds`) без пробелов.

**Вычисление** — `app/tests/rules.py`, чистые функции, без БД:
- `level_of(rules, score)` → код уровня; только для `main`-шкал;
- `is_valid(rules, scores)` — все `validity.scales` не выше `max_valid`; без блока — `None`;
- `types_of(rules, scores)` — все шкалы типа ≥ `threshold`; при недостоверности — с пометкой ` (<invalid_mark>)`;
- `summarize(rules, scores)` → `{is_valid, types}` — снимок `rule_summary`.

Результаты ИТО обязаны совпасть с нынешними `ito_sobchik.py` / `analytics.py` (эталонный тест).

## 4. Модель данных (миграция этапа 2)

- **`tests.scoring_rules`** JSONB NULL.
- **`tests.lineage_uuid`** UUID NOT NULL (backfill = `tests.uuid`) + индекс. Общий для версий одной методики.
- **`tests.superseded_at`** TIMESTAMPTZ NULL — вышла опубликованная новая версия.
- **`test_results.rule_summary`** JSONB NULL — снимок `{is_valid, types}` на момент отправки.
- **CHECK `ck_tests_scoring_profile` удаляется.** Data-миграция: тест с `scoring_profile = 'ito_sobchik'` получает `scoring_rules` из констант ИТО (значения зафиксированы в миграции, не импортом модуля).
- **Downgrade** — fail-closed:
  - есть `scoring_rules` у теста без `scoring_profile`;
  - есть версии с общим `lineage_uuid`;
  - есть заполненный `rule_summary`.

## 5. Поведение

- **Каталог студента** (`find_active_tests`, `get_active_test_full`, `save_result`): плюс `superseded_at IS NULL`; `campaign_only` по-прежнему скрыт.
- **Выбор методики кампании:** опубликованная, включённая, не `superseded`; `campaign_only` не требуется.
- **Правка** (`update_test`, `update_my_test`):
  - без результатов — как обычный тест, включая rules и `campaign_only`;
  - с результатами — метаданные можно, вопросы, ключ и rules нельзя: 409 `test_has_results` с текстом «Создайте новую версию».
  - Удаление теста с ответами кампаний запрещено (RESTRICT).
- **Новая версия:** `POST …/{uuid}/new-version`:
  - копия с тем же `lineage_uuid`, `version = max(version по lineage) + 1`, draft, `is_active=false`, тем же названием и `campaign_only`;
  - одна черновая версия на lineage — повтор → 409 `draft_version_exists`;
  - событие `test_version_created`.
- **Публикация** версии v>1: в той же транзакции прежним опубликованным версиям lineage ставится `superseded_at`.
- **Исправить текст:** `PATCH …/{uuid}/texts` `{expected_updated_at, questions: [{question_order, text, options: [{option_order, text}]}], instruction?}`:
  - тест под `FOR UPDATE`;
  - набор порядковых номеров должен совпасть полностью, иначе 422 `structure_changed`;
  - меняются только тексты; событие `test_texts_corrected`.
  - Доступно admin/supervisor и автору-психологу для своих тестов.
- **Студенту** в результате `rule_summary` не отдаётся. Staff-деталь (Этап E) отдаёт `rule_summary` и подписи шкал.

## 6. Шаблон xlsx

| Лист | Колонки | Примечание |
|---|---|---|
| Методика | Поле / Значение: Название, Описание, Инструкция, Подсчёт (`sum`) | |
| Варианты ответа | Порядок, Текст | общий набор для всех вопросов (Да/Нет, 1–5) |
| Вопросы | №, Текст | № — 1..N без пропусков |
| Ключ | Шкала, № вопроса, Вариант (порядок), Балл | вопрос — не больше одной шкалы; нет строки — балл 0 |
| Шкалы | Код, Подпись, Основная (да/нет), Предел достоверности | предел заполняют только для шкал достоверности |
| Уровни | Код, Подпись, От, До | |
| Типы | Название, Шкалы (через запятую), Порог | порог одинаков для всех строк |

**Эндпоинты** (admin/supervisor — `/api/admin/tests`, психолог — `/api/psychologist/tests`):
- `GET /methodology-template.xlsx` — пустой шаблон с листом «Как заполнить» (пример заполнения — выгрузка ИТО);
- `GET /{uuid}/methodology.xlsx` — методика в шаблоне;
- `POST /import?dry_run=true` multipart → `{ok, errors: [{sheet, row, column, message}], summary: {questions, scales, levels, types}}`;
- `POST /import` → `TestRead` черновика, событие `test_imported`.

**Безопасность:**
- ≤ 2 МБ, ≤ 500 вопросов, ≤ 20 вариантов, ≤ 50 шкал;
- openpyxl `read_only=True, data_only=True`;
- только `.xlsx` (zip-сигнатура);
- файл не сохраняется, значения ячеек не логируются;
- ошибки — без эха содержимого, только адрес и правило.

**Туда-обратно:** выгрузка → импорт → идентичные вопросы, ключ, пороги и rules.

## 7. Аудит

| Событие | Роли | Режим |
|---|---|---|
| `test_imported` | admin, supervisor, psychologist | ATOMIC/RAISE, target test, metadata пустая |
| `test_version_created` | admin, supervisor, psychologist | то же |
| `test_texts_corrected` | admin, supervisor, psychologist | то же |

Правка rules — `test_updated`. Шаблон, выгрузка методики и `dry_run` — без события.

После правки REGISTRY:
- `scripts/export_audit_registry.py`;
- `auditLabels.js`;
- точные счётчики: `test_audit_registry.py`, `test_audit_logs_viewed_event_unit.py`, `test_audit_admin_options_unit.py`, `integration/test_admin_audit_api.py`, `*_audit_unit.py`.

## 8. Этапы

| № | Содержание | Статус |
|---|---|---|
| 1 | ADR-037, это ТЗ | ✅ 2026-11-06 |
| 2 | Миграция, `ScoringRulesV1`, `rules.py`, перенос ИТО, analytics/export на rules, `rule_summary`, эталонный тест | ✅ 2026-11-06: миграция `b6d2e8f4a1c3`; `tests/test_scoring_rules.py`, `test_campaign_golden_ito.py` (эталон `tests/fixtures/ito_campaign_golden.json`), `integration/test_rule_summary_results.py`, gated `test_methodology_rules_migration.py`. API результатов кампании: `profile` → `has_rules`/`has_validity`/`levels[{tone}]`/`validity_title`/`type_threshold` |
| 3 | UI «Правила обработки», `campaign_only`, analyze/preview, выбор методики кампании | ✅ 2026-11-06: `RulesBuilder`, `lib/rulesShape`; API `rule_issues`, preview `levels`/`rule_summary`; 422 при публикации/отправке с несогласованными правилами; `TestCampaignOnly` снят досрочно (вместо него `TestUsedByCampaigns` на удаление); буферный вопрос без шкалы (все варианты 0) разрешён — иначе ИТО не сохранялся в конструкторе. Демо: миграция применена, сервис перезапущен |
| 4 | Новая версия, `superseded_at`, исправление текстов, снятие `TestCampaignOnly` | ✅ 2026-11-06: `test_methodology_versions_api.py`; UI — «Новая версия», «Сохранить только тексты», бейджи версии |
| 5 | Шаблон, импорт с проверкой, выгрузка методики, UI импорта | ✅ 2026-11-06: `methodology_xlsx.py`, `test_methodology_import_api.py` (туда-обратно ИТО), `MethodologyImportDialog`. Отдельного листа «Пример» нет — пример = выгрузка ИТО |
| 6 | Handoff, CLAUDE.md, деплой на демо, руководство (по согласию) | ✅ 2026-11-06: `docs/HANDOFFS/2026-11-06-methodology-editor.md`, демо обновлено; руководство заказчика — по запросу |

# Handoff 2026-11-06 — общий редактор методик, версии, импорт xlsx (ADR-037)

Ветка `mindcare_vb`. Решение — **ADR-037**, ТЗ —
`docs/MODULES/methodology-editor-spec.md`. Миграция **`b6d2e8f4a1c3`** (head).
REGISTRY **152 → 155** (AUDIT_LOG 148).

## 1. Что сделано

- **Правила обработки как данные.** `tests.scoring_rules` (ScoringRulesV1,
  `app/tests/rules.py`): шкалы (подпись, основная, порядок выгрузки), общие
  уровни основных шкал, достоверность, типы, инструкция. ИТО перенесён
  data-миграцией; `scoring_profile` код больше не читает, CHECK снят.
  Аналитика и xlsx тестирования по ссылке берут правила теста кампании.
- **Методики общие.** Правила работают и в каталоге студента: при отправке
  снимок `{is_valid, types}` пишется в `test_results.rule_summary`; видят
  психолог и супервизор (Этап E), студент — нет. Кампанию можно создать по
  любой опубликованной методике последней версии; `campaign_only` — только
  «не показывать в каталоге».
- **Редактор** — существующий конструктор: раздел «Правила обработки»
  (`RulesBuilder`, `lib/rulesShape`), флажок «Только для тестирования по ссылке».
  `analyze` → `rule_issues`, `preview-score` → уровни, достоверность, тип.
  Отправка на проверку и публикация с несогласованными правилами — 422.
- **Версии.** `POST …/{uuid}/new-version` (тот же `lineage_uuid`, version+1,
  черновик; вторая неопубликованная — 409). Публикация ставит прежним версиям
  `superseded_at` — их нет в каталоге, в прохождении и в выборе методики
  кампании; результаты и кампании остаются на своей версии.
  `PATCH …/{uuid}/texts` — опечатки без новой версии (только тексты и
  инструкция, под FOR UPDATE с `expected_updated_at`). Сплошной запрет правки
  `campaign_only` (`TestCampaignOnly`) снят: после ответов нельзя менять
  вопросы и правила (409), удалить методику с кампаниями нельзя
  (`TestUsedByCampaigns`).
- **Импорт/выгрузка xlsx** (`app/tests/methodology_xlsx.py`): шаблон с листом
  «Как заполнить»; `GET …/methodology-template.xlsx`, `GET …/{uuid}/methodology.xlsx`,
  `POST …/import?dry_run=` (admin/supervisor и психолог — своё). Импорт — всегда
  черновик через проверки конструктора; ошибки — «лист / строка / колонка» без
  содержимого ячеек; ≤ 2 МБ, только xlsx, read_only/data_only. Пример
  заполнения — выгрузка любой методики (например ИТО); отдельного листа
  «Пример» в шаблоне нет.
- **Аудит:** `test_version_created`, `test_texts_corrected`, `test_imported`
  ({admin,supervisor,psychologist}, ATOMIC/RAISE, metadata пустая). Правка
  правил — `test_updated`; шаблон, выгрузка и dry_run — без события.

## 2. Попутные исправления

- Буферный вопрос без шкалы (все варианты 0 баллов, как № 1 и 91 ИТО) больше
  не ошибка «шкала указана не у всех» — иначе ИТО нельзя было сохранить
  в конструкторе.
- Фронт: `analyzeTest`/`previewScore` теряли `scoring_rules` (исправлено, есть тест).
- «Дублировать» теперь переносит правила и `campaign_only` (новая методика,
  свой lineage).
- API результатов кампании: вместо `profile` — `has_rules`, `has_validity`,
  `levels[{code,label,min,max,tone}]`, `validity_title`, `type_threshold`.

## 3. Деплой

`alembic upgrade head` (b6d2e8f4a1c3) → перезапуск API → сборка фронта.
Новых зависимостей нет. Демо-стенд обновлён 2026-11-06.

## 4. Тесты

- Backend: `test_scoring_rules.py`, `test_campaign_golden_ito.py` (эталон
  `tests/fixtures/ito_campaign_golden.json` — все цифры и ячейки xlsx ИТО
  совпадают с прежним кодом), `integration/test_rule_summary_results.py`,
  `test_methodology_rules_api.py`, `test_methodology_versions_api.py`,
  `test_methodology_import_api.py`, gated `test_methodology_rules_migration.py`
  (`MINDCARE_MIGRATION_ROUNDTRIP=1`).
- Frontend: `rulesShape`, `RulesBuilder`, `TestFormPage` (правила, версии,
  тексты), `MethodologyImportDialog`, `tests.api`; полный набор 2681 passed.
- Известный посторонний сбой: `test_public_email_domains_api::test_seeded_domains_are_normalized_names`
  (порядок `yandex.ru`/`ya.ru`), не связан с этой работой.

## 5. Не сделано / открыто

- Нормы и T-баллы по полу и возрасту; несколько шкал на вопрос.
- В шаблоне — только single_choice с общим набором вариантов, без медиа
  (выгрузка такой методики — 422 с пояснением).
- Перевод действующей кампании на новую версию методики, правка анкеты
  участника.
- Импорт произвольных файлов заказчика (xls/docx).
- Ручной браузерный smoke редактора и импорта не выполнялся.

# Handoff 2026-11-07 — редактор методик, этап 2: варианты у вопроса, уровни шкал, нормы, сроки и код ссылки, статистика

Ветка `mindcare_vb`. ТЗ — `docs/MODULES/methodology-editor-v2-spec.md`
(основание — сравнение с onlinetestpad.com, где центр проводит GAD-7, HADS и
др.). Продолжение ADR-037. Миграция **`c2a5f7d9e3b1`** (head). REGISTRY
**155 → 157** (AUDIT_LOG 150). **Деплой: `alembic upgrade head`.**

## 1. Что сделано

| Этап | Коммит | Суть |
|---|---|---|
| Варианты у вопроса в xlsx | `c8205d7` | Лист «Варианты вопросов» (№, порядок, текст) заменяет общий набор у своих вопросов. Выгрузка выбирает лист сама (ИТО и Лайкерт — общим набором). Сводка импорта: `options=None`, `option_sets` |
| Свои уровни шкалы | `3687080` | `scales[].levels` (только основная шкала) вместо общих. `rules.levels_for/level_of(…, scale)/has_levels/own_levels`. Покрытие диапазона — по уровням шкалы. Экран результатов — `scale_levels`; xlsx — подписи по шкале; шаблон — колонка «Шкала» листа «Уровни»; конструктор — «Свои уровни» |
| Сроки и кодовое слово | `730fb75`, `ca0887e` | `test_campaigns.opens_at/closes_at/access_code_hash` (bcrypt). До начала — 409 `campaign_not_started` + `opens_at`; после окончания — 404 как закрытая. Слово: GET — «замок», `POST /unlock`, `submit.access_code`; bcrypt вне транзакции, хеш перепроверяется под FOR SHARE. Супервизор: `PATCH /schedule`, `PUT/DELETE /access-code`, `link_state`, панель «Сроки и код» |
| Статистика | `cefcb39` | `GET /api/supervisor/campaigns/{uuid}/statistics` (фильтры как у results): по дням (МСК), по вопросам, распределение баллов; < 5 участников — без распределений. ФИО не загружаются. Лист «Статистика по вопросам» в xlsx. Вкладка «Статистика» |
| Нормы | `7f82437` | `scales[].norms {kind, label?, groups[{when, table}]}`; условия по `gender`/`age`/`faculty_code` (перечень — `rules.NORM_FIELDS`). Только кампании: `enrich_row.norms`, колонка в xlsx, «(N)» после балла. `norm_gap` блокирует публикацию. Лист «Нормы» в шаблоне. Конструктор — «Нормы (стандартные баллы)» |

**Нормы ИТО:** проверены книга Собчик (2002) целиком, включая таблицы и
ссылки в тексте, ключ, бланк, `ИТО Собчик_шкалы_типы.docx`, пример выгрузки —
таблиц перевода в стены/T-баллы и поправок на пол и возраст нет. ИТО остаётся
на сырых баллах.

## 2. Аудит

- `test_campaign_schedule_changed`, `test_campaign_access_code_changed` —
  {supervisor}, ATOMIC/RAISE под FOR UPDATE, target `test_campaign`, metadata
  только `impersonator_user_id`; ни дат, ни слова, ни хеша. Те же сроки и
  снятие отсутствующего слова — без события; задание слова — событие всегда.
- Статистика — существующее `campaign_results_read` (INDEPENDENT/RAISE).
- Неверное слово, «ещё не началось» — без события (анонимный поток, ADR-036).

## 3. Тесты

- Новые unit: `test_methodology_xlsx.py`, `test_scale_own_levels.py`,
  `test_campaign_statistics.py`, `test_scale_norms.py`.
- Новые integration: `test_campaign_schedule_code_api.py`,
  `test_campaign_statistics_api.py`, gated `test_campaign_schedule_code_migration.py`
  (`MINDCARE_MIGRATION_ROUNDTRIP=1 -k campaign_schedule_code_migration`).
- Счётчики REGISTRY обновлены (157/150), `CURRENT_HEAD = c2a5f7d9e3b1`.
- Эталон ИТО (`test_campaign_golden_ito.py`) без изменений.
- Frontend: 2694 теста, lint чистый.

## 4. Не сделано / риски

- §4.2 (вопрос в нескольких шкалах) — отложено решением владельца.
- Уровни по стандартному баллу (`levels_on: "norm"`) — нет.
- GAD-7 и HADS центра на сайт не перенесены (тексты — содержимое заказчика;
  перенос — их выгрузкой в шаблон по решению владельца). Механизм проверен
  на синтетической HADS-подобной методике.
- Лимит попыток слова — per-process (как весь `rate_limit`).
- Ручной браузерный smoke новых экранов на демо — см. отчёт в чате.

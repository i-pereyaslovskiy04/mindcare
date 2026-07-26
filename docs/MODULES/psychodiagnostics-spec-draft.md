# ТЗ (черновик): Модуль психологических тестов

> Статус: **решения утверждены; реализованы Этапы A-D**:
> backend/admin CRUD, frontend admin-конструктор, student прохождение,
> scoring, consent-gate и история/деталка результатов. Дата сверки: 2026-06-27.
> Backend-модуль `app/tests/` (routes/routes_admin/schemas/service/storage/scoring),
> миграция `c1d4e7a2f9b3` (test_interpretations), seed `test_consent` v1,
> демо PHQ-9 (`scripts/seed_demo_test.py`). Остаётся Этап E (supervisor/psychologist
> просмотр результатов по правилам ADR-016) и отдельный этап moderation workflow.
> Опирается на уже существующую схему БД ([005_psychodiagnostics.sql](../../db/sql/migrations/005_psychodiagnostics.sql),
> [diagnostics.py](../../mindcare_api/app/db/models/diagnostics.py)) и enum-типы
> ([001_extensions_types.sql](../../db/sql/migrations/001_extensions_types.sql)).
> Раздел «Открытые решения» требует подтверждения до начала реализации.

## 1. Цель и границы

Онлайн-психодиагностика: студент проходит тест, система автоматически считает баллы,
выдаёт результат с интерпретацией/рекомендациями и сохраняет историю.

**В scope:**
- Admin/supervisor CRUD тестов, вопросов, вариантов, шкал и порогов интерпретации.
- Публикация/снятие теста (`is_active`, soft delete).
- Прохождение теста студентом с проверкой согласия ФЗ-152.
- Автоподсчёт (`sum`, `average`) одношкальных и многошкальных тестов.
- Сохранение результата, истории прохождений, просмотр результата студентом.
- Просмотр результатов supervisor (право `tests:view_results_any`) и связанного
  psychologist по правилам ADR-016.

**Вне scope MVP** (отдельные этапы):
- `weighted` / `custom` scoring.
- Тайм-лимит с серверным enforcement (`time_limit_min` хранится, но не принуждается в MVP).
- Картиночные тесты (`question_media` / `option_media`) — таблицы есть, UI/логика позже.
- Экспорт результатов (PDF/CSV), сравнение во времени, графики динамики.
- Экспорт результатов для staff, сравнение динамики и графики по времени.

## 2. Роли и доступ

| Действие | student | psychologist | supervisor | admin |
|---|---|---|---|---|
| Список/прохождение активных тестов | ✅ | — | — | — |
| Свои результаты | ✅ | — | — | — |
| CRUD тестов/вопросов | — | — | ✅ | ✅ |
| Результаты любого пользователя | — | — | ✅ | metadata-only? (см. 8.4) |
| Результаты своих назначенных студентов | — | planned (active/past engagement) | ✅ | — |

Права уже засижены: `tests:list`, `tests:take`, `tests:manage`, `tests:view_results_any`
(последнее — у supervisor). Защита — на роутере через `require_role`, не только на фронте.

> ⚠️ Обновление 2026-06-27: ADR-016 разрешает psychologist видеть результаты только тех
> студентов, с которыми есть active/past `TherapyEngagement`. Backend/UI для этого доступа
> ещё не реализованы; при реализации нужны scope-check, audit и отсутствие доступа admin
> к регулярному просмотру результатов.

## 3. Модель данных (существующая, без изменений где возможно)

8 таблиц — см. схему. Ключевое:

- `tests`: `scoring` (enum `scoring_method`), `max_score`, `version`, `is_active`, `deleted_at`.
- `questions`: `question_type` (enum), `question_order`, `is_required`, `config` JSONB.
- `options`: `value_score` (балл варианта), `option_order`.
- `test_results`: `total_score`, `max_possible`, `scoring_used`, `recommendations`, `test_version`.
- `test_result_scales`: пошкальный результат (`scale_name`, `score`, `interpretation`, `metadata`).
- `student_answers`: `option_id` / `selected_options[]` / `scale_value` / `free_text_answer`.

**Enum-типы (авторитетный источник — БД):**
```
question_type  = single_choice | multiple_choice | scale | free_text
scoring_method = sum | average | weighted | custom
```
> Примечание: комментарий в ORM `Test.scoring` («sum/average/scale») неточен — поправить на
> значения enum. В MVP реализуем только `sum` и `average`.

### 3.1. Чего в схеме НЕ хватает (требует решения — см. раздел «Открытые решения»)

1. **Пороги интерпретации** (диапазон балла → метка + рекомендация). Сейчас негде хранить.
2. **Маппинг вопрос → шкала** для многошкальных тестов. Кандидат: `questions.config` JSONB.
3. У `tests` нет JSONB-поля под конфиг теста (в отличие от `questions`).

## 4. Подсчёт результата

1. **single_choice** → балл = `value_score` выбранного варианта.
2. **multiple_choice** → сумма `value_score` всех выбранных (`selected_options[]`).
3. **scale** → `scale_value` (как введён).
4. **free_text** → баллов не даёт (`is_required` валидируется, в скоринг не входит).

**Агрегация по тесту:**
- `sum` → сумма баллов всех вопросов.
- `average` → среднее по вопросам, дающим балл.

**Многошкальные тесты:** каждый вопрос относится к шкале (см. маппинг). Балл считается
по каждой шкале отдельно → строки в `test_result_scales`. `total_score` для многошкального
теста = `NULL` (решение 9.4 — смысл в шкалах, не в общей сумме).

**Интерпретация:** по итоговому баллу (или баллу шкалы) ищется диапазон в порогах →
`recommendations` (тест) / `interpretation` (шкала).

## 5. Версионирование

- Результат фиксирует `test_version` на момент прохождения.
- Редактирование уже опубликованного теста, на который есть результаты: **поднимать `version`**,
  старые результаты остаются привязаны к старой версии (исторически корректны).
- Решение 9.5: «жёсткое» версионирование (snapshot вопросов) в MVP **не делаем** — храним только
  номер версии; вопросы редактируются in-place. Риск: текст вопроса для старого результата
  может измениться. Для MVP приемлемо (результат хранит баллы, не снапшот формулировок).

## 6. ФЗ-152 / согласие

- Тип согласия **`test_consent`** уже предусмотрен в модели `consents` и helper
  `get_active_consent_id("test_consent")` существует.
- **Перед стартом прохождения** проверять наличие принятого актуального `test_consent`:
  - нет активной версии политики в БД → 500/конфиг-ошибка (как с другими seed-согласиями);
  - пользователь не принял текущую версию → 403, фронт показывает экран согласия;
  - при принятии — запись в `consent_records` (с IP/User-Agent через `save_consent_record`).
- Plaintext результатов не логировать. Persistence результатов — обычные таблицы, **без шифрования**
  (решение 9.6): результат теста = структурированные баллы + шаблонная трактовка, не свободный
  терапевтический текст уровня session_notes.
- IP в `consent_records` анонимизируется штатным `anonymize_old_ips()` (90 дней).

## 7. API (предлагаемые эндпоинты)

Канон модуля: `routes.py` (public/student), `routes_admin.py`, `schemas.py`, `service.py`,
`storage.py`. Все эндпоинты `def`. Внешние идентификаторы — `uuid`.

### Студент / публичные
| Метод | URL | Доступ |
|---|---|---|
| GET | `/api/tests` | student — список активных тестов (без вопросов) |
| GET | `/api/tests/{uuid}` | student — тест с вопросами/вариантами для прохождения (без `value_score`!) |
| POST | `/api/tests/{uuid}/submit` | student — отправка ответов → подсчёт → `test_result` |
| GET | `/api/tests/results` | student — свои результаты |
| GET | `/api/tests/results/{uuid}` | student — один свой результат (+ шкалы) |

> ⚠️ Публичная выдача вопросов **не должна содержать `value_score` / правильные баллы** —
> иначе клиент видит «ключ» теста.

### Admin / supervisor
| Метод | URL | Доступ |
|---|---|---|
| GET/POST | `/api/admin/tests` | admin, supervisor |
| GET/PATCH/DELETE | `/api/admin/tests/{uuid}` | admin, supervisor |
| вложенное управление вопросами/вариантами/порогами | (через PATCH теста или под-роуты) | admin, supervisor |
| GET | `/api/admin/tests/{uuid}/results` | supervisor (`tests:view_results_any`) |
| GET | TBD psychologist results endpoint | psychologist только по active/past engagement |

## 8. Валидация и edge-cases

1. Нельзя submit на неактивный/удалённый тест.
2. Все `is_required` вопросы должны иметь ответ → иначе 422.
3. `single_choice`: ровно один `option_id`. `multiple_choice`: `selected_options[]` ⊆ вариантов вопроса.
4. `scale`: `scale_value` в диапазоне из `questions.config` (`min`/`max`).
5. Повторное прохождение: **разрешено** (новая строка `test_results`); история сохраняется.
6. Submit атомарен: `test_result` + `test_result_scales` + `student_answers` в одной транзакции.
7. Консистентность ответов с текущей версией теста (вопросы/варианты принадлежат этому тесту).

## 9. Принятые решения (подтверждены 2026-06-20)

| # | Вопрос | **Решение** |
|---|---|---|
| 9.1 | Где хранить пороги интерпретации? | ✅ **Новая таблица** `test_interpretations` (test_id, scale_name NULLABLE, min_score, max_score, label, recommendation). Требует новой Alembic-миграции. |
| 9.2 | Маппинг вопрос→шкала | ✅ В `questions.config` JSONB: `{"scale": "anxiety"}`. Без миграции. |
| 9.3 | Какие question_type в MVP | ✅ `single_choice`, `multiple_choice`, `scale`. `free_text` — хранить, но в скоринг не включать. |
| 9.4 | `total_score` многошкального теста | ✅ Оставить `NULL` (смысл — в шкалах). |
| 9.5 | Глубина версионирования | ✅ Только номер `version`, без снапшота формулировок. |
| 9.6 | Шифровать ли результаты | ✅ **Нет** — результат теста (структурированные баллы + шаблонная трактовка) не является свободным терапевтическим текстом. Хранить как обычные таблицы. |
| 9.7 | Доступ psychologist к результатам своих студентов | ✅ Обновлено ADR-016: разрешить только для студентов с active/past `TherapyEngagement`; реализация pending и требует scope-check + audit. |
| 9.8 | Seed реальных методик | ✅ Засидить **одну** валидированную демо-методику (PHQ-9 или HADS) для end-to-end проверки скоринга/интерпретации. |

### 9.1 — детализация таблицы `test_interpretations`
```
test_interpretations
  id              PK
  test_id         FK tests(id) ON DELETE CASCADE
  scale_name      VARCHAR(100) NULL   -- NULL = интерпретация по итоговому баллу теста;
                                      --        иначе привязка к шкале (test_result_scales.scale_name)
  min_score       INT NOT NULL
  max_score       INT NOT NULL
  label           VARCHAR(255) NOT NULL   -- напр. "Умеренная тревога"
  recommendation  TEXT                    -- текст рекомендации
  -- индекс (test_id, scale_name); диапазоны не должны пересекаться (валидация в service)
```
Новая Alembic-миграция → новый head. ORM-модель добавить в `diagnostics.py`.

## 10. Тестирование (по правилам проекта)

- Unit: scoring-логика (`sum`/`average`, multi-scale, интерпретация по порогам) — без БД.
- Integration: submit end-to-end (валидация, consent-gate, атомарность, повторное прохождение,
  изоляция `value_score` от публичной выдачи).
- Failure-injection для submit UoW (как для auth).
- Frontend: smoke прохождения + admin CRUD.

## 11. Этапность (предложение)

1. **Этап A** — backend admin CRUD тестов/вопросов/вариантов (+ пороги после решения 9.1).
2. **Этап B** — backend прохождение + scoring + consent-gate + результаты (+ тесты).
3. **Этап C** — frontend admin-конструктор теста. ✅ Реализовано.
4. **Этап D** — frontend прохождения и просмотра результата студентом. ✅ Реализовано.
5. **Этап E** — supervisor/psychologist-просмотр результатов с role/scope checks. Pending.
6. **Этап F** — moderation workflow для тестов: `draft -> in_review -> published`
   / `needs_changes`, авторство psychologist, публикация admin/supervisor. Pending.
7. Позже: медиа-вопросы, weighted/custom, тайм-лимит, экспорт, динамика.

# Handoff (2026-09-02): доработки модерации тестов после Этапов E/F1/F2

Продолжение блока психодиагностики поверх `docs/HANDOFFS/2026-08-30-test-question-option-media-images.md`
(Этапы E/F1/F2). Три независимых доработки, все покрыты тестами и задеплоены
на демо-стенд в рамках работы.

## 1. Модерация тестов доступна supervisor во фронтенде

**Баг, не недоделка**: backend уже разрешал supervisor модерацию тестов
(`require_role("admin","supervisor")` на всём `routes_admin.py`), но
frontend-роут `/admin/tests` был закрыт `RoleRoute roles={['admin']}` — у
supervisor не было НИКАКОГО пути к списку/публикации/возврату тестов.

Исправлено параметризацией: `AdminTestsPage`/`TestFormPage` принимают проп
`cabinetRole` (по умолчанию `'admin'`) и строят базовый путь
`` `/${cabinetRole}/tests` `` — тот же паттерн, что `MeetingTypesPage`/
`ServiceCardsPage`/`BannerSlidesPage`. `router.jsx` монтирует те же
компоненты под `/supervisor/tests`(`/new`, `/:uuid`) с `cabinetRole="supervisor"`.
`SupervisorLayout.jsx` — новый nav-пункт «Тесты» + dynamic crumb.

Попутно найден и исправлен собственный баг рефакторинга: `adminConfig(cabinetRole)`
создавал новый объект конфига на каждый рендер, что зацикливало `useEffect`
загрузки теста (`effectiveConfig.api` в deps) — форма зависала на «Загрузка…».
Исправлено `useMemo`.

## 2. Быстрая деактивация/активация теста из списка

`TestsTable.jsx` — новая кнопка (иконка `power`, тон меняется по `is_active`)
рядом с «Предпросмотром»; проп `onToggleActive` (только admin/supervisor-контекст,
психологу не передаётся). `AdminTestsPage.handleToggleActive` — частичный
`PATCH {is_active: !item.is_active}`, не затрагивает вопросы/интерпретацию.

## 3. Этап F2.1 — психолог дорабатывает СВОЙ published-тест

Раньше правка психолога была заперта на `draft/needs_changes`. Теперь:

- `service._own_updatable_test` (новый, отдельно от `_own_editable_test`,
  который остался delete-only) — допускает `draft/needs_changes/published`,
  блокирует только `in_review`.
- `update_my_test`: если тест был `published`, `storage.update_test` получает
  `unpublish_event="test_unpublished_for_edit"` — атомарно (одна транзакция/
  commit) ставит `status="draft"` и пишет audit-событие ПОВЕРХ обычного
  `test_updated`. Порядок внутри `storage.update_test` важен: `has_results`-
  проверка на вопросах идёт ДО unpublish-мутации, поэтому неуспешная правка
  (409 `TestHasResults`) не демоутит тест попутно — оригинал остаётся
  `published`, если правка вопросов отклонена.
- `has_results` стала ДОСТИЖИМА для психолога (раньше была мертва — draft/
  needs_changes никогда не имеют результатов): вопросы published-теста с
  результатами менять нельзя, метаданные/интерпретацию — можно.
- Фронт: диалог-подтверждение в `PsychologistTestsPage` перед входом в
  редактор published-теста + баннер-дублёр внутри `TestFormPage`
  (`config.warnOnPublishedEdit`) на случай прямого перехода по ссылке.
  `TestsTable` получил раздельные `restrictEditToStatuses`/
  `restrictDeleteToStatuses` (Edit включает published, Delete — нет).
- Audit: `test_unpublished_for_edit` ({psychologist}, ATOMIC/RAISE). REGISTRY
  110 → 111.

## 4. Этап F2.2 — психолог дублирует СВОЙ тест

- `service._own_test_uuid` — гейт владения БЕЗ ограничения по статусу
  источника: дублирование не мутирует оригинал (read + insert независимой
  копии), поэтому разрешено дублировать тест в ЛЮБОМ статусе, включая
  `published`/`in_review` — в отличие от update/delete. Ключевое отличие от
  F2.1: дублирование published НЕ снимает оригинал с публикации.
- `service.duplicate_my_test` переиспользует общий `storage.duplicate_test`
  (тот же путь, что admin/supervisor) — копия всегда `draft`,
  `is_active=False`, `version=1`.
- Роут: `POST /api/psychologist/tests/{uuid}/duplicate` (201, `TestRead`).
- Audit: `test_duplicated` роли расширены `{admin,supervisor}` →
  `{admin,supervisor,psychologist}` (только role-set, REGISTRY count не
  меняется — 111).
- Фронт: `TestFormPage` — `handleDuplicate` параметризован через
  `effectiveConfig.duplicateFn` (раньше был хардкожен на admin-эндпоинт).
  `PsychologistTestFormPage`: `showDuplicate: true`, `duplicateFn: duplicateMyTest`.
  Побочный эффект: 409-баннер «есть результаты, создайте копию» (has_results
  на правке вопросов published-теста) стал ОСМЫСЛЕННЫМ и для психолога — до
  F2.2 кнопки дублирования не было, баннер скрывался, показывался только
  текст ошибки.
- Как в списке (`PsychologistTestsPage`/`TestsTable`) духлицировать НЕ
  добавлено — как и у admin, действие доступно только из редактора теста
  (кнопка «Дублировать» на странице правки).

## Тесты

Backend: unit — `_own_updatable_test`/`_own_test_uuid` все комбинации
статус×владение, `update_my_test`/`duplicate_my_test` вызывают
`storage.*` с ожидаемыми kwargs (mock). Integration
(`test_psychologist_tests_api.py`): правка published → 200, status=draft, оба
audit-события одной транзакцией; правка draft/needs_changes НЕ пишет
unpublish-событие; published с результатами — правка вопросов 409 (оригинал
остаётся published), правка метаданных 200 (снимается); дублирование draft →
201 независимая копия; дублирование published/in_review → 201, ОРИГИНАЛ не
меняет статус; чужой тест — 404 и для правки, и для дублирования. Полный isolated suite:
**2888 passed, 0 failed, 69 skipped**.

Frontend: lint 0, build успешен, 82/82 suite (1082/1082 тестов).

## Не делалось (за пределами этого блока)

Экспорт результатов для staff (см. `docs/BACKLOG.md` §«🔵 Запланировано» —
помечен приоритетным, но НЕ реализован: только зафиксирован объём решений,
которые нужно принять до начала работы). `custom` scoring, `duration_seconds`,
PDF-экспорт результата, серверный тайм-лимит, caption вариантов —
по-прежнему отложены (см. `docs/HANDOFFS/2026-08-30-test-question-option-media-images.md` §8).

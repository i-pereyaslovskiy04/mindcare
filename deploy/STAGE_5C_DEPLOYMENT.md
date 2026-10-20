# Развёртывание Stage 5C (audit расписаний, групп и maintenance)

Stage 5C добавляет две Alembic-ревизии и **два обязательных периодических
job'а**. Обычный порядок «накатить миграции, потом выложить приложение» здесь
**небезопасен** — ниже описаны два поддерживаемых пути и почему третьего нет.

## Что именно меняется

| Ревизия | Что делает |
|---|---|
| `a1c4e8b2f7d3` (5C-0A) | `CREATE TABLE schedule_series` + идемпотентный fail-closed backfill. **FK не добавляются.** |
| `b5d7f0a3c9e1` (5C-0C) | Повторный backfill → preflight → `ADD CONSTRAINT … NOT VALID` ×2 → `VALIDATE CONSTRAINT` ×2 |

Между ними находится **изменение приложения (5C-0B)**: все три генератора
`series_id` (`create_schedule_rules_bulk`, `create_schedule_series`,
`create_schedule_breaks_bulk`) начинают вставлять identity-строку `schedule_series`
ДО вставки rules/breaks.

## Почему `alembic upgrade head` в один шаг небезопасен

`upgrade head` применяет **обе** ревизии подряд. Если старая версия приложения в
этот момент ещё обслуживает запросы, она создаёт серии `series_id` **без**
identity-строки. Сразу после этого 5C-0C включает FK — и такие записи нарушают
constraint: supervisor получает 500 при создании расписания, а `VALIDATE` может
упасть на «сиротах».

Поэтому допустимы ровно два пути.

---

## Путь A — с остановкой приложения (рекомендуется для этого стенда)

Подходит, когда короткий простой приемлем. Compatibility window физически
отсутствует, потому что старый код не работает во время миграции.

> **Автоматизировано:** `./deploy.sh` при обновлении **существующей** БД
> выполняет ровно этот путь — останавливает writer-юниты, спрашивает
> подтверждение, падает при ошибке Alembic и поднимает сервисы обратно (в т.ч.
> при неудачной миграции). Ручная последовательность ниже нужна, когда деплой
> идёт не через скрипт.

### Какие юниты гасить

Останавливать надо **все процессы, которые пишут в БД**, а не один известный:

| Юнит | Когда существует | Пишет в БД |
|---|---|---|
| `mindcare-api.service` | создаёт `deploy.sh` | да (`uvicorn app.main:app`) |
| `mindcare-demo.service` | демо-стенд, `deploy/mindcare-demo.service` | да (`serve_demo:app` — тот же `app.main`) |
| `mindcare-web.service` | создаёт `deploy.sh` | нет (CRA-фронт) |
| ручной `uvicorn` / `mindcare-mode.sh dev` | dev-режим | да |

`mindcare-complete-group-sessions.timer` и `mindcare-extend-schedules.timer`
тоже пишут, но `series_id` **не создают** и окно совместимости не нарушают;
останавливать их не обязательно.

```bash
cd /media/data2/psycho/mindcare

# 1. Погасить ВСЕХ писателей (существующие из них)
sudo systemctl stop mindcare-api.service mindcare-demo.service 2>/dev/null
scripts/mindcare-mode.sh stop          # dev-серверы, если они были подняты

#    Проверка, что писателей не осталось: ответа быть не должно
curl -sf --max-time 3 http://localhost:8000/docs && echo "ПИСАТЕЛЬ ЖИВ — не продолжать"

# 2. Выложить новый код (5C) — приложение НЕ запускать
git pull   # или иной способ доставки

# 3. Накатить обе ревизии
cd mindcare_api && .venv/bin/alembic upgrade head && .venv/bin/alembic current

# 4. Поднять приложение уже с новым кодом
cd .. && sudo systemctl start mindcare-api.service   # либо scripts/mindcare-mode.sh demo
```

**Требование:** между шагами 1 и 4 старая версия приложения не должна принимать
запросы. Это и есть «гарантированный downtime» — его нельзя заменить надеждой,
что в окно никто не создаст расписание. Именно поэтому шаг 1 содержит явную
проверку порта: незамеченный ручной `uvicorn` превращает простой в фикцию.

---

## Путь B — поэтапный rollout без простоя (expand/contract)

Подходит, когда останавливать сервис нельзя. Ревизии применяются **раздельно**, а
между ними выкладывается совместимое приложение.

```bash
cd /media/data2/psycho/mindcare/mindcare_api

# ── Шаг 1: только identity-таблица + backfill (БЕЗ FK) ──
.venv/bin/alembic upgrade a1c4e8b2f7d3
.venv/bin/alembic current          # ожидается a1c4e8b2f7d3
```
Старое приложение продолжает работать: FK ещё нет, «сироты» допустимы.

```bash
# ── Шаг 2: выложить новый код приложения и перезапустить ──
cd /media/data2/psycho/mindcare
git pull
# перезапустить ВСЕ writer-юниты, которые есть на хосте (см. таблицу в пути A)
sudo systemctl restart mindcare-api.service mindcare-demo.service 2>/dev/null
systemctl is-active mindcare-api.service mindcare-demo.service   # хотя бы один active
```
С этого момента новые серии больше не создаются без identity.

```bash
# ── Шаг 3: включить и валидировать FK ──
cd mindcare_api
.venv/bin/alembic upgrade b5d7f0a3c9e1
.venv/bin/alembic current          # ожидается b5d7f0a3c9e1 (head)
```
5C-0C **повторно** прогоняет идемпотентный backfill — он подбирает серии,
созданные старым кодом в окне между шагами 1 и 2, поэтому `VALIDATE` не падает.

**Шаг 3 нельзя выполнять раньше шага 2.** Порядок обязателен.

### Проверка после любого пути

```bash
cd mindcare_api
.venv/bin/python - <<'PY'
from sqlalchemy import create_engine, text
import os
e = create_engine(os.environ["DATABASE_URL"])
with e.connect() as c:
    print(c.execute(text(
        "SELECT conname, convalidated FROM pg_constraint "
        "WHERE conname IN ('fk_schedule_rules_series','fk_schedule_breaks_series')"
    )).fetchall())
    print("orphans:", c.execute(text(
        "SELECT count(*) FROM schedule_rules r LEFT JOIN schedule_series s "
        "ON s.series_uuid = r.series_id "
        "WHERE r.series_id IS NOT NULL AND s.id IS NULL"
    )).scalar())
PY
```
Ожидается: оба constraint присутствуют с `convalidated = true`, orphans = 0.

### Откат

Downgrade **fail-closed**: если `audit_log` уже содержит строки с
`entity_type='schedule_series'`, обе ревизии откажутся откатываться (фиксированная
диагностика, оба FK и таблица остаются на месте). Это намеренно: пересоздание
таблицы выдало бы другие SERIAL id, и исторический append-only аудит стал бы
ссылаться на неверные серии. **Миграция обратима только до начала audit-writes.**

---

## Обязательные maintenance-job'ы

Stage 5C-3 убрал lazy-completion из GET/list и из регистрации — read-пути больше
не мутируют данные. Поэтому переходы выполняются периодическими job'ами, и их
запуск является **условием эксплуатации, а не опцией**.

| Юнит | Периодичность | Что делает | Без него |
|---|---|---|---|
| `mindcare-complete-group-sessions.timer` | каждые 10 мин | `scheduled → completed` для начавшихся занятий | `status` в supervisor/psychologist-списках отстаёт |
| `mindcare-extend-schedules.timer` | ежедневно 03:20 | продление серий с `auto_extend` на 1 мес (окно 14 дней) | расписание обрывается по достижении `effective_until` |

Запись студента на прошедшее занятие невозможна **независимо** от таймера:
регистрация сама проверяет `status`, `booking_enabled` и lead time (не позднее
чем за час до начала). Таймер влияет на актуальность отображения, не на
безопасность.

### Установка (разово)

```bash
cd /media/data2/psycho/mindcare
sudo cp deploy/mindcare-complete-group-sessions.service \
        deploy/mindcare-complete-group-sessions.timer \
        deploy/mindcare-extend-schedules.service \
        deploy/mindcare-extend-schedules.timer \
        deploy/mindcare-maintenance-failure@.service \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mindcare-complete-group-sessions.timer
sudo systemctl enable --now mindcare-extend-schedules.timer
```

### Мониторинг по exit code

Оба скрипта завершаются **exit 1** при любом сбое мутации / audit / commit, и
**exit 0** при успехе (включая «нечего делать»). Мониторинг строится на состоянии
юнита, а не на разборе логов:

```bash
systemctl list-timers 'mindcare-*'                     # когда следующий прогон
systemctl is-failed mindcare-complete-group-sessions.service   # failed / active
systemctl is-failed mindcare-extend-schedules.service
journalctl -u mindcare-complete-group-sessions.service -n 50
```

`OnFailure=mindcare-maintenance-failure@<unit>` в обоих job-юнитах пишет запись
уровня `daemon.err` в syslog при ненулевом коде. Внешнюю доставку (email /
Telegram / webhook) подключать **в шаблонный юнит**
`mindcare-maintenance-failure@.service`, не трогая сами job-юниты.

### Диагностика намеренно минимизирована

В journal попадают только фаза и **класс** исключения
(`[error] phase=auto_extend error=OperationalError`). `str(exc)`, SQL, UUID
серий, id занятий и даты **не логируются** — это требование минимизации ПДн
Stage 5C. Подробности инцидента ищутся по времени в `audit_log` и в БД, а не в
тексте лога.

### Ручной прогон и предпросмотр

```bash
cd /media/data2/psycho/mindcare/mindcare_api
.venv/bin/python scripts/extend_schedules.py --dry-run   # 0 мутаций, 0 audit-строк
.venv/bin/python scripts/complete_group_sessions.py
echo "exit=$?"
```

`--dry-run` у автопродления **не вызывает audit-writer вообще** — превью не
зависит от доступности audit storage.

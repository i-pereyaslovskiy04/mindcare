# Развёртывание MindCare

> **Stage 5C:** порядок накатывания миграций `a1c4e8b2f7d3` / `b5d7f0a3c9e1` и
> установка обязательных maintenance-таймеров описаны в отдельном runbook —
> [`STAGE_5C_DEPLOYMENT.md`](STAGE_5C_DEPLOYMENT.md). Одношаговый
> `alembic upgrade head` без остановки приложения там **не** поддерживается.
>
> **Stage 7:** IP-анонимизация audit-журналов (ревизия `c8e2b5f7a3d1`) и
> обслуживание партиций — [`STAGE_7_DEPLOYMENT.md`](STAGE_7_DEPLOYMENT.md).
> ⚠ Первый прогон анонимизации **необратим**, поэтому её таймер `deploy.sh`
> устанавливает, но **не включает**.

## Демо-стенд MindCare (локальная сеть)

Постоянно работающий стенд для демонстрации заказчику. Живёт на том же
Raspberry Pi, что и разработка; наружу временно отдаётся роутером
(`mindcare.vitbond.keenetic.pro` → `192.168.0.2:3000`, HTTP).

## Два режима, взаимоисключающие

Оба претендуют на порт **3000**, поэтому одновременно не работают.

| Режим | Что запускается | Порты |
|-------|-----------------|-------|
| `demo` | systemd-юнит `mindcare-demo.service`: один uvicorn (`serve_demo:app`) — API + собранный SPA | 3000 |
| `dev`  | CRA `npm start` + `uvicorn app.main:app --reload` (как при обычной разработке) | 3000, 8000 |

Переключение — скриптом из корня проекта:

```bash
scripts/mindcare-mode.sh demo            # поднять демо (соберёт фронт, если сборки нет)
scripts/mindcare-mode.sh demo --build    # пересобрать фронт и перезапустить демо
scripts/mindcare-mode.sh dev             # погасить демо, поднять dev-серверы
scripts/mindcare-mode.sh stop            # погасить всё
scripts/mindcare-mode.sh status          # что сейчас работает
```

## Как устроен demo-режим

`mindcare_api/serve_demo.py` — ASGI-точка входа: импортирует тот же FastAPI-app
из `app.main` (роуты `/api/*` и `/media/*` не меняются) и монтирует поверх него
`mindcare_web/build` с SPA-fallback на `index.html` — чтобы прямой заход на
`/student/diary` и F5 не давали 404. Плюс gzip (1.4 МБ бандла → ~370 КБ).

Один процесс вместо двух: без nginx и без webpack dev server, который держал бы
сборку в памяти и пересобирал её впустую. RSS демо-процесса — около 120 МБ.

## Установка юнита (разово)

```bash
sudo cp deploy/mindcare-demo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mindcare-demo.service
```

Юнит запускается от пользователя `vitbo`, поднимается после `postgresql.service`,
перезапускается при падении и стартует автоматически после перезагрузки Pi.

```bash
systemctl status mindcare-demo.service
journalctl -u mindcare-demo.service -f     # логи
```

## После изменений в коде

Демо отдаёт **собранную** статику — правки во фронтенде не подхватываются сами:

```bash
scripts/mindcare-mode.sh demo --build      # пересобрать и перезапустить
```

Изменения бэкенда достаточно перезапустить: `sudo systemctl restart mindcare-demo.service`.

**Миграции.** Общего «применить как обычно» больше нет: начиная со Stage 5C
`alembic upgrade head` на работающем приложении небезопасен — между ревизиями
`a1c4e8b2f7d3` и `b5d7f0a3c9e1` есть окно совместимости. Порядок:

- **новая пустая БД** — `cd mindcare_api && alembic upgrade head` (окна нет,
  старой версии приложения не существует);
- **существующая БД** — только один из двух путей
  [`STAGE_5C_DEPLOYMENT.md`](STAGE_5C_DEPLOYMENT.md): путь A (остановить
  writer-юниты, мигрировать, поднять) или путь B (поэтапный rollout без простоя).
  Путь A автоматизирован в `deploy.sh` — он сам останавливает писателей,
  спрашивает подтверждение и падает при ошибке Alembic.

Обязательные maintenance-таймеры (`mindcare-complete-group-sessions.timer`,
`mindcare-extend-schedules.timer`) ставит тот же `deploy.sh`; вручную — по
разделу «Обязательные maintenance-job'ы» того же runbook.

## Maintenance-таймеры: что включается само, а что нет

`deploy.sh` **устанавливает** все maintenance-юниты безусловно — отсутствие
любого unit-файла прерывает деплой. А вот **активируются** они по-разному:

| Таймер | Периодичность | Активация | Почему |
|---|---|---|---|
| `mindcare-complete-group-sessions.timer` | каждые 10 мин | автоматически | read-пути больше не мутируют данные |
| `mindcare-extend-schedules.timer` | ежедневно 03:20 | автоматически | иначе расписание обрывается по `effective_until` |
| `mindcare-ensure-audit-partitions.timer` | ежемесячно 1-го, 04:00 | автоматически | только создаёт будущие партиции, ничего не удаляет |
| `mindcare-anonymize-ips.timer` | ежедневно 03:40 | **вручную** | первый прогон **необратим** |

Анонимизация IP — единственный job, у которого установка отделена от
активации. `Persistent=true` + `enable --now` запустили бы первый прогон
немедленно, до dry-run; обнулённые `ip_address` не восстанавливает ни
`alembic downgrade`, ни повторный запуск.

Порядок ввода в эксплуатацию (подробно — в
[`STAGE_7_DEPLOYMENT.md`](STAGE_7_DEPLOYMENT.md)):

```bash
cd mindcare_api
.venv/bin/python scripts/anonymize_old_ips.py --days 90 --dry-run  # объём
.venv/bin/python scripts/anonymize_old_ips.py --days 90            # необратимо
sudo systemctl enable --now mindcare-anonymize-ips.timer           # только теперь
```

Если dry-run и ручной прогон уже выполнялись, таймер можно включить сразу при
развёртывании: `./deploy.sh --enable-ip-anonymization`.

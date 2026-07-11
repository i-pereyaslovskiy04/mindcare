# Демо-стенд MindCare (локальная сеть)

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
Новые миграции применять как обычно: `cd mindcare_api && alembic upgrade head`.

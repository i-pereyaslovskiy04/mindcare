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
>
> **ADR-029:** повторная доставка system-сообщений (outbox
> `system_message_intents`: приглашение подтвердить статус студента ДонГУ и
> результат решения по заявке) — `mindcare-deliver-system-messages.timer`
> (каждые 5 минут, `scripts/deliver_system_message_intents.py`). `deploy.sh`
> устанавливает и **включает** его сразу: job идемпотентен (event_key), только
> публикует уже зафиксированные намерения и ничего не удаляет. Exit 1 (ошибка
> чтения outbox, публикации или отметки) поднимает
> `mindcare-maintenance-failure@`. Ручной запуск:
> `cd mindcare_api && .venv/bin/python scripts/deliver_system_message_intents.py [--dry-run] [--limit N]`.

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

## Вход через Яндекс ID (Stage Social Auth 3A)

> Вход и регистрация через Яндекс реализованы (Stage 3A/3B/4, ADR-026/027):
> новая identity проходит быструю регистрацию (email и имя — из профиля
> Яндекса, права `login:email login:info`; пользователь вводит только код из
> письма и отмечает согласие), известная — сразу входит. Stage 4 миграций не
> добавляет. В приложении Яндекс OAuth должны быть включены права на email и
> на имя/профиль.
> ⚠ В production включать только после выполнения условий ниже (HTTPS,
> маскировка query callback на прокси, trusted proxy, PROD-приложение,
> верификация сервиса) и живой проверки. Регистрация шлёт письмо с кодом —
> нужен рабочий `EMAIL_MODE=smtp`. Allowlist доменов к регистрации через
> Яндекс не применяется (ADR-027 п. 5) — только к обычной. Привязки к
> уже существующему аккаунту нет (Stage 5): такой пользователь входит по
> email и паролю.

Перед первым запуском кода Stage 3A — `alembic upgrade head` (ревизия
`b8d2f6a3c9e4`, `auth_log.auth_method`). Без миграции новые строки `auth_log`
не запишутся (журнал auth — soft-fail: вход работает, аудит теряется).

Настройки (`mindcare_api/.env`, не в git):

| Переменная | Значение |
|---|---|
| `YANDEX_OAUTH_ENABLED` | `true` — включить; по умолчанию `false` |
| `YANDEX_OAUTH_CLIENT_ID` | ClientID приложения Яндекс OAuth **этого** окружения |
| `OAUTH_CALLBACK_BASE_URL` | `https://<домен>` (dev: `http://localhost:8000`) |
| `OAUTH_FRONTEND_CALLBACK_URL` | `https://<домен>/auth/callback` (dev: `http://localhost:3000/auth/callback`) |

- **client_secret не используется** и в `.env` не добавляется: PKCE S256 +
  `code_verifier`. Адреса Яндекса зашиты в адаптер.
- Redirect URI приложения Яндекс OAuth должен **точно** совпадать с
  `{OAUTH_CALLBACK_BASE_URL}/api/auth/oauth/yandex/callback` (схема, хост,
  порт, путь). Один Redirect URI на приложение: при неточном совпадении Яндекс
  молча подставляет первый зарегистрированный. Фактический `redirect_uri`
  backend пишет в лог при старте (`Yandex ID login enabled (redirect_uri=…)`).
- DEV и PROD — **разные** приложения Яндекс OAuth (свой ClientID и Redirect
  URI); ClientID боевого приложения в dev `.env` не попадает. Права приложения —
  «Адрес электронной почты» (`login:email`).
- Неполная конфигурация (нет ClientID, `http://` не на localhost, URL с
  userinfo/fragment) — адаптер **не** регистрируется, в логе ERROR без
  значений, MindCare стартует как обычно; `/api/auth/oauth/yandex/*` → 404.

Обязательные условия публичного (не localhost) включения:

1. HTTPS (TLS-терминатор/reverse proxy) — `OAUTH_CALLBACK_BASE_URL` с
   `https://` включает `Secure` у state-cookie.
2. Access log прокси **не** пишет query `/api/auth/oauth/*/callback`
   (там authorization code и state): например `$uri` вместо `$request`/
   `$request_uri` в `log_format` либо `access_log off` для этого location.
   Uvicorn маскирует его сам (`app/core/log_redaction.py`), прокси — нет.
3. SPA и `/api` — один сайт (лучше один origin, как в demo-режиме):
   state-cookie `SameSite=Lax` от `POST /oauth/yandex/start`.
4. Trusted proxy (`--proxy-headers --forwarded-allow-ips=<IP прокси>`): иначе
   rate limit `oauth_*:ip` общий для всех и IP в аудите — адрес прокси.
5. Верификация сервиса в Яндекс ID — иначе пользователи видят предупреждение
   перед выдачей доступа (технически вход работает).

## Вход и регистрация через VK ID (Stage Social Auth VK-1A/VK-1B)

> Вход по привязанной VK identity — сразу, без кода. Новая identity проходит
> регистрацию с шагом email (ADR-030): VK может не вернуть адрес, поэтому
> пользователь подтверждает или указывает его сам; адрес проходит тот же
> allowlist доменов, что обычная регистрация, и подтверждается кодом MindCare.
> Регистрация шлёт письмо — нужен рабочий `EMAIL_MODE=smtp`. Привязки к
> существующему аккаунту по email нет. Mail.ru и QR внутри VK ID — тот же
> провайдер `vk`. Миграций нет.

Настройки (только в локальном `.env`, в git не коммитить):

```
VK_OAUTH_ENABLED=true
VK_OAUTH_CLIENT_ID=<ID приложения VK ID>
VK_OAUTH_CALLBACK_BASE_URL=http://localhost
```

Защищённый ключ и сервисный ключ приложения VK **не нужны** и никуда не
добавляются: публичный клиент, OAuth 2.1 Authorization Code + PKCE.

Доверенный Redirect URL приложения VK должен точно совпадать с
`{VK_OAUTH_CALLBACK_BASE_URL}/api/auth/oauth/vk/callback`. Если
`VK_OAUTH_CALLBACK_BASE_URL` пуст, берётся общий `OAUTH_CALLBACK_BASE_URL`.
Схема (`http`/`https`) обеих баз обязана совпадать.

### DEV: callback на порту 80

**Почему порт 80.** VK ID принимает `localhost` в доверенном Redirect URL
только на стандартных портах: `http://localhost` (порт 80) либо
`https://localhost` (порт 443); другие localhost-порты VK ID не поддерживает.
Поэтому DEV-приложение VK зарегистрировано на
`http://localhost/api/auth/oauth/vk/callback`, хотя основной backend слушает
`:8000` (на него же настроен Яндекс). Dev reverse proxy в репозитории нет,
поэтому callback принимает второй экземпляр того же backend на порту 80 — та
же БД и тот же `.env`.

**Запускать его вручную не нужно.** DEV-launcher'ы поднимают listener сами:

| Launcher | Где живёт listener `:80` | Как останавливается |
|----------|--------------------------|---------------------|
| `.\start.ps1` (Windows) | в окне backend, вместе с `:8000` (заголовок окна «Backend :8000 + VK callback :80 (dev)») | Ctrl+C или закрытие окна backend гасят оба экземпляра; если основной backend завершился сам, listener гасится следом |
| `./start.sh` (Linux) | фоном, лог `logs/vk-callback.log`, PID `logs/vk-callback.pid` | той же командой `kill …`, что backend и frontend (скрипт печатает её в конце) |

Listener запускается, только когда локальный `.env` этого требует:
`VK_OAUTH_ENABLED=true` и `VK_OAUTH_CALLBACK_BASE_URL=http://localhost` (http,
loopback, порт 80). Решение принимает
`mindcare_api/scripts/dev_oauth_callback_port.py`: печатает номер порта либо
ничего; значения настроек он не выводит. В остальных случаях (VK выключен,
своя база не задана, база — https-адрес) launcher пишет «listener не нужен» и
стартует как раньше. Listener слушает только `127.0.0.1` и работает с
`--reload`, как основной backend, поэтому оба экземпляра всегда на одном коде.

Если порт 80 недоступен, launcher предупреждает и продолжает запуск без
listener (вход через VK локально работать не будет):

- Windows: порт обычно свободен и прав администратора не требует; занять его
  может IIS, другой веб-сервер или забытый ручной `uvicorn --port 80`;
- Linux: порты ниже 1024 требуют привилегий (root, `CAP_NET_BIND_SERVICE` либо
  `net.ipv4.ip_unprivileged_port_start`); launcher их не меняет.

`scripts/mindcare-mode.sh dev` (dev-режим на общем стенде) listener не
поднимает: там браузер работает не с `localhost` стенда.

Основной backend на `:8000` и фронтенд на `:3000` работают как обычно: `start`
уходит через прокси фронтенда на `:8000`, VK возвращает браузер на
`http://localhost/...` (порт 80), state-cookie привязан к хосту `localhost` без
порта и приходит на оба экземпляра, state и ticket лежат в общей БД.

Чего здесь нет намеренно: приложение само второй сервер не запускает (никакого
subprocess в FastAPI lifespan — это давало бы дубли при `--reload`, нескольких
воркерах и в тестах), отдельного пользовательского скрипта запуска для VK нет.

**Production этот механизм не использует.** `deploy.sh` и systemd-юниты
launcher'ы и helper не вызывают; обе базы callback там — один https-адрес
сайта, callback обслуживает обычный HTTPS reverse proxy, отдельный Uvicorn на
`:80` не нужен.

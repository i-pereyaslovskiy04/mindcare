# Развёртывание Stage 7 (IP-анонимизация и обслуживание audit-партиций)

Ревизия: **`c8e2b5f7a3d1`** (`adopt_ip_anonymization`), от `d4a7b2c9f6e1`.

## Что именно меняется

Документация проекта обещала 90-дневную анонимизацию IP, но на стенде,
развёрнутом через Alembic, её **не происходило вообще**: функция
`anonymize_old_ips()` жила только в legacy bootstrap-SQL (`db/sql/`), не входила
в Alembic-цепочку, не имела ни одного consumer'а и ни одного планировщика.

Stage 7 закрывает этот разрыв:

| Объект | Что это |
|---|---|
| `public.anonymize_old_ips(integer) RETURNS bigint` | обнуляет `ip_address` старше границы в `audit_log` / `auth_log` / `data_change_log` |
| `public.count_old_ips(integer) RETURNS bigint` | строго read-only счётчик тех же строк (основа честного dry-run) |
| `mindcare_api/scripts/anonymize_old_ips.py` | CLI-consumer обеих функций |
| `mindcare-anonymize-ips.timer` | ежедневный прогон — **по умолчанию НЕ активируется** |
| `mindcare-ensure-audit-partitions.timer` | ежемесячное создание будущих партиций |

**Чего Stage 7 НЕ делает:** не удаляет строки журналов, не удаляет и не
отцепляет партиции, не трогает `user_sessions` / `consent_records` /
`user_legal_basis_records`, не меняет источник IP (`request.client.host`) и не
вводит доверенные прокси. Всё это — отдельные вопросы, часть из них требует
решения DPO (см. `docs/BACKLOG.md`).

---

## ⚠ Первый прогон необратим

`alembic downgrade` возвращает **механизм, но не данные**: строки, у которых
`ip_address` уже обнулён, восстановлению не подлежат.

Поэтому установка таймера отделена от его активации:

- `deploy.sh` **устанавливает** `mindcare-anonymize-ips.{service,timer}`, но
  **не включает** таймер;
- `Persistent=true` + `enable --now` запустили бы первый прогон немедленно — до
  dry-run и до того, как оператор увидел объём;
- интерактивного подтверждения внутри job быть не может (`Type=oneshot`, stdin
  недоступен), поэтому решение принимает оператор **до** активации;
- флаг `./deploy.sh --enable-ip-anonymization` включает таймер сразу — только
  если dry-run и ручной прогон уже выполнялись.

`mindcare-ensure-audit-partitions.timer` включается автоматически: он только
создаёт недостающие будущие партиции, ничего не удаляет и не изменяет.

---

## Порядок ввода в эксплуатацию

Четыре различных режима — не смешивать.

### A. Штатный `deploy.sh` (без флага)

Порядок задан самим скриптом и не является выбором оператора: ШАГ 5
(`alembic upgrade head`) выполняется до ШАГ 8 (systemd).

```bash
./deploy.sh
```

1. Выкладывается код, применяется миграция, ставятся все maintenance-юниты.
2. `mindcare-ensure-audit-partitions.timer` включается автоматически.
3. `mindcare-anonymize-ips.timer` установлен, но **не активирован**; скрипт
   печатает инструкцию к режиму C.

**Сама ревизия Stage 7 downtime не требует.** Её DDL — `DROP`/`CREATE FUNCTION`
плюс `REVOKE`, таблицы не блокируются, приложение эти функции не вызывает.

Но фактическое поведение `deploy.sh` на ШАГ 5 зависит не от Stage 7, а от
состояния схемы стенда **в целом**:

- **новая пустая БД** — миграции (включая Stage 7) применяются напрямую,
  простой не нужен: старой версии приложения, которая могла бы писать в окно
  между ревизиями, не существует;
- **схема уже на head** — `alembic upgrade head` для Stage 7 не делает ничего,
  простой не нужен;
- **существующая БД позади head на любую ревизию** (не обязательно именно
  Stage 7 — это может быть накопленный разрыв в несколько миграций) —
  `deploy.sh` идёт по общему гарантированному downtime-пути Stage 5C («путь A»):
  запрашивает подтверждение, **временно останавливает writer-юниты**
  (`mindcare-api`, `mindcare-demo`), применяет все недостающие миграции разом,
  поднимает писателей обратно. Это общее поведение скрипта для любого разрыва
  ревизий, а не специфика Stage 7; подробности — в
  [`STAGE_5C_DEPLOYMENT.md`](STAGE_5C_DEPLOYMENT.md).

Стенд, который применяет Stage 7 отдельной командой сразу после того, как
schema была ровно на `d4a7b2c9f6e1`, всё равно пройдёт через эту же ветку
`deploy.sh` (разрыв в одну ревизию — такой же «существующая БД позади head»,
как разрыв в десять) и получит кратковременную остановку писателей. Избежать
её можно только применив миграцию напрямую (`alembic upgrade head`, режим B
ниже) вне `deploy.sh`, на свой риск относительно совместимости версий кода.

### B. Ручной staged rollout (стенд без `deploy.sh`)

```bash
# 1. Выложить код. До миграции CLI завершится exit 1 с phase=missing_function.
# 2. Применить ревизию:
cd mindcare_api && .venv/bin/alembic upgrade head

# 3. Установить юниты:
cd /media/data2/psycho/mindcare
sudo cp deploy/mindcare-anonymize-ips.service \
        deploy/mindcare-anonymize-ips.timer \
        deploy/mindcare-ensure-audit-partitions.service \
        deploy/mindcare-ensure-audit-partitions.timer \
        deploy/mindcare-maintenance-failure@.service \
        /etc/systemd/system/
sudo systemctl daemon-reload

# 4. Партиции — можно включать сразу:
sudo systemctl enable --now mindcare-ensure-audit-partitions.timer

# 5. Анонимизацию ПОКА НЕ включать → режим C.
```

> Юниты в репозитории захардкожены под референсный стенд
> (`/media/data2/psycho/mindcare`, `User=vitbo`). При ручном копировании
> подставьте фактические путь и пользователя — `deploy.sh` делает это `sed`'ом
> автоматически.

### C. Первый (необратимый) прогон анонимизации

Выполняется **вручную, вне systemd, без таймаута**.

```bash
cd /media/data2/psycho/mindcare/mindcare_api

# 1. Узнать объём. count_old_ips — read-only: без advisory lock, без write
#    locks и мутации, без WAL-записей данных. Обычные PostgreSQL read-locks
#    (AccessShareLock на сканируемые таблицы) при этом возникают — это
#    штатное поведение любого SELECT, а не блокировка в смысле job'а.
.venv/bin/python scripts/anonymize_old_ips.py --days 90 --dry-run
echo "exit=$?"

# 2. Оценить affected_rows. При большом объёме — выбрать окно низкой нагрузки.

# 3. Live-прогон. НЕОБРАТИМО.
.venv/bin/python scripts/anonymize_old_ips.py --days 90
echo "exit=$?"

# 4. Проверка: повторный dry-run должен дать ~0.
.venv/bin/python scripts/anonymize_old_ips.py --days 90 --dry-run

# 5. Только теперь — активировать таймер:
sudo systemctl enable --now mindcare-anonymize-ips.timer
```

**Шаг 5 (bloat).** Массовый первый прогон переписывает кортежи старых партиций:
растут WAL и число dead tuples. `VACUUM` и `REINDEX` из job **не запускаются
никогда** — это решение оператора **по результатам замера**, а не обязательный
шаг:

```sql
-- сначала измерить
SELECT relname, n_dead_tup, n_live_tup
  FROM pg_stat_all_tables
 WHERE relname LIKE 'audit_log_%'
    OR relname LIKE 'auth_log_%'
    OR relname LIKE 'data_change_log_%'
 ORDER BY n_dead_tup DESC LIMIT 20;
```

`idx_auth_ip` и `idx_auth_failures` содержат `ip_address`, поэтому массовое
обнуление оставляет в них мёртвые записи. `REINDEX` осмыслен только если замер
это подтверждает.

### D. Последующие автоматические прогоны

Ежедневно 03:40 ±15 мин. Объём — однодневный срез строк, пересёкших границу,
то есть единицы секунд. Мониторинг — `systemctl is-failed` +
`OnFailure=mindcare-maintenance-failure@`.

---

## Периодичность и таймауты

| Юнит | Периодичность | Таймаут | Активация |
|---|---|---|---|
| `mindcare-anonymize-ips.timer` | ежедневно 03:40, `RandomizedDelaySec=15min` | 1800 с | **только вручную / `--enable-ip-anonymization`** |
| `mindcare-ensure-audit-partitions.timer` | ежемесячно 1-го, 04:00 | 600 с | автоматически |

03:40 выбрано **после** `mindcare-extend-schedules.timer` (03:20), чтобы два
maintenance-job'а не пересекались. Advisory-ключи у них тоже разные — общий
ключ заставил бы независимые job'ы блокировать друг друга.

> **Про `TimeoutStartSec=1800`.** По таймауту systemd шлёт SIGTERM, соединение
> рвётся, PostgreSQL откатывает **всю** транзакцию: работа выполняется и
> выбрасывается, и так на каждом тике. Значение корректно для установившегося
> режима; патологический объём существует ровно один раз — в режиме C, который
> идёт вне systemd.
>
> Если тик когда-либо упрётся в таймаут — **не поднимать значение вслепую**.
> Это сигнал аномалии (простой таймера, скачок объёма). Порядок: остановить
> таймер, разобрать backlog ручным прогоном, вернуть таймер.

---

## Мониторинг и health-check

SQL-проверки запускаются **от имени service DB-role** — тем же `DATABASE_URL`,
которым пользуется CLI. Запуск от другой роли проверяет чужие права и даёт
ложный результат.

```bash
systemctl list-timers 'mindcare-*'
systemctl is-failed mindcare-anonymize-ips.service
systemctl is-failed mindcare-ensure-audit-partitions.service
journalctl -u mindcare-anonymize-ips.service -n 50
```

Убедиться, что таймер анонимизации активен **только если** его включали
осознанно:

```bash
systemctl is-enabled mindcare-anonymize-ips.timer   # disabled — норма до режима C
```

Права на функции (обе должны вернуть `t`):

```sql
SELECT has_function_privilege(current_user,
       'public.anonymize_old_ips(integer)', 'EXECUTE');
SELECT has_function_privilege(current_user,
       'public.count_old_ips(integer)', 'EXECUTE');
```

Партиции на текущий и ближайшие три календарных месяца — по всем трём
partitioned parent'ам разом. Read-only; отсутствие ожидаемой партиции видно
как отдельная строка с `NULL` в `actual_partition`/`bound`, а не молча
пропадает из выборки:

```sql
WITH parents(parent) AS (
    VALUES ('audit_log'), ('auth_log'), ('data_change_log')
), existing AS (
    SELECT p.relname AS parent, c.relname AS partition,
           pg_get_expr(c.relpartbound, c.oid) AS bound
      FROM pg_inherits i
      JOIN pg_class c ON c.oid = i.inhrelid
      JOIN pg_class p ON p.oid = i.inhparent
      JOIN pg_namespace n ON n.oid = p.relnamespace
     WHERE n.nspname = 'public'
), expected AS (
    SELECT pt.parent,
           pt.parent || '_' || to_char(
               date_trunc('month', now()) + (n || ' months')::interval,
               'YYYY_MM'
           ) AS expected_partition
      FROM parents pt CROSS JOIN generate_series(0, 3) AS n
)
SELECT e.parent, e.expected_partition,
       ex.partition AS actual_partition, ex.bound
  FROM expected e
  LEFT JOIN existing ex
         ON ex.parent = e.parent AND ex.partition = e.expected_partition
 ORDER BY e.parent, e.expected_partition;
```

12 строк (3 таблицы × 4 месяца). Любая с `actual_partition IS NULL` — партиция
не создана; при исправно работающем `mindcare-ensure-audit-partitions.timer`
(запас `--months-ahead 24`) такого не бывает вплоть до истечения запаса.

Наутро после прогона счётчик должен быть около нуля:

```sql
SELECT public.count_old_ips(90);
```

---

## Диагностика намеренно минимизирована

В journal и в `mindcare_api/logs/maintenance/anonymize_old_ips_<ts>.log`
попадают только фаза и **класс** исключения. `str(exc)`, SQL, `DATABASE_URL`,
имена ролей, id и сами IP-адреса **не логируются**.

Формат строк:

```
[config] mode=live days=90
[result] mode=live days=90 affected_rows=1234
[error]  phase=insufficient_table_privilege error=PhaseError
```

Стабильные фазы отказа — оператор различает причины **по `phase`**, а не по
тексту:

| phase | Что произошло |
|---|---|
| `config` | некорректный `--days` (< 1) либо сбой настройки логирования — до подключения к БД |
| `connect` | не удалось создать engine или открыть транзакцию |
| `missing_function` | миграция `c8e2b5f7a3d1` не накачена |
| `insufficient_function_privilege` | у роли нет `EXECUTE` на функциях |
| `insufficient_table_privilege` | `EXECUTE` есть, но нет прав на сами журналы (`SECURITY INVOKER`) |
| `count` / `anonymize` | сбой самой рабочей функции |

---

## Модель привилегий

Функции объявлены `SECURITY INVOKER`, поэтому `EXECUTE` — лишь право **войти**
в функцию: `SELECT`/`UPDATE` внутри тела выполняются с правами вызывающей роли.
Доступ определяется двумя независимыми слоями.

**Слой 1 — ACL функций (управляется миграцией):**

| Grantee | EXECUTE | Механизм |
|---|---|---|
| владелец = роль, выполнившая миграцию | ✅ | владение объектом |
| `PUBLIC` | ❌ | `REVOKE ALL … FROM PUBLIC` |
| роль с уцелевшим legacy-`GRANT` | ❌ | ревизия делает `DROP`+`CREATE`, а не `CREATE OR REPLACE` — `proacl` обнуляется |

**Слой 2 — табличные права вызывающей роли (миграцией НЕ выдаются):**

| Операция | Что требуется |
|---|---|
| `count_old_ips` (dry-run) | `SELECT` на `created_at` и `ip_address` трёх журналов |
| `anonymize_old_ips` (live) | то же плюс `UPDATE(ip_address)` |

**Поддерживаемый контракт развёртывания — одна роль.** `deploy.sh` пишет
единственный `DATABASE_URL` в `mindcare_api/.env`; Alembic (`alembic/env.py`) и
CLI (`scripts/*.py`) читают то же поле. Эта роль владеет и функциями, и
журналами, поэтому оба слоя удовлетворены автоматически.

**Split-role deployment (migration-role ≠ maintenance-role) Stage 7 не
поддерживает** — до отдельного security-design этапа. Выдать «только EXECUTE»
недостаточно: без табличных прав прогон упадёт в рантайме с
`insufficient_table_privilege`. Полный least-privilege рецепт требует проверки
на живом PostgreSQL того, как привилегии, выданные на partitioned parent,
распространяются на дочерние партиции — включая созданные позже
`ensure_audit_partitions.py`. `PUBLIC EXECUTE` как обходной путь запрещён;
`SECURITY DEFINER` молча не вводится.

---

## Откат

```bash
sudo systemctl disable --now mindcare-anonymize-ips.timer
cd mindcare_api && .venv/bin/alembic downgrade d4a7b2c9f6e1
```

`downgrade` — **strict**: `DROP FUNCTION` без `IF EXISTS` и без `CASCADE`.
Отсутствие одной из функций уронит миграцию, а не замаскируется под успех;
транзакционный DDL при этом откатит и уже выполненный `DROP`, поэтому
`alembic_version` не сдвинется.

Round-trip **намеренно неполный**: legacy-тело функции не восстанавливается.
Оно содержало дефект — при `days_old <= 0` граница уходила в будущее и
обнулялись **все** `ip_address`, включая свежие; при `NULL` функция молча
ничего не делала. Возврат такого варианта не является операционной процедурой.

> ⚠ **Откат возвращает механизм, но не данные.** Уже обнулённые `ip_address`
> восстановлению не подлежат.

---

## Связанные документы

- [`STAGE_5C_DEPLOYMENT.md`](STAGE_5C_DEPLOYMENT.md) — обязательные
  maintenance-таймеры Stage 5C и порядок миграций `a1c4e8b2f7d3` / `b5d7f0a3c9e1`
- `docs/BACKLOG.md` — открытые решения DPO: retention журналов, DROP старых
  партиций, `user_sessions` / `consent_records` / `user_legal_basis_records`,
  доверенные прокси

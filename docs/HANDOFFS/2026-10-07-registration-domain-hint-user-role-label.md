# Handoff (2026-10-07): понятный отказ по домену при регистрации по email и подпись роли «Пользователь»

Решения — **ADR-019** (дополнение 2026-10-07) и **ADR-027** п. 5 (регистрация через
Яндекс от allowlist освобождена). Правила — `mindcare_api/CLAUDE.md` (блок про
allowlist). Схема БД и миграции не менялись, audit REGISTRY — 115.

## Главное

- **Один текст на init и confirm** (422): «Для регистрации по электронной почте
  используйте адрес с одним из разрешённых доменов: @a, @b.» Список — активные
  домены из БД на момент отказа, в коде их нет. Нет активных — «Регистрация по
  электронной почте сейчас недоступна. Обратитесь в поддержку.» Домен отключили
  между init и confirm — тот же текст, OTP цел, пользователь не создан.
- **Подсказка формы:** «Разрешённые домены: @a, @b» под полем Email из публичного
  `GET /api/public/email-domains`. Нет списка или запрос упал — подсказки нет,
  форма работает; список её не блокирует (решает backend). Placeholder email во
  всех трёх формах (регистрация, вход, восстановление пароля) — «Введите email».
- **Роль `student` в UI — «Пользователь»** (общая карта `shared/lib/roles.js`).
  Код роли, маршруты `/student`, membership и permissions прежние.
- **Яндекс не менялся:** тексты и подсказка говорят о регистрации «по электронной
  почте», а не о любой регистрации.

## Backend

| Файл | Что |
|---|---|
| `email_domains/errors.py` | `EmailDomainNotAllowedError(message, allowed_domains=())` |
| `email_domains/storage.py` | `list_active_domain_names()`; in-tx проверка читает список только в ветке отказа (без блокировок); FOR SHARE, точное сравнение, rollback без consume OTP прежние |
| `email_domains/service.py` | `assert_email_domain_allowed` (имя и сигнатура прежние) прикладывает список; `registration_domain_message`, `list_public_domains` |
| `email_domains/routes_public.py`, `schemas.py`, `main.py` | `GET /api/public/email-domains` → `{"domains": [...]}`: имена активных по возрастанию, `no-store`, без auth и аудита |
| `auth/service.py` | `_domain_not_allowed_error` — общий для init и confirm (confirm: `domain_not_allowed`) |

В `/api/public/config` список не добавлялся: ответ без БД, ключи закреплены тестом.

## Frontend

- `roles.js` — метка; общую карту берут chooser, switcher, профиль, badges,
  фильтры. Дубли убраны: `SettingsPage` (локальный `ROLE_LABEL`), `UsersFilters`,
  `GroupSessionsPage`, `StudentHome` (fallback имени).
- `api/domains.api.js` + `features/auth/hooks/useAllowedEmailDomains.js` — «побеждает
  последний запрос»: запоздавший ответ (в т.ч. после `refetch`, в StrictMode) не
  перезаписывает свежий список. `RegisterForm` после 422 перечитывает список.

## Audit impact

Новых событий и DCL нет. `registration_failed/domain_not_allowed` на confirm как
был; ранний отказ init не аудируется; публичное чтение журналов не пишет. Введённый
email не попадает в ответ и `app.*`-логи (тесты).

## Не менялось

Политика Яндекса; admin CRUD allowlist; тексты отказов admin-/supervisor-created
flows; `/api/public/config`; `roles.display_name` в `db/seed.py` (API не отдаёт);
«студент» как контент у психолога/супервизора; подписи событий аудита.

## Тесты

Backend `..\test.ps1` (изолированная БД): 3666 passed / 79 skipped (было 3624 / 79);
unit-only 2283 / 1. Frontend: 99 наборов / 1357 тестов (было 94 / 1306), lint, build
и `test:contrast` чистые. Яндекс — существующие `test_oauth_registration_flow.py`
без правок.

## Pending / риски

- Список доменов виден любому (в отказе и через endpoint) — по заданию; оценка
  раскрытия за владельцем продукта/DPO. Публичный GET без rate limit.
- В audit viewer «Пользователь» теперь и тип участника, и тип объекта, и роль
  `student` (фильтры «Тип участника» и «Роль действия»). Не менялось — решение
  за владельцем продукта.
- `guides/student_guide.md:38` («только домен вуза, `@donstu.ru`») и
  `guides/admin_guide.md` устарели; не менялись (md/docx/pdf).
- Подсказка может кратко отставать от БД; авторитетен текст ошибки сервера.
- Ручной browser smoke не выполнялся: рабочая БД не мигрирована до `d7e2a9c4f1b6`.

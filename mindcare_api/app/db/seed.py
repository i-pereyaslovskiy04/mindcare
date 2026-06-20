"""
Начальное заполнение (seed) базы данных.

Принципы:
  - Idempotent: повторный вызов ничего не дублирует (INSERT OR SKIP)
  - Minimal: только то, что нужно для старта приложения
  - Explicit: все данные задаются явно (никаких авто-генераций)

Что создаётся:
  1. Роли          — student, psychologist, admin, supervisor
  2. Permissions   — базовый набор по модулям (расширяемый)
  3. Привязки      — роль admin → все permissions
  4. Consents      — privacy_policy v1, data_processing v1, test_consent v1
                     (обязательны для работы register_confirm)

Вызывается из init_db.py → init_db().
"""

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# ─── Данные ───────────────────────────────────────────────────────────────────

_ROLES = [
    {
        "name":         "student",
        "display_name": "Студент",
        "description":  "Клиент психологической службы — студент университета",
        "is_system":    True,
    },
    {
        "name":         "psychologist",
        "display_name": "Психолог",
        "description":  "Штатный психолог-консультант",
        "is_system":    True,
    },
    {
        "name":         "admin",
        "display_name": "Администратор",
        "description":  "Полный доступ к административной панели",
        "is_system":    True,
    },
    {
        "name":         "supervisor",
        "display_name": "Супервизор",
        "description":  "Руководитель службы, доступ к отчётам и аудиту",
        "is_system":    True,
    },
]

_PERMISSIONS = [
    # ── auth ──────────────────────────────────────────────────────────────────
    {"code": "auth:view_logs",       "module": "auth",          "description": "Просмотр журнала аутентификации"},
    # ── users ─────────────────────────────────────────────────────────────────
    {"code": "users:list",           "module": "users",         "description": "Список пользователей"},
    {"code": "users:create",         "module": "users",         "description": "Создание пользователя"},
    {"code": "users:update",         "module": "users",         "description": "Редактирование пользователя"},
    {"code": "users:delete",         "module": "users",         "description": "Мягкое удаление пользователя"},
    {"code": "users:view_any",       "module": "users",         "description": "Просмотр любого профиля"},
    # ── appointments ──────────────────────────────────────────────────────────
    {"code": "appointments:list",    "module": "appointments",  "description": "Список записей на консультацию"},
    {"code": "appointments:create",  "module": "appointments",  "description": "Запись на консультацию"},
    {"code": "appointments:cancel",  "module": "appointments",  "description": "Отмена записи"},
    {"code": "appointments:view_any","module": "appointments",  "description": "Просмотр чужих записей"},
    # ── tests ─────────────────────────────────────────────────────────────────
    {"code": "tests:list",           "module": "tests",         "description": "Список тестов"},
    {"code": "tests:take",           "module": "tests",         "description": "Прохождение теста"},
    {"code": "tests:manage",         "module": "tests",         "description": "Создание/редактирование тестов"},
    {"code": "tests:view_results_any","module": "tests",        "description": "Просмотр результатов любого пользователя"},
    # ── content ───────────────────────────────────────────────────────────────
    {"code": "content:manage",       "module": "content",       "description": "Управление статьями и новостями"},
    {"code": "content:publish",      "module": "content",       "description": "Публикация/снятие контента"},
    # ── notes ─────────────────────────────────────────────────────────────────
    {"code": "notes:create",         "module": "notes",         "description": "Создание заметок сессии"},
    {"code": "notes:view_own",       "module": "notes",         "description": "Просмотр своих заметок"},
    {"code": "notes:view_any",       "module": "notes",         "description": "Просмотр всех заметок"},
    # ── qa ────────────────────────────────────────────────────────────────────
    {"code": "qa:ask",               "module": "qa",            "description": "Задать вопрос"},
    {"code": "qa:answer",            "module": "qa",            "description": "Ответить на вопрос"},
    {"code": "qa:moderate",          "module": "qa",            "description": "Модерация Q&A"},
    # ── admin ─────────────────────────────────────────────────────────────────
    {"code": "admin:dashboard",      "module": "admin",         "description": "Доступ к панели администратора"},
    {"code": "admin:audit",          "module": "admin",         "description": "Просмотр журналов аудита"},
]

# Права, которые назначаем роли admin (все) и supervisor
_ADMIN_PERMISSIONS = [p["code"] for p in _PERMISSIONS]
_SUPERVISOR_PERMISSIONS = [
    "users:list", "users:view_any",
    "appointments:list", "appointments:view_any",
    "tests:view_results_any",
    "notes:view_any",
    "admin:dashboard", "admin:audit",
    "auth:view_logs",
]

_now = datetime.now(timezone.utc)

_CONSENTS = [
    {
        "policy_type":  "privacy_policy",
        "version":      1,
        "title":        "Политика конфиденциальности",
        "is_mandatory": True,
        "published_at": _now,
        "content": (
            "Настоящая Политика конфиденциальности регулирует порядок обработки "
            "персональных данных пользователей платформы MindCare психологической "
            "службы Донецкого государственного университета.\n\n"
            "1. Оператор персональных данных: ФГБОУ ВО «Донецкий государственный "
            "университет», г. Донецк.\n"
            "2. Цель обработки: оказание психологической помощи и сопровождения "
            "студентов, ведение записей на консультации, проведение психодиагностики.\n"
            "3. Состав данных: ФИО, адрес электронной почты, телефон, учебная группа, "
            "факультет, результаты психодиагностических тестов.\n"
            "4. Хранение: данные хранятся на серверах в Российской Федерации.\n"
            "5. Передача третьим лицам: не осуществляется без согласия субъекта, "
            "за исключением случаев, предусмотренных законодательством РФ.\n"
            "6. Права субъекта: право на доступ, исправление и удаление данных "
            "в соответствии с ФЗ-152 «О персональных данных».\n"
            "7. Срок хранения: в течение обучения в университете и 3 лет после "
            "отчисления/окончания.\n"
            "8. Версия документа: 1.0 от 2024-01-01."
        ),
    },
    {
        "policy_type":  "data_processing",
        "version":      1,
        "title":        "Согласие на обработку персональных данных",
        "is_mandatory": True,
        "published_at": _now,
        "content": (
            "Настоящим я, субъект персональных данных, выражаю своё согласие на "
            "обработку моих персональных данных психологической службой Донецкого "
            "государственного университета (далее — Оператор) в соответствии с "
            "Федеральным законом № 152-ФЗ «О персональных данных».\n\n"
            "Я даю согласие на обработку следующих данных:\n"
            "— ФИО, адрес электронной почты, номер телефона;\n"
            "— учебная группа, курс, факультет;\n"
            "— результаты психодиагностических методик;\n"
            "— записи консультаций (дата, время, тема обращения).\n\n"
            "Цель обработки: организация психологической поддержки и сопровождения.\n"
            "Срок действия согласия: до момента его отзыва.\n"
            "Согласие может быть отозвано путём направления письменного заявления "
            "по адресу Оператора.\n\n"
            "Версия: 1.0 от 2024-01-01."
        ),
    },
    {
        "policy_type":  "test_consent",
        "version":      1,
        "title":        "Согласие на прохождение психодиагностики",
        "is_mandatory": True,
        "published_at": _now,
        "content": (
            "Настоящим я даю согласие на прохождение психодиагностического "
            "тестирования на платформе MindCare психологической службы Донецкого "
            "государственного университета и на обработку его результатов в "
            "соответствии с Федеральным законом № 152-ФЗ «О персональных данных».\n\n"
            "Я проинформирован(а), что:\n"
            "— результаты тестирования носят ориентировочный характер и не являются "
            "медицинским диагнозом;\n"
            "— результаты сохраняются в моём личном кабинете и могут быть "
            "использованы психологом службы для оказания помощи;\n"
            "— я могу отказаться от прохождения теста в любой момент.\n\n"
            "Цель обработки: психологическая диагностика и сопровождение.\n"
            "Срок действия согласия: до момента его отзыва.\n\n"
            "Версия: 1.0 от 2024-01-01."
        ),
    },
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _seed_roles(db) -> dict[str, int]:
    """
    Создаёт роли если их нет. Возвращает {name: id} для всех ролей.
    """
    from app.db.models.auth import Role

    role_ids: dict[str, int] = {}
    for data in _ROLES:
        existing = db.query(Role).filter(Role.name == data["name"]).first()
        if existing:
            role_ids[data["name"]] = existing.id
            log.debug("[SEED] Role '%s' already exists (id=%d)", data["name"], existing.id)
        else:
            role = Role(**data)
            db.add(role)
            db.flush()
            role_ids[data["name"]] = role.id
            log.info("[SEED] Created role '%s' (id=%d)", data["name"], role.id)

    return role_ids


def _seed_permissions(db) -> dict[str, int]:
    """
    Создаёт permissions если их нет. Возвращает {code: id}.
    """
    from app.db.models.auth import Permission

    perm_ids: dict[str, int] = {}
    for data in _PERMISSIONS:
        existing = db.query(Permission).filter(Permission.code == data["code"]).first()
        if existing:
            perm_ids[data["code"]] = existing.id
        else:
            perm = Permission(**data)
            db.add(perm)
            db.flush()
            perm_ids[data["code"]] = perm.id
            log.info("[SEED] Created permission '%s'", data["code"])

    return perm_ids


def _seed_role_permissions(
    db,
    role_ids: dict[str, int],
    perm_ids: dict[str, int],
) -> None:
    """
    Назначает permissions ролям admin и supervisor.
    Idempotent: пропускает уже существующие связи.
    """
    from app.db.models.auth import RolePermission
    from sqlalchemy.exc import IntegrityError

    assignments: list[tuple[str, list[str]]] = [
        ("admin",      _ADMIN_PERMISSIONS),
        ("supervisor", _SUPERVISOR_PERMISSIONS),
    ]

    for role_name, codes in assignments:
        role_id = role_ids.get(role_name)
        if not role_id:
            continue
        for code in codes:
            perm_id = perm_ids.get(code)
            if not perm_id:
                continue
            existing = (
                db.query(RolePermission)
                .filter(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == perm_id,
                )
                .first()
            )
            if not existing:
                try:
                    db.add(RolePermission(role_id=role_id, permission_id=perm_id))
                    db.flush()
                    log.debug("[SEED] %s → %s", role_name, code)
                except IntegrityError:
                    db.rollback()  # гонка при parallel startup — не критично


def _seed_consents(db) -> None:
    """
    Создаёт версии политик согласия если их нет.
    КРИТИЧЕСКИ ВАЖНО: без этих записей register_confirm вернёт HTTP 500.
    """
    from app.db.models.consents import Consent

    for data in _CONSENTS:
        existing = (
            db.query(Consent)
            .filter(
                Consent.policy_type == data["policy_type"],
                Consent.version == data["version"],
            )
            .first()
        )
        if existing:
            log.debug(
                "[SEED] Consent '%s' v%d already exists",
                data["policy_type"], data["version"],
            )
        else:
            db.add(Consent(**data))
            log.info(
                "[SEED] Created consent '%s' v%d", data["policy_type"], data["version"]
            )


# ─── Entry point ─────────────────────────────────────────────────────────────

def run_seed() -> None:
    """
    Запускает все seed-функции в одной транзакции.
    Idempotent: повторный вызов не создаёт дублей.
    При ошибке выполняет rollback и логирует — не роняет приложение
    (если базовые данные уже есть из предыдущего запуска).
    """
    from app.db.session import SessionLocal

    log.info("[SEED] Starting seed...")
    try:
        with SessionLocal() as db:
            role_ids = _seed_roles(db)
            perm_ids = _seed_permissions(db)
            _seed_role_permissions(db, role_ids, perm_ids)
            _seed_consents(db)
            db.commit()
        log.info("[SEED] Seed completed OK")
    except Exception as exc:
        log.error("[SEED] Seed failed: %s", exc, exc_info=True)
        # Не бросаем дальше: если таблицы уже заполнены из предыдущего запуска,
        # приложение продолжит работу. Если нет — проблемы всплывут при первом запросе.
        raise

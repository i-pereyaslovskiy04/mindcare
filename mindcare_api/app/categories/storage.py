import re
from typing import Optional

from sqlalchemy import func, select, asc
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.db.models import Category, ArticleCategory
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context


# ── slug helpers ──────────────────────────────────────────────────────────────

# str.maketrans с двумя строками требует одинаковой длины, что невозможно
# при многосимвольных транслитерациях (ж→zh, ш→sh и т.д.).
# Используем dict: ord(кириллица) → латиница.
_TRANSLIT = {
    'а': 'a',  'б': 'b',  'в': 'v',  'г': 'g',  'д': 'd',
    'е': 'e',  'ё': 'yo', 'ж': 'zh', 'з': 'z',  'и': 'i',
    'й': 'y',  'к': 'k',  'л': 'l',  'м': 'm',  'н': 'n',
    'о': 'o',  'п': 'p',  'р': 'r',  'с': 's',  'т': 't',
    'у': 'u',  'ф': 'f',  'х': 'kh', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'sch', 'ъ': '',  'ы': 'y',  'ь': '',
    'э': 'e',  'ю': 'yu', 'я': 'ya',
}


def _slugify(text: str) -> str:
    """
    Генерирует slug из названия:
    'Управление стрессом' → 'upravlenie-stressom'
    """
    parts = []
    for ch in text.lower():
        parts.append(_TRANSLIT.get(ch, ch))
    slug = re.sub(r"[^a-z0-9]+", "-", "".join(parts))
    slug = slug.strip("-")
    return slug or "category"


def _article_count_subquery():
    """
    Коррелированный подзапрос: кол-во активных материалов для каждой категории.
    Выполняется внутри основного SELECT — один запрос к БД.
    """
    return (
        select(func.count())
        .select_from(ArticleCategory)
        .where(ArticleCategory.category_id == Category.id)
        .correlate(Category)
        .scalar_subquery()
    )


def find_categories(
    page: int = 1,
    size: int = 50,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> tuple[list[dict], int]:
    """Возвращает (items, total) — пагинированный список категорий со счётчиком материалов."""
    article_count = _article_count_subquery()

    with SessionLocal() as db:
        query = db.query(
            Category,
            article_count.label("article_count"),
        )

        if search:
            query = query.filter(Category.name.ilike(f"%{search.strip()}%"))

        if is_active is not None:
            query = query.filter(Category.is_active.is_(is_active))

        total = query.count()

        results = (
            query
            .order_by(asc(Category.display_order), asc(func.lower(Category.name)))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = [
            {
                "id":            cat.id,
                "name":          cat.name,
                "slug":          cat.slug,
                "description":   cat.description,
                "display_order": cat.display_order,
                "is_active":     cat.is_active,
                "created_at":    cat.created_at,
                "article_count": ac,
            }
            for cat, ac in results
        ]

    return items, total


def get_category_by_id(category_id: int) -> Optional[dict]:
    """Возвращает одну категорию со счётчиком материалов или None."""
    article_count = _article_count_subquery()

    with SessionLocal() as db:
        row = (
            db.query(
                Category,
                article_count.label("article_count"),
            )
            .filter(Category.id == category_id)
            .first()
        )
        if not row:
            return None
        cat, ac = row

        return {
            "id":            cat.id,
            "name":          cat.name,
            "slug":          cat.slug,
            "description":   cat.description,
            "display_order": cat.display_order,
            "is_active":     cat.is_active,
            "created_at":    cat.created_at,
            "article_count": ac,
        }


def create_category(
    *,
    name: str,
    slug: Optional[str],
    description: Optional[str],
    display_order: int,
    is_active: bool,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Создаёт категорию. Slug генерируется из name если не передан.
    parent_id всегда None — иерархия не используется в текущем MVP.
    Raises ValueError при конфликте slug; RuntimeError при отсутствии actor.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "category create requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        raw_slug = slug.strip() if slug and slug.strip() else _slugify(name)

        # Проверяем уникальность slug; если занят — поднимаем ValueError (409)
        existing = db.query(Category.id).filter(Category.slug == raw_slug).scalar()
        if existing:
            raise ValueError(f"Slug «{raw_slug}» уже используется")

        cat = Category(
            name=name.strip(),
            slug=raw_slug,
            parent_id=None,
            description=description,
            display_order=display_order,
            is_active=is_active,
        )
        # Узкий try: ТОЛЬКО business INSERT+flush. IntegrityError здесь = дубль
        # slug → доменный ValueError (409). Audit staging/commit ВНЕ этого
        # обработчика — иначе IntegrityError самой audit-строки был бы ошибочно
        # преобразован в конфликт slug.
        try:
            db.add(cat)
            db.flush()   # id до commit — нужен Target
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Slug «{raw_slug}» уже используется")

        # ATOMIC audit в той же транзакции (db=db), после успешного business
        # flush, до commit. AuditError/AuditStorageError и любой IntegrityError
        # на commit всплывают и откатывают всю транзакцию (with-блок), НЕ
        # преобразуются в конфликт slug.
        record_event(
            event="category_created",
            actor=Actor.user(actor_id, actor_role),
            target=Target("category", cat.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(cat)

    return get_category_by_id(cat.id)


def update_category(
    category_id: int,
    data: dict,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Обновляет только переданные поля (exclude_unset семантика через dict).
    parent_id не принимается — иерархия не используется в текущем MVP.
    Raises ValueError при конфликте slug; RuntimeError при отсутствии actor.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "category update requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        cat = db.query(Category).filter(Category.id == category_id).first()
        if not cat:
            return None

        if "name" in data and data["name"] is not None:
            cat.name = data["name"].strip()

        if "slug" in data and data["slug"] is not None:
            new_slug = data["slug"].strip()
            if not new_slug:
                new_slug = _slugify(cat.name)
            conflict = db.query(Category.id).filter(
                Category.slug == new_slug,
                Category.id != category_id,
            ).scalar()
            if conflict:
                raise ValueError(f"Slug «{new_slug}» уже используется")
            cat.slug = new_slug

        if "description" in data:
            cat.description = data["description"]

        if "display_order" in data and data["display_order"] is not None:
            cat.display_order = data["display_order"]

        if "is_active" in data and data["is_active"] is not None:
            cat.is_active = data["is_active"]

        # Узкий try: ТОЛЬКО business flush → IntegrityError = конфликт данных
        # (доменный ValueError). Audit staging/commit ВНЕ обработчика.
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ValueError("Конфликт данных при сохранении")

        record_event(
            event="category_updated",
            actor=Actor.user(actor_id, actor_role),
            target=Target("category", cat.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()

    return get_category_by_id(category_id)


def deactivate_category(
    category_id: int,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """
    Soft delete: устанавливает is_active=False.
    Связи article_categories не трогаем — материалы остаются привязаны,
    но активная форма не предложит категорию при создании нового.
    Возвращает True если категория найдена, False если нет.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "category delete requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        cat = db.query(Category).filter(Category.id == category_id).first()
        if not cat:
            return False
        cat.is_active = False
        record_event(
            event="category_deleted",
            actor=Actor.user(actor_id, actor_role),
            target=Target("category", cat.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
    return True

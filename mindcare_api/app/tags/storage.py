import uuid as _uuid
from typing import Optional

from sqlalchemy import func, select, asc
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.db.models import Tag, ArticleTag, NewsTag, TestTag
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context


def _count_subqueries():
    """
    Три коррелированных подзапроса: кол-во статей, новостей и тестов для каждого тега.
    Выполняются внутри основного SELECT — один запрос к БД вместо N+1.
    """
    article_count = (
        select(func.count())
        .select_from(ArticleTag)
        .where(ArticleTag.tag_id == Tag.id)
        .correlate(Tag)
        .scalar_subquery()
    )
    news_count = (
        select(func.count())
        .select_from(NewsTag)
        .where(NewsTag.tag_id == Tag.id)
        .correlate(Tag)
        .scalar_subquery()
    )
    test_count = (
        select(func.count())
        .select_from(TestTag)
        .where(TestTag.tag_id == Tag.id)
        .correlate(Tag)
        .scalar_subquery()
    )
    return article_count, news_count, test_count


def find_tags(
    page: int = 1,
    size: int = 50,
    search: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Возвращает (items, total) — пагинированный список тегов со счётчиками."""
    article_count, news_count, test_count = _count_subqueries()

    with SessionLocal() as db:
        query = db.query(
            Tag,
            article_count.label("article_count"),
            news_count.label("news_count"),
            test_count.label("test_count"),
        )

        if search:
            query = query.filter(Tag.name.ilike(f"%{search.strip()}%"))

        total = query.count()

        results = (
            query
            .order_by(asc(func.lower(Tag.name)))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = [
            {
                "uuid":          str(tag.uuid),
                "name":          tag.name,
                "article_count": ac,
                "news_count":    nc,
                "test_count":    tc,
                "created_at":    tag.created_at,
            }
            for tag, ac, nc, tc in results
        ]

    return items, total


def get_tag_by_uuid(uuid: str) -> Optional[dict]:
    """Возвращает один тег со счётчиками или None."""
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        return None

    article_count, news_count, test_count = _count_subqueries()

    with SessionLocal() as db:
        row = (
            db.query(
                Tag,
                article_count.label("article_count"),
                news_count.label("news_count"),
                test_count.label("test_count"),
            )
            .filter(Tag.uuid == uuid_obj)
            .first()
        )
        if not row:
            return None
        tag, ac, nc, tc = row
        return {
            "uuid":          str(tag.uuid),
            "name":          tag.name,
            "article_count": ac,
            "news_count":    nc,
            "test_count":    tc,
            "created_at":    tag.created_at,
        }


def create_tag(
    name: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Создаёт тег. Проверяет уникальность через lower(name).
    Raises ValueError если тег с таким именем уже есть; RuntimeError без actor.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "tag create requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        existing = db.query(Tag).filter(
            func.lower(Tag.name) == name.lower()
        ).first()
        if existing:
            raise ValueError(f"Тег «{name}» уже существует")

        tag = Tag(name=name)
        # Узкий try: ТОЛЬКО business INSERT+flush → IntegrityError = дубль имени
        # (доменный ValueError). Audit staging/commit ВНЕ обработчика — иначе
        # IntegrityError самой audit-строки был бы преобразован в конфликт имени.
        try:
            db.add(tag)
            db.flush()   # id до commit — нужен Target
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Тег «{name}» уже существует")

        record_event(
            event="tag_created",
            actor=Actor.user(actor_id, actor_role),
            target=Target("tag", tag.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(tag)

        return {
            "uuid":          str(tag.uuid),
            "name":          tag.name,
            "article_count": 0,
            "news_count":    0,
            "test_count":    0,
            "created_at":    tag.created_at,
        }


def update_tag(
    uuid: str,
    name: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Переименовывает тег. Проверяет уникальность нового имени (исключая себя).
    Raises ValueError если тег не найден или имя занято; RuntimeError без actor.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "tag update requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        raise ValueError(f"Некорректный UUID: {uuid}")

    with SessionLocal() as db:
        tag = db.query(Tag).filter(Tag.uuid == uuid_obj).first()
        if not tag:
            raise ValueError("Тег не найден")

        conflict = db.query(Tag).filter(
            func.lower(Tag.name) == name.lower(),
            Tag.id != tag.id,
        ).first()
        if conflict:
            raise ValueError(f"Тег «{name}» уже существует")

        tag.name = name
        # Узкий try: ТОЛЬКО business flush → IntegrityError = дубль имени.
        # Audit staging/commit ВНЕ обработчика.
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Тег «{name}» уже существует")

        record_event(
            event="tag_updated",
            actor=Actor.user(actor_id, actor_role),
            target=Target("tag", tag.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()

    return get_tag_by_uuid(uuid)


def delete_tag(
    uuid: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """
    Удаляет тег физически. CASCADE в БД автоматически удаляет
    все записи в article_tags, news_tags, test_tags.
    Возвращает True если тег найден и удалён, False если не найден.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "tag delete requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        return False

    with SessionLocal() as db:
        tag = db.query(Tag).filter(Tag.uuid == uuid_obj).first()
        if not tag:
            return False
        tag_id = tag.id   # захватываем до физического удаления (Target)
        record_event(
            event="tag_deleted",
            actor=Actor.user(actor_id, actor_role),
            target=Target("tag", tag_id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.delete(tag)
        db.commit()

    return True


def find_tags_public(search: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Облегчённый список для autocomplete — только uuid и name."""
    with SessionLocal() as db:
        query = db.query(Tag)
        if search:
            query = query.filter(Tag.name.ilike(f"%{search.strip()}%"))
        tags = query.order_by(asc(func.lower(Tag.name))).limit(limit).all()
        return [{"uuid": str(t.uuid), "name": t.name} for t in tags]

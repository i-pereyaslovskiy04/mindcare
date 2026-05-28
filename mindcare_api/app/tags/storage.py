import uuid as _uuid
from typing import Optional

from sqlalchemy import func, select, asc
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.db.models import Tag, ArticleTag, NewsTag, TestTag


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


def create_tag(name: str) -> dict:
    """
    Создаёт тег. Проверяет уникальность через lower(name).
    Raises ValueError если тег с таким именем уже есть.
    """
    with SessionLocal() as db:
        existing = db.query(Tag).filter(
            func.lower(Tag.name) == name.lower()
        ).first()
        if existing:
            raise ValueError(f"Тег «{name}» уже существует")

        tag = Tag(name=name)
        try:
            db.add(tag)
            db.commit()
            db.refresh(tag)
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Тег «{name}» уже существует")

        return {
            "uuid":          str(tag.uuid),
            "name":          tag.name,
            "article_count": 0,
            "news_count":    0,
            "test_count":    0,
            "created_at":    tag.created_at,
        }


def update_tag(uuid: str, name: str) -> Optional[dict]:
    """
    Переименовывает тег. Проверяет уникальность нового имени (исключая себя).
    Raises ValueError если тег не найден или имя занято.
    """
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

        try:
            tag.name = name
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Тег «{name}» уже существует")

    return get_tag_by_uuid(uuid)


def delete_tag(uuid: str) -> bool:
    """
    Удаляет тег физически. CASCADE в БД автоматически удаляет
    все записи в article_tags, news_tags, test_tags.
    Возвращает True если тег найден и удалён, False если не найден.
    """
    try:
        uuid_obj = _uuid.UUID(uuid)
    except ValueError:
        return False

    with SessionLocal() as db:
        tag = db.query(Tag).filter(Tag.uuid == uuid_obj).first()
        if not tag:
            return False
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

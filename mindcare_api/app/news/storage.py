import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, asc, desc
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.db.models import News, NewsTag, Tag, User, MediaFile


# ── helpers ───────────────────────────────────────────────────────────────────

def _news_to_dict(news: News, db) -> dict:
    tags = (
        db.query(Tag)
        .join(NewsTag, NewsTag.tag_id == Tag.id)
        .filter(NewsTag.news_id == news.id)
        .all()
    )
    cover_url = None
    if news.cover_image:
        mf = db.query(MediaFile).filter(MediaFile.id == news.cover_image).first()
        if mf:
            cover_url = mf.file_path

    author_name = None
    if news.created_by:
        user = db.query(User).filter(User.id == news.created_by).first()
        if user:
            author_name = user.full_name

    return {
        "uuid":            str(news.uuid),
        "title":           news.title,
        "content":         news.content,
        "cover_image_url": cover_url,
        "tags":            [{"uuid": str(t.uuid), "name": t.name} for t in tags],
        "is_published":    news.is_published,
        "published_at":    news.published_at,
        "created_at":      news.created_at,
        "updated_at":      news.updated_at,
        "created_by_name": author_name,
    }


def _resolve_cover(uuid_str: Optional[str], db) -> Optional[int]:
    """Резолвит UUID обложки в integer FK или возвращает None."""
    if not uuid_str:
        return None
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None
    mf = db.query(MediaFile).filter(
        MediaFile.uuid == uuid_obj,
        MediaFile.is_active.is_(True),
    ).first()
    return mf.id if mf else None


def _sync_tags(news_id: int, tag_uuids: list[str], db) -> None:
    """Полностью заменяет теги новости."""
    db.query(NewsTag).filter(NewsTag.news_id == news_id).delete()
    for uuid_str in tag_uuids:
        try:
            uuid_obj = _uuid.UUID(uuid_str)
        except ValueError:
            continue
        tag = db.query(Tag).filter(Tag.uuid == uuid_obj).first()
        if tag:
            db.add(NewsTag(news_id=news_id, tag_id=tag.id))


# ── public API ────────────────────────────────────────────────────────────────

def find_news(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    is_published: Optional[bool] = None,
    public_only: bool = False,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        q = db.query(News).filter(News.deleted_at.is_(None))

        if public_only:
            q = q.filter(News.is_published.is_(True))
        elif is_published is not None:
            q = q.filter(News.is_published.is_(is_published))

        if search:
            q = q.filter(News.title.ilike(f"%{search.strip()}%"))

        total = q.count()
        news_list = (
            q.order_by(desc(News.created_at))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        items = [_news_to_dict(n, db) for n in news_list]

    return items, total


def get_news_by_uuid(uuid_str: str, public_only: bool = False) -> Optional[dict]:
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None

    with SessionLocal() as db:
        q = db.query(News).filter(News.uuid == uuid_obj, News.deleted_at.is_(None))
        if public_only:
            q = q.filter(News.is_published.is_(True))
        news = q.first()
        if not news:
            return None
        return _news_to_dict(news, db)


def create_news(
    *,
    title: str,
    content: Optional[str],
    cover_image_uuid: Optional[str],
    tag_uuids: list[str],
    is_published: bool,
    published_at: Optional[datetime],
    created_by: int,
) -> dict:
    with SessionLocal() as db:
        cover_id = _resolve_cover(cover_image_uuid, db)
        auto_published_at = published_at
        if is_published and not auto_published_at:
            auto_published_at = datetime.now(timezone.utc)

        news = News(
            title=title,
            content=content,
            cover_image=cover_id,
            is_published=is_published,
            published_at=auto_published_at,
            created_by=created_by,
        )
        db.add(news)
        db.flush()
        _sync_tags(news.id, tag_uuids, db)
        db.commit()
        db.refresh(news)
        return _news_to_dict(news, db)


def update_news(uuid_str: str, data: dict) -> Optional[dict]:
    """
    Обновляет только поля переданные в data (exclude_unset семантика).
    cover_image_uuid: None в data → убрать обложку.
    cover_image_uuid отсутствует в data → не трогать обложку.
    """
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None

    with SessionLocal() as db:
        news = db.query(News).filter(
            News.uuid == uuid_obj, News.deleted_at.is_(None)
        ).first()
        if not news:
            return None

        if "title" in data and data["title"] is not None:
            news.title = data["title"]
        if "content" in data:
            news.content = data["content"]
        if "cover_image_uuid" in data:
            news.cover_image = _resolve_cover(data["cover_image_uuid"], db)
        if "is_published" in data and data["is_published"] is not None:
            news.is_published = data["is_published"]
            if data["is_published"] and not news.published_at and "published_at" not in data:
                news.published_at = datetime.now(timezone.utc)
        if "published_at" in data:
            news.published_at = data["published_at"]
        if "tag_uuids" in data and data["tag_uuids"] is not None:
            _sync_tags(news.id, data["tag_uuids"], db)

        news.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(news)
        return _news_to_dict(news, db)


def delete_news(uuid_str: str) -> bool:
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return False

    with SessionLocal() as db:
        news = db.query(News).filter(
            News.uuid == uuid_obj, News.deleted_at.is_(None)
        ).first()
        if not news:
            return False
        news.deleted_at = datetime.now(timezone.utc)
        db.commit()

    return True

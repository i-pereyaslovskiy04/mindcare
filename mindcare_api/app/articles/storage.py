import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc

from app.db.session import SessionLocal
from app.db.models import (
    Article, ArticleCategory, ArticleTag,
    Category, Tag, User, MediaFile,
)
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context


# ── helpers ───────────────────────────────────────────────────────────────────

def _article_to_dict(article: Article, db) -> dict:
    categories = (
        db.query(Category)
        .join(ArticleCategory, ArticleCategory.category_id == Category.id)
        .filter(ArticleCategory.article_id == article.id)
        .all()
    )
    tags = (
        db.query(Tag)
        .join(ArticleTag, ArticleTag.tag_id == Tag.id)
        .filter(ArticleTag.article_id == article.id)
        .all()
    )
    cover_url = None
    cover_uuid = None
    if article.cover_image:
        mf = db.query(MediaFile).filter(MediaFile.id == article.cover_image).first()
        if mf:
            cover_url  = mf.file_path
            cover_uuid = str(mf.uuid)

    author_name = None
    if article.created_by:
        user = db.query(User).filter(User.id == article.created_by).first()
        if user:
            author_name = user.full_name

    return {
        "uuid":             str(article.uuid),
        "title":            article.title,
        "excerpt":          article.excerpt,
        "content":          article.content,
        "cover_image_uuid": cover_uuid,
        "cover_image_url":  cover_url,
        "categories": [
            {"id": c.id, "name": c.name, "slug": c.slug} for c in categories
        ],
        "tags": [{"uuid": str(t.uuid), "name": t.name} for t in tags],
        "is_published":    article.is_published,
        "published_at":    article.published_at,
        "created_at":      article.created_at,
        "updated_at":      article.updated_at,
        "created_by_name": author_name,
    }


def _resolve_cover(uuid_str: Optional[str], db) -> Optional[int]:
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


def _sync_categories(article_id: int, category_ids: list[int], db) -> None:
    db.query(ArticleCategory).filter(ArticleCategory.article_id == article_id).delete()
    for cat_id in category_ids:
        cat = db.query(Category).filter(Category.id == cat_id, Category.is_active.is_(True)).first()
        if cat:
            db.add(ArticleCategory(article_id=article_id, category_id=cat.id))


def _sync_tags(article_id: int, tag_uuids: list[str], db) -> None:
    db.query(ArticleTag).filter(ArticleTag.article_id == article_id).delete()
    for uuid_str in tag_uuids:
        try:
            uuid_obj = _uuid.UUID(uuid_str)
        except ValueError:
            continue
        tag = db.query(Tag).filter(Tag.uuid == uuid_obj).first()
        if tag:
            db.add(ArticleTag(article_id=article_id, tag_id=tag.id))


# ── public API ────────────────────────────────────────────────────────────────

def find_articles(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    is_published: Optional[bool] = None,
    category_id: Optional[int] = None,
    public_only: bool = False,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        q = db.query(Article).filter(Article.deleted_at.is_(None))

        if public_only:
            q = q.filter(Article.is_published.is_(True))
        elif is_published is not None:
            q = q.filter(Article.is_published.is_(is_published))

        if search:
            q = q.filter(Article.title.ilike(f"%{search.strip()}%"))

        if category_id is not None:
            q = q.join(ArticleCategory, ArticleCategory.article_id == Article.id).filter(
                ArticleCategory.category_id == category_id
            )

        total = q.count()
        articles = (
            q.order_by(desc(Article.created_at))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        items = [_article_to_dict(a, db) for a in articles]

    return items, total


def get_article_by_uuid(uuid_str: str, public_only: bool = False) -> Optional[dict]:
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None

    with SessionLocal() as db:
        q = db.query(Article).filter(Article.uuid == uuid_obj, Article.deleted_at.is_(None))
        if public_only:
            q = q.filter(Article.is_published.is_(True))
        article = q.first()
        if not article:
            return None
        return _article_to_dict(article, db)


def create_article(
    *,
    title: str,
    excerpt: Optional[str],
    content: Optional[str],
    cover_image_uuid: Optional[str],
    category_ids: list[int],
    tag_uuids: list[str],
    is_published: bool,
    published_at: Optional[datetime],
    created_by: int,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    # created_by — единственный actor id (не вводим второй actor_id).
    if created_by is None or actor_role is None:
        raise RuntimeError(
            "article create requires authenticated actor context "
            "(created_by and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    with SessionLocal() as db:
        cover_id = _resolve_cover(cover_image_uuid, db)
        auto_published_at = published_at
        if is_published and not auto_published_at:
            auto_published_at = datetime.now(timezone.utc)

        article = Article(
            title=title,
            excerpt=excerpt,
            content=content,
            cover_image=cover_id,
            is_published=is_published,
            published_at=auto_published_at,
            created_by=created_by,
        )
        db.add(article)
        db.flush()
        _sync_categories(article.id, category_ids, db)
        _sync_tags(article.id, tag_uuids, db)
        record_event(
            event="article_created",
            actor=Actor.user(created_by, actor_role),
            target=Target("article", article.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(article)
        return _article_to_dict(article, db)


def update_article(
    uuid_str: str,
    data: dict,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Обновляет только поля переданные в data (exclude_unset семантика).
    cover_image_uuid: None в data → убрать обложку.
    cover_image_uuid отсутствует в data → не трогать обложку.
    """
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "article update requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None

    with SessionLocal() as db:
        article = db.query(Article).filter(
            Article.uuid == uuid_obj, Article.deleted_at.is_(None)
        ).first()
        if not article:
            return None

        if "title" in data and data["title"] is not None:
            article.title = data["title"]
        if "excerpt" in data:
            article.excerpt = data["excerpt"]
        if "content" in data:
            article.content = data["content"]
        if "cover_image_uuid" in data:
            article.cover_image = _resolve_cover(data["cover_image_uuid"], db)
        if "is_published" in data and data["is_published"] is not None:
            article.is_published = data["is_published"]
            if data["is_published"] and not article.published_at and "published_at" not in data:
                article.published_at = datetime.now(timezone.utc)
        if "published_at" in data:
            article.published_at = data["published_at"]
        if "category_ids" in data and data["category_ids"] is not None:
            _sync_categories(article.id, data["category_ids"], db)
        if "tag_uuids" in data and data["tag_uuids"] is not None:
            _sync_tags(article.id, data["tag_uuids"], db)

        article.updated_at = datetime.now(timezone.utc)
        record_event(
            event="article_updated",
            actor=Actor.user(actor_id, actor_role),
            target=Target("article", article.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()
        db.refresh(article)
        return _article_to_dict(article, db)


def delete_article(
    uuid_str: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    if actor_id is None or actor_role is None:
        raise RuntimeError(
            "article delete requires authenticated actor context "
            "(actor_id and actor_role)"
        )
    safe_ctx = build_request_context(ip=ip, user_agent=user_agent)

    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return False

    with SessionLocal() as db:
        article = db.query(Article).filter(
            Article.uuid == uuid_obj, Article.deleted_at.is_(None)
        ).first()
        if not article:
            return False
        article.deleted_at = datetime.now(timezone.utc)
        record_event(
            event="article_deleted",
            actor=Actor.user(actor_id, actor_role),
            target=Target("article", article.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=safe_ctx,
            db=db,
        )
        db.commit()

    return True


def list_categories() -> list[dict]:
    with SessionLocal() as db:
        cats = db.query(Category).filter(Category.is_active.is_(True)).order_by(
            Category.display_order, Category.name
        ).all()
        return [{"id": c.id, "name": c.name, "slug": c.slug} for c in cats]

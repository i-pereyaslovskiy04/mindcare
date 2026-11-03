"""
Статьи психолога и их модерация — весь SQLAlchemy (ADR-034).

Автор (psychologist; supervisor — Дополнение 2026-10-28) работает только со
СВОИМИ статьями (created_by = actor):
  * создание — всегда draft (is_published = false);
  * правка — в draft / needs_changes / published; правка published атомарно
    снимает её с публикации (status → draft, is_published → false) и пишет
    article_unpublished_for_edit (как test_unpublished_for_edit, F2.1);
    in_review не правится (409) — проверяющий видит неизменную версию;
  * удаление (мягкое) — в draft / needs_changes;
  * отправка на проверку — draft / needs_changes → in_review (комментарий
    прежнего возврата снимается);
  * supervisor-автор публикует свою статью сам — draft / needs_changes →
    published (publish_own, событие article_published с ролью supervisor),
    без очереди: как у тестов, где staff публикует draft напрямую.
Проверяющий (admin / supervisor):
  * публикация — in_review → published (is_published → true, published_at,
    если не было); возврат — in_review → needs_changes с необязательным
    комментарием (Fernet enc:v1:, виден только автору; в журнал не попадает).

Каждая мутация — одна транзакция: SELECT … FOR UPDATE строки статьи →
проверка владельца/статуса ПОД блокировкой → изменение → record_event(db=db)
ATOMIC/RAISE → commit. Конкурирующие переходы сериализуются, проигравший видит
свежий статус и получает ArticleStateConflict. Задание, прикрепляющее статью,
берёт её FOR SHARE с публичным предикатом — снятие с публикации и назначение
тоже не проскальзывают друг мимо друга.
"""
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc

from app.articles.storage import (
    _article_to_dict, _resolve_cover, _sync_categories, _sync_tags,
)
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.core.encryption import decrypt_text, encrypt_text
from app.db.models import Article
from app.db.session import SessionLocal

AUTHOR_EDITABLE = frozenset({"draft", "needs_changes", "published"})
AUTHOR_DELETABLE = frozenset({"draft", "needs_changes"})
AUTHOR_SUBMITTABLE = frozenset({"draft", "needs_changes"})
AUTHOR_PUBLISHABLE = frozenset({"draft", "needs_changes"})
REVIEW_COMMENT_MAX = 2000


class ArticleNotFound(Exception):
    """Нет статьи / не своя / не на проверке — один и тот же ответ (404)."""


class ArticleStateConflict(Exception):
    """Переход недопустим из текущего статуса (409)."""

    def __init__(self, current_status: str):
        self.current_status = current_status
        super().__init__(current_status)


def _parse_uuid(value) -> Optional[_uuid.UUID]:
    if isinstance(value, _uuid.UUID):
        return value
    try:
        return _uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _lock(db, article_uuid) -> Optional[Article]:
    uuid_obj = _parse_uuid(article_uuid)
    if uuid_obj is None:
        return None
    return (
        db.query(Article)
        .filter(Article.uuid == uuid_obj, Article.deleted_at.is_(None))
        .with_for_update()
        .populate_existing()
        .first()
    )


def _author_dict(article: Article, db) -> dict:
    data = _article_to_dict(article, db)
    data["review_comment"] = (
        decrypt_text(article.review_comment_enc) if article.review_comment_enc else None
    )
    return data


def _event(db, event: str, actor_id: int, role: str, article_id: int, ip, user_agent) -> None:
    record_event(
        event=event,
        actor=Actor.user(int(actor_id), role),
        target=Target("article", article_id),
        outcome=Outcome.SUCCESS,
        metadata={},
        context=build_request_context(ip=ip, user_agent=user_agent),
        db=db,
    )


def _notify_author(article: Article, reviewer_id: int) -> Optional[dict]:
    """
    Данные post-commit уведомления автора о решении (routes публикует
    system-сообщение после commit). Своё решение (автор = проверяющий) и статья
    без автора — без уведомления. occurrence — updated_at этого перехода:
    повторный возврат той же статьи даёт новый ключ, ретрай — тот же.
    """
    if article.created_by is None or int(article.created_by) == int(reviewer_id):
        return None
    return {
        "author_id": int(article.created_by),
        "article_uuid": str(article.uuid),
        "title": article.title,
        "occurrence": article.updated_at.strftime("%Y%m%d%H%M%S%f"),
    }


def _apply_content(article: Article, data: dict, db) -> None:
    if data.get("title") is not None:
        article.title = data["title"]
    if "excerpt" in data:
        article.excerpt = data["excerpt"]
    if "content" in data:
        article.content = data["content"]
    if "cover_image_uuid" in data:
        article.cover_image = _resolve_cover(data["cover_image_uuid"], db)
    if data.get("category_ids") is not None:
        _sync_categories(article.id, data["category_ids"], db)
    if data.get("tag_uuids") is not None:
        _sync_tags(article.id, data["tag_uuids"], db)


# ── автор ─────────────────────────────────────────────────────────────────────

def list_own(
    author_id: int, *, page: int, size: int,
    search: Optional[str] = None, status: Optional[str] = None,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        q = db.query(Article).filter(
            Article.created_by == int(author_id), Article.deleted_at.is_(None),
        )
        if status:
            q = q.filter(Article.status == status)
        if search:
            q = q.filter(Article.title.ilike(f"%{search.strip()}%"))
        total = q.count()
        rows = (
            q.order_by(desc(Article.updated_at), desc(Article.id))
            .offset((page - 1) * size).limit(size).all()
        )
        return [_author_dict(a, db) for a in rows], total


def get_own(author_id: int, article_uuid) -> Optional[dict]:
    uuid_obj = _parse_uuid(article_uuid)
    if uuid_obj is None:
        return None
    with SessionLocal() as db:
        article = db.query(Article).filter(
            Article.uuid == uuid_obj, Article.deleted_at.is_(None),
            Article.created_by == int(author_id),
        ).first()
        return _author_dict(article, db) if article else None


def create_own(
    author_id: int, data: dict, *, role: str = "psychologist", ip=None, user_agent=None,
) -> dict:
    with SessionLocal() as db:
        article = Article(
            title=data["title"],
            excerpt=data.get("excerpt"),
            content=data.get("content"),
            cover_image=_resolve_cover(data.get("cover_image_uuid"), db),
            is_published=False,
            status="draft",
            created_by=int(author_id),
        )
        db.add(article)
        db.flush()
        _sync_categories(article.id, data.get("category_ids") or [], db)
        _sync_tags(article.id, data.get("tag_uuids") or [], db)
        _event(db, "article_created", author_id, role, article.id, ip, user_agent)
        db.commit()
        db.refresh(article)
        return _author_dict(article, db)


def update_own(
    author_id: int, article_uuid, data: dict, *, role: str = "psychologist",
    ip=None, user_agent=None,
) -> dict:
    with SessionLocal() as db:
        article = _lock(db, article_uuid)
        if article is None or article.created_by != int(author_id):
            raise ArticleNotFound()
        if article.status not in AUTHOR_EDITABLE:
            raise ArticleStateConflict(article.status)
        if article.status == "published":
            # F2.1-паттерн: правка опубликованной статьи снимает её с публикации.
            article.status = "draft"
            article.is_published = False
            _event(db, "article_unpublished_for_edit", author_id, role,
                   article.id, ip, user_agent)
        _apply_content(article, data, db)
        article.updated_at = datetime.now(timezone.utc)
        _event(db, "article_updated", author_id, role, article.id, ip, user_agent)
        db.commit()
        db.refresh(article)
        return _author_dict(article, db)


def delete_own(
    author_id: int, article_uuid, *, role: str = "psychologist", ip=None, user_agent=None,
) -> None:
    with SessionLocal() as db:
        article = _lock(db, article_uuid)
        if article is None or article.created_by != int(author_id):
            raise ArticleNotFound()
        if article.status not in AUTHOR_DELETABLE:
            raise ArticleStateConflict(article.status)
        article.deleted_at = datetime.now(timezone.utc)
        _event(db, "article_deleted", author_id, role, article.id, ip, user_agent)
        db.commit()


def submit_own(author_id: int, article_uuid, *, ip=None, user_agent=None) -> dict:
    with SessionLocal() as db:
        article = _lock(db, article_uuid)
        if article is None or article.created_by != int(author_id):
            raise ArticleNotFound()
        if article.status not in AUTHOR_SUBMITTABLE:
            raise ArticleStateConflict(article.status)
        article.status = "in_review"
        article.review_comment_enc = None
        article.updated_at = datetime.now(timezone.utc)
        _event(db, "article_submitted_for_review", author_id, "psychologist",
               article.id, ip, user_agent)
        db.commit()
        db.refresh(article)
        return _author_dict(article, db)


def publish_own(author_id: int, article_uuid, *, ip=None, user_agent=None) -> dict:
    """Supervisor публикует СВОЮ статью сам: draft / needs_changes → published."""
    with SessionLocal() as db:
        article = _lock(db, article_uuid)
        if article is None or article.created_by != int(author_id):
            raise ArticleNotFound()
        if article.status not in AUTHOR_PUBLISHABLE:
            raise ArticleStateConflict(article.status)
        now = datetime.now(timezone.utc)
        article.status = "published"
        article.is_published = True
        article.review_comment_enc = None
        if not article.published_at:
            article.published_at = now
        article.updated_at = now
        _event(db, "article_published", author_id, "supervisor", article.id, ip, user_agent)
        db.commit()
        db.refresh(article)
        return _author_dict(article, db)


# ── проверяющий ───────────────────────────────────────────────────────────────

def pending_count() -> int:
    """Число статей на проверке — бейдж меню проверяющего (без аудита)."""
    with SessionLocal() as db:
        return db.query(Article).filter(
            Article.status == "in_review", Article.deleted_at.is_(None),
        ).count()


def review_list(*, page: int, size: int) -> tuple[list[dict], int]:
    """Очередь модерации: только статьи на проверке, старые заявки сначала."""
    with SessionLocal() as db:
        q = db.query(Article).filter(
            Article.status == "in_review", Article.deleted_at.is_(None),
        )
        total = q.count()
        rows = (
            q.order_by(Article.updated_at, Article.id)
            .offset((page - 1) * size).limit(size).all()
        )
        return [_article_to_dict(a, db) for a in rows], total


def review_get(article_uuid) -> Optional[dict]:
    """Полная статья для проверки — только в статусе in_review."""
    uuid_obj = _parse_uuid(article_uuid)
    if uuid_obj is None:
        return None
    with SessionLocal() as db:
        article = db.query(Article).filter(
            Article.uuid == uuid_obj, Article.deleted_at.is_(None),
            Article.status == "in_review",
        ).first()
        return _article_to_dict(article, db) if article else None


def publish(reviewer_id: int, role: str, article_uuid, *, ip=None, user_agent=None) -> dict:
    with SessionLocal() as db:
        article = _lock(db, article_uuid)
        if article is None:
            raise ArticleNotFound()
        if article.status != "in_review":
            raise ArticleStateConflict(article.status)
        now = datetime.now(timezone.utc)
        article.status = "published"
        article.is_published = True
        article.review_comment_enc = None
        if not article.published_at:
            article.published_at = now
        article.updated_at = now
        _event(db, "article_published", reviewer_id, role, article.id, ip, user_agent)
        db.commit()
        db.refresh(article)
        result = _article_to_dict(article, db)
        result["_notify"] = _notify_author(article, reviewer_id)
        return result


def return_for_changes(
    reviewer_id: int, role: str, article_uuid, comment: Optional[str],
    *, ip=None, user_agent=None,
) -> dict:
    with SessionLocal() as db:
        article = _lock(db, article_uuid)
        if article is None:
            raise ArticleNotFound()
        if article.status != "in_review":
            raise ArticleStateConflict(article.status)
        article.status = "needs_changes"
        article.is_published = False
        article.review_comment_enc = encrypt_text(comment) if comment else None
        article.updated_at = datetime.now(timezone.utc)
        _event(db, "article_returned_for_changes", reviewer_id, role, article.id, ip, user_agent)
        db.commit()
        db.refresh(article)
        result = _article_to_dict(article, db)
        result["_notify"] = _notify_author(article, reviewer_id)
        return result

"""
Избранные материалы — весь SQLAlchemy (ADR-034).

Добавить можно только опубликованную неудалённую статью (тот же публичный
предикат, что у /api/articles): назначение не обходит ограничения чтения.
Список и идентификаторы отдают только статьи, опубликованные СЕЙЧАС; отметка
снятой с публикации статьи сохраняется, но не показывается. Повтор добавления
и удаления — no-op (ON CONFLICT DO NOTHING / DELETE без строки).

Потолок FAVORITES_LIMIT проверяется под блокировкой строки users владельца
(FOR KEY SHARE ниже по силе не сериализовал бы два параллельных добавления):
users FOR UPDATE → COUNT → INSERT. Порядок блокировок совпадает с другими
путями, берущими users FOR UPDATE первым (ADR-028), а здесь больше ничего не
блокируется — цикла нет.

Санитизация: неожиданная SQLAlchemyError → rollback, в stderr — операция,
фаза, класс; наружу FavoritesStorageError (вне except, from None).
"""
import sys

from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Article, MaterialFavorite as MF, User
from app.db.models.material_favorites import FAVORITES_LIMIT
from app.db.session import SessionLocal

_PUBLIC_ARTICLE = and_(Article.is_published.is_(True), Article.deleted_at.is_(None))


class FavoritesStorageError(RuntimeError):
    def __init__(self):
        super().__init__("material favorites storage failure")


class ArticleNotAvailable(Exception):
    """Статья не опубликована, удалена или не существует (не различаем)."""


class FavoritesLimitReached(Exception):
    pass


def _failure(db, operation: str, phase: str, error_class: str) -> FavoritesStorageError:
    try:
        db.rollback()
    except Exception as exc:   # noqa: BLE001 — rollback best-effort
        print(f"[FAVORITES] op={operation} phase=rollback error={type(exc).__name__}", file=sys.stderr)
    print(f"[FAVORITES] op={operation} phase={phase} error={error_class}", file=sys.stderr)
    return FavoritesStorageError()


def favorite_uuids(user_id: int) -> list:
    """uuid опубликованных статей из избранного, новые отметки сначала."""
    with SessionLocal() as db:
        error_class = None
        rows = []
        try:
            rows = db.execute(
                select(Article.uuid)
                .join(MF, MF.article_id == Article.id)
                .where(MF.user_id == int(user_id), _PUBLIC_ARTICLE)
                .order_by(MF.created_at.desc(), Article.id.desc())
                .limit(FAVORITES_LIMIT)
            ).scalars().all()
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "ids", "read", error_class) from None
    return [str(u) for u in rows]


def add(user_id: int, article_uuid) -> bool:
    """True — добавлено, False — уже было. ArticleNotAvailable / FavoritesLimitReached."""
    user_id = int(user_id)
    with SessionLocal() as db:
        error_class = None
        article_id = None
        count = 0
        try:
            db.execute(select(User.id).where(User.id == user_id).with_for_update())
            article_id = db.execute(
                select(Article.id).where(Article.uuid == article_uuid, _PUBLIC_ARTICLE)
            ).scalar()
            if article_id is not None:
                exists = db.execute(
                    select(MF.article_id).where(MF.user_id == user_id, MF.article_id == article_id)
                ).first()
                if exists is not None:
                    db.rollback()
                    return False
                count = db.execute(
                    select(func.count()).select_from(MF).where(MF.user_id == user_id)
                ).scalar() or 0
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "add", "read", error_class) from None

        if article_id is None:
            db.rollback()
            raise ArticleNotAvailable()
        if count >= FAVORITES_LIMIT:
            db.rollback()
            raise FavoritesLimitReached()

        inserted = None
        try:
            inserted = db.execute(
                pg_insert(MF)
                .values(user_id=user_id, article_id=article_id)
                .on_conflict_do_nothing(index_elements=[MF.user_id, MF.article_id])
                .returning(MF.article_id)
            ).first()
            db.commit()
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "add", "write", error_class) from None
    return inserted is not None


def remove(user_id: int, article_uuid) -> bool:
    """True — удалено, False — отметки не было (в т.ч. нет такой статьи)."""
    with SessionLocal() as db:
        error_class = None
        removed = None
        try:
            article_id = db.execute(
                select(Article.id).where(Article.uuid == article_uuid)
            ).scalar()
            if article_id is not None:
                removed = db.execute(
                    delete(MF)
                    .where(MF.user_id == int(user_id), MF.article_id == article_id)
                    .returning(MF.article_id)
                ).first()
            db.commit()
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _failure(db, "remove", "write", error_class) from None
    return removed is not None


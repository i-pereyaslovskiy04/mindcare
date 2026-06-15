"""
FastAPI application entry point.

╔══════════════════════════════════════════════════════════════╗
║  ПОРЯДОК ЗАПУСКА (обязательно):                             ║
║                                                              ║
║  1. alembic upgrade head   ← применить миграции (CLI)       ║
║  2. uvicorn app.main:app   ← стартовать приложение          ║
╚══════════════════════════════════════════════════════════════╝

Startup sequence (lifespan):
  1. init_db()         — ensure_database + check_migrations (read-only) + seed
  2. cleanup_expired() — удаляет просроченные OTP из прошлых запусков

  Миграции НЕ запускаются при старте. Только проверка версии (WARNING если
  DB отстаёт) и idempotent seed.

Маршруты:
  /api/auth/*         — аутентификация (open + protected)
  /api/admin/users/*  — управление пользователями (admin only)
  /api/health         — health-check (БД + revision + tables count)
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings

# Принудительно задаём кодировку клиента PostgreSQL до любых импортов SQLAlchemy.
# На Windows с русской локалью (cp1251) psycopg2 иначе падает с UnicodeDecodeError
# при первом обращении к БД (PostgreSQL возвращает ошибки на русском в cp1251).
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Выполняется один раз при старте (до первого запроса) и при остановке.

    Блокирующие sync-операции (init_db, cleanup_expired) безопасны здесь:
    приложение ещё не обслуживает запросы — event-loop не заблокирован.
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    log.info("MindCare API starting up...")

    # Fail-fast: без валидного DATA_ENCRYPTION_KEY chat/session_notes сломались бы
    # только при первом encrypted read/write. Проверяем до обработки запросов.
    from app.core.encryption import assert_encryption_ready
    assert_encryption_ready()

    from app.db.init_db import init_db
    init_db()                   # ensure_database + check_migrations + seed

    from app.auth.otp_service import cleanup_expired
    removed = cleanup_expired()  # чистим просроченные OTP прошлых сессий
    if removed:
        log.info("Cleaned up %d expired OTP record(s)", removed)

    log.info("MindCare API ready")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("MindCare API shutting down...")
    from app.db.session import engine
    engine.dispose()
    log.info("Database connections closed.")


# ─── Application ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="MindCare API",
    description="Психологическая служба Донецкого государственного университета",
    version="1.0.0",
    lifespan=lifespan,
)

_allowed_origins = [
    origin.strip()
    for origin in settings.ALLOWED_ORIGINS.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Static files (media uploads) ─────────────────────────────────────────────

_MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"
_MEDIA_DIR.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=str(_MEDIA_DIR)), name="media")

# ─── Routers ──────────────────────────────────────────────────────────────────

from app.auth.routes import router as auth_router                # noqa: E402
from app.users.routes_admin import router as admin_users_router  # noqa: E402
from app.tags.routes_admin import router as admin_tags_router    # noqa: E402
from app.tags.routes_public import router as public_tags_router  # noqa: E402
from app.media.routes import router as media_router              # noqa: E402
from app.news.routes_admin import router as admin_news_router          # noqa: E402
from app.news.routes_public import router as public_news_router        # noqa: E402
from app.articles.routes_admin import router as admin_articles_router    # noqa: E402
from app.articles.routes_public import router as public_articles_router  # noqa: E402
from app.categories.routes_admin import router as admin_categories_router  # noqa: E402
from app.supervisor.routes import router as supervisor_router              # noqa: E402
from app.psychologist.routes import router as psychologist_router          # noqa: E402
from app.session_notes.routes import router as session_notes_router        # noqa: E402
from app.chat.routes import router as chat_router                          # noqa: E402
from app.chat.routes import system_router as chat_system_router            # noqa: E402

app.include_router(auth_router,               prefix="/api")
app.include_router(admin_users_router,        prefix="/api")
app.include_router(admin_tags_router,         prefix="/api")
app.include_router(public_tags_router,        prefix="/api")
app.include_router(media_router,              prefix="/api")
app.include_router(admin_news_router,         prefix="/api")
app.include_router(public_news_router,        prefix="/api")
app.include_router(admin_articles_router,     prefix="/api")
app.include_router(public_articles_router,    prefix="/api")
app.include_router(admin_categories_router,   prefix="/api")
app.include_router(supervisor_router,         prefix="/api")
app.include_router(psychologist_router,       prefix="/api")
app.include_router(session_notes_router,      prefix="/api")
app.include_router(chat_router,               prefix="/api")
app.include_router(chat_system_router,        prefix="/api")


# ─── Built-in endpoints ───────────────────────────────────────────────────────

@app.get("/api/hello", tags=["meta"])
def read_root():
    return {"message": "Привет from FastAPI!"}


@app.get("/api/health", tags=["meta"])
def health():
    """
    Health-check: проверяет соединение с БД и возвращает кол-во таблиц в metadata.
    """
    from app.db.init_db import health_check
    return health_check()


@app.get("/api/public/config", tags=["meta"])
def public_config():
    """
    Публичная конфигурация для фронтенда (без авторизации).
    Позволяет избежать дублирования ENV-переменных между backend и frontend.
    """
    return {
        "newsImageMaxSizeMb": settings.NEWS_IMAGE_MAX_SIZE_MB,
    }

"""
Фабрика соединений с БД.

Экспортирует:
  engine       — SQLAlchemy Engine (psycopg2, синхронный)
  SessionLocal — фабрика сессий
  get_db()     — FastAPI-dependency (yield-based)

Base живёт в app.db.base — импортируй оттуда напрямую.

ВАЖНО: проект использует синхронный SQLAlchemy (psycopg2).
Не переключать на asyncpg без явного решения команды.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,      # проверяет соединение перед использованием из пула
    pool_size=10,            # базовый пул
    max_overflow=20,         # доп. соединения при пиковой нагрузке
    pool_timeout=30,         # секунд ждать свободное соединение
    echo=False,              # True → SQL в stdout (только для отладки)
    # Windows + русская локаль PostgreSQL: принудительно UTF-8 для соединения.
    # Без этого psycopg2 падает с UnicodeDecodeError при получении ошибки
    # от PostgreSQL на русском языке (cp1251 → UTF-8 decode fail).
    connect_args={"client_encoding": "utf8"},
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db():
    """
    FastAPI dependency: открывает сессию, передаёт в эндпоинт, закрывает после.

    Использование:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

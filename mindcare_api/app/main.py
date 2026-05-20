from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.users.routes_admin import router as admin_users_router
from app.db.session import engine
from app.db import models  # noqa: F401 — регистрирует все модели в Base
from app.db.models import Base


def _create_custom_tables() -> None:
    """Создаёт только кастомные таблицы, которых нет в SQL-схеме.
    Основные 38 таблиц (users, roles, user_sessions и др.) применяются через:
      psql -U postgres -d mindcare -f db/sql/full_schema.sql
    """
    from sqlalchemy import inspect as _inspect
    inspector = _inspect(engine)
    existing = set(inspector.get_table_names())
    tables_to_create = [
        t for t in Base.metadata.sorted_tables
        if t.name == "otp_verifications" and t.name not in existing
    ]
    if tables_to_create:
        Base.metadata.create_all(bind=engine, tables=tables_to_create)


_create_custom_tables()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.auth.otp_service import cleanup_expired
    cleanup_expired()
    yield


app = FastAPI(title="MindCare API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(admin_users_router, prefix="/api")


@app.get("/api/hello")
def read_root():
    return {"message": "Привет from FastAPI!"}

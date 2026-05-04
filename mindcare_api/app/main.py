from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.db.session import engine
from app.db import models  # noqa: F401 — registers all models with Base
from app.db.models import Base

# Create all tables (including otp_verifications) before the app starts accepting requests.
Base.metadata.create_all(bind=engine)


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


@app.get("/api/hello")
def read_root():
    return {"message": "Привет from FastAPI!"}

from fastapi import APIRouter, HTTPException, Depends
from app.routers.auth import get_current_user, require_role
from app.schemas.user import UserResponse
from app.data.fake_db import USERS

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: dict = Depends(get_current_user)):
    return UserResponse(**{k: current_user[k] for k in ("id", "email", "name", "role")})


@router.get("/psychologists")
def get_psychologists(_: dict = Depends(get_current_user)):
    return [
        {"id": u["id"], "name": u["name"], "specialization": u.get("specialization", "")}
        for u in USERS.values()
        if u["role"] == "psychologist"
    ]


@router.get("/all")
def get_all_users(_: dict = Depends(require_role("admin"))):
    return [
        {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}
        for u in USERS.values()
    ]

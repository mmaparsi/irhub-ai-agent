from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth.deps import get_current_user
from app.auth.security import create_access_token, verify_password
from app.database import get_db
from app.models import User
from app.schemas import LoginIn, LoginOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or not user.is_active
        or not verify_password(body.password, user.hashed_password)
    ):
        raise HTTPException(status_code=401, detail="ایمیل یا گذرواژه نادرست است")
    write_audit(
        db,
        actor_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        details={},
    )
    db.commit()
    token = create_access_token(user_id=user.id, role=user.role)
    return LoginOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user

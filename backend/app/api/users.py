from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth.deps import require_roles
from app.auth.security import hash_password
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
) -> User:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="این ایمیل قبلاً ثبت شده است")
    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name.strip(),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        actor_id=actor.id,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role},
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    data = body.model_dump(exclude_unset=True)
    next_role = data.get("role", user.role)
    next_active = data.get("is_active", user.is_active)
    if user.id == actor.id and (next_role != "admin" or next_active is False):
        raise HTTPException(status_code=409, detail="نمی‌توانید دسترسی مدیر فعلی خود را حذف کنید")
    if "full_name" in data and data["full_name"] is not None:
        user.full_name = data["full_name"].strip()
    if "role" in data and data["role"] is not None:
        user.role = data["role"]
    if "is_active" in data and data["is_active"] is not None:
        user.is_active = data["is_active"]
    write_audit(
        db,
        actor_id=actor.id,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role, "is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return user

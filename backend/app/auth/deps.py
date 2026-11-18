from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.database import get_db
from app.models import User


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="احراز هویت نشده")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="توکن نامعتبر است") from None
    user_id = payload.get("sub")
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="کاربر غیرفعال است یا پیدا نشد")
    return user


def require_roles(*roles: str) -> Callable:
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
        return user

    return _dep

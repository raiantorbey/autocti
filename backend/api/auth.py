"""Auth routes: /login, /register (admin only), /me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import (
    create_access_token,
    hash_password,
    require_roles,
    verify_password,
    ROLE_ADMIN,
    ROLE_READONLY,
)
from backend.db.postgres import get_session
from backend.models.models import User
from backend.schemas.schemas import Token, UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> Token:
    q = await session.execute(select(User).where(User.username == form.username))
    user = q.scalar_one_or_none()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User disabled"
        )
    token = create_access_token(subject=user.username, role=user.role)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post(
    "/register",
    response_model=UserOut,
    dependencies=[Depends(require_roles(*ROLE_ADMIN))],
)
async def register(
    payload: UserCreate, session: AsyncSession = Depends(get_session)
) -> UserOut:
    existing = await session.execute(
        select(User).where(
            (User.username == payload.username) | (User.email == payload.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already taken",
        )
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.flush()
    return UserOut.model_validate(user)


@router.get("/me", response_model=UserOut)
async def me(
    user: User = Depends(require_roles(*ROLE_READONLY)),
) -> UserOut:
    return UserOut.model_validate(user)

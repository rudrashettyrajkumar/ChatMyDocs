"""Auth routes: self-contained email/password → our own HS256 JWT.

`POST /auth/register` and `POST /auth/login` both return `{access_token, user}`
so the client can sign in immediately after signing up. `GET /auth/me` reports
the live profile behind a bearer token.

Validation is intentionally light (no `email-validator` dependency): a token
`@`-shaped check plus length bounds. The real uniqueness/identity guarantee is
the user store, not the regex.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from backend.middleware.jwt_auth import get_current_user, issue_jwt
from backend.services.users import (
    AuthUnavailable,
    AuthUser,
    EmailAlreadyRegistered,
    InvalidCredentials,
    authenticate,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_log = logging.getLogger("docchat.api.auth")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_AUTH_UNAVAILABLE = "Sign-in temporarily unavailable. Please try again."


class _Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v


class RegisterRequest(_Credentials):
    name: str | None = Field(default=None, max_length=80)


class LoginRequest(_Credentials):
    pass


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None = None
    created_at: float


class AuthResponse(BaseModel):
    access_token: str
    user: UserOut


def _user_out(user: AuthUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, created_at=user.created_at)


def _auth_response(user: AuthUser) -> AuthResponse:
    return AuthResponse(
        access_token=issue_jwt(user_id=user.id, email=user.email),
        user=_user_out(user),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest) -> AuthResponse:
    try:
        user = await register_user(body.email, body.password, body.name)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    except AuthUnavailable as exc:
        _log.warning("register failed: store unavailable", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_AUTH_UNAVAILABLE
        ) from exc
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest) -> AuthResponse:
    try:
        user = await authenticate(body.email, body.password)
    except InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        ) from exc
    except AuthUnavailable as exc:
        _log.warning("login failed: store unavailable", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_AUTH_UNAVAILABLE
        ) from exc
    return _auth_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: AuthUser = Depends(get_current_user)) -> UserOut:
    return _user_out(user)

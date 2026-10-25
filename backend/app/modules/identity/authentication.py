from datetime import datetime, timedelta, timezone

import jwt
from app.core.security import hash_api_key
from app.core.settings import get_settings
from app.db.session import get_db
from app.modules.identity.models import User
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session


def create_access_token(*, user: User) -> tuple[str, int]:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_minutes
    )
    token = jwt.encode(
        {
            "sub": str(user.id),
            "ver": user.auth_version,
            "exp": expires_at,
            "type": "access",
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, settings.jwt_access_token_minutes * 60


def _get_bearer_user(authorization: str | None, db: Session) -> User | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="登录令牌格式无效")
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            raise ValueError("unexpected token type")
        user_id = int(payload["sub"])
        auth_version = int(payload["ver"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="登录令牌无效或已过期")
    user = db.get(User, user_id)
    if user is None or user.auth_version != auth_version:
        raise HTTPException(status_code=401, detail="登录令牌无效或已过期")
    return user


async def get_authenticated_account(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate a browser JWT, with temporary API-key compatibility."""
    jwt_user = _get_bearer_user(authorization, db)
    if jwt_user is not None:
        return jwt_user

    if x_api_key is None:
        raise HTTPException(status_code=401, detail="请先登录或提供有效的访问凭证")

    user = db.query(User).filter(User.api_key_hash == hash_api_key(x_api_key)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="访问凭证无效")
    return user


async def get_current_user(
    user: User = Depends(get_authenticated_account),
) -> User:
    if not user.is_active:
        raise HTTPException(status_code=401, detail="account is inactive")
    return user

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get("access_token") or token
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(
        text("SELECT id, username, is_admin FROM users WHERE username = :username"),
        {"username": username},
    )
    user = result.fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


async def require_internal_service_token(
    x_internal_service_token: str | None = Header(default=None, alias="X-Internal-Service-Token"),
):
    if x_internal_service_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal service token")

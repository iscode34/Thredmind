from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

from app.config import settings
from app.services.db_client import execute_one

ALGORITHM = settings.JWT_ALGORITHM
SECRET = settings.jwt_secret
EXPIRE_MINUTES = settings.JWT_EXPIRE_MINUTES


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        SECRET,
        algorithm=ALGORITHM,
    )


def get_current_user(request: Request):
    token = request.cookies.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        user = execute_one("SELECT id, email, created_at FROM users WHERE id = %s", (user_id,))
        return dict(user) if user else None
    except JWTError:
        return None


def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def theme_from_request(request: Request) -> str:
    return request.cookies.get("theme", "dark")


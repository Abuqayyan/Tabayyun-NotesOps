"""Authentication primitives: password hashing, JWT issue/verify, current-user dependency."""
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext

from app.core.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_DAYS, SESSION_HOURS
from app.core.db_mongo import db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def make_token(user_id: str, hours: Optional[int] = None) -> str:
    exp_delta = timedelta(hours=hours) if hours else timedelta(days=JWT_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + exp_delta,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def make_session_token(user_id: str) -> str:
    """Session token issued after OTP verification."""
    return make_token(user_id, hours=SESSION_HOURS)


def decode_token(token: str) -> Optional[str]:
    """Returns the user_id (sub) for a valid token, else None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not creds:
        raise HTTPException(401, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token")
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(401, "User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")

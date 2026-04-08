"""
JWT Utilities

Token creation and validation using python-jose.
"""

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt


def _settings():
    from app.config import settings
    return settings


def create_access_token(user_id: str, username: str, role: str) -> str:
    """Create a signed JWT access token."""
    s = _settings()
    expires = datetime.utcnow() + timedelta(hours=s.jwt_expiration_hours)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": expires,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT. Returns payload dict or None if invalid/expired."""
    s = _settings()
    try:
        return jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm])
    except JWTError:
        return None

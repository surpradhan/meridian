"""
Auth API Routes

POST /api/auth/register  — create a new user account
POST /api/auth/login     — exchange credentials for a JWT
GET  /api/auth/me        — return the authenticated user's profile

Registration policy:
  - If no users exist yet (bootstrap), the request is open and the first
    account is forced to role=admin regardless of what was requested.
  - Once at least one user exists, a valid admin Bearer token is required.
"""

import logging
from typing import Any, Dict, List, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_optional_current_user
from app.auth.jwt import create_access_token
from app.auth.store import AuthStore, User, get_auth_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Password helpers — always use bcrypt directly to avoid passlib compat issues
# ---------------------------------------------------------------------------

# Lazily created dummy hash used in timing-safe login comparisons.
# Low cost factor (4) is intentional — we only need it to take ~constant time,
# not to be cryptographically strong, since this hash is never stored.
_DUMMY_HASH: Optional[str] = None


def _get_dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = bcrypt.hashpw(b"meridian_sentinel_dummy", bcrypt.gensalt(4)).decode()
    return _DUMMY_HASH


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


_OAUTH_ONLY_SENTINEL = "<oauth_only>"


def _verify_password(password: str, hashed: str) -> bool:
    # OAuth-only accounts have no stored password — never allow password login.
    if not hashed or hashed == _OAUTH_ONLY_SENTINEL:
        return False
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    role: str = Field(default="viewer", description="Role: admin | analyst | viewer")
    allowed_domains: List[str] = Field(
        default=[],
        description="Domains this user can access. Empty list = no domain access for non-admins.",
    )


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_hours: int


class UserProfile(BaseModel):
    id: str
    username: str
    email: str
    role: str
    allowed_domains: List[str]
    created_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    store: AuthStore = Depends(get_auth_store),
    caller: Optional[User] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Register a new user account.

    Bootstrap mode: if no users exist, the first registration is open and
    the account is forced to admin role regardless of the requested role.
    After that, only an authenticated admin can create new accounts.
    """
    client_ip = request.client.host if request.client else "unknown"
    is_bootstrap = store.count_users() == 0

    if not is_bootstrap:
        if caller is None:
            store.log_audit(
                action="auth.register.denied",
                resource="/api/auth/register",
                username=body.username,
                status_code=401,
                client_ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to register new users",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if caller.role != "admin":
            store.log_audit(
                action="auth.register.denied",
                resource="/api/auth/register",
                user_id=caller.id,
                username=caller.username,
                status_code=403,
                client_ip=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can register new users",
            )

    if body.role not in ("admin", "analyst", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role must be one of: admin, analyst, viewer",
        )

    if store.user_exists(username=body.username, email=body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    # Bootstrap: override requested role — first user must be admin
    effective_role = "admin" if is_bootstrap else body.role

    password_hash = _hash_password(body.password)
    user = store.create_user(
        username=body.username,
        email=body.email,
        password_hash=password_hash,
        role=effective_role,
        allowed_domains=body.allowed_domains,
    )

    store.log_audit(
        action="auth.register",
        resource="/api/auth/register",
        user_id=caller.id if caller else user.id,
        username=caller.username if caller else user.username,
        status_code=201,
        client_ip=client_ip,
    )
    logger.info(f"Registered new user: {user.username!r} (role={user.role}, bootstrap={is_bootstrap})")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "allowed_domains": user.allowed_domains,
        "created_at": user.created_at,
    }


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    store: AuthStore = Depends(get_auth_store),
) -> Dict[str, Any]:
    """Authenticate with username + password and receive a JWT access token."""
    client_ip = request.client.host if request.client else "unknown"

    user = store.get_user_by_username(body.username)

    # Always run bcrypt to prevent username enumeration via timing.
    hash_to_check = user.password_hash if user else _get_dummy_hash()
    password_ok = _verify_password(body.password, hash_to_check)

    if user is None or not password_ok:
        store.log_audit(
            action="auth.login.failed",
            resource="/api/auth/login",
            username=body.username,
            status_code=401,
            client_ip=client_ip,
        )
        logger.warning(f"Failed login attempt for username {body.username!r} from {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id, user.username, user.role)

    from app.auth.jwt import _settings as _jwt_settings
    store.log_audit(
        action="auth.login",
        resource="/api/auth/login",
        user_id=user.id,
        username=user.username,
        status_code=200,
        client_ip=client_ip,
    )
    logger.info(f"User {user.username!r} logged in from {client_ip}")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_hours": _jwt_settings().jwt_expiration_hours,
    }


_SUPPORTED_OAUTH_PROVIDERS = frozenset({"google", "oidc"})


@router.get("/oauth/authorize")
async def oauth_authorize(
    provider: str,
    request: Request,
    store: AuthStore = Depends(get_auth_store),
) -> Dict[str, Any]:
    """
    Begin an OAuth2 / OIDC authorization code flow.

    Returns a redirect URL that the client should navigate to.  Supported
    providers: ``google``, ``oidc`` (requires OIDC_ISSUER to be configured).

    Example:
        GET /api/auth/oauth/authorize?provider=google
        → {"redirect_url": "https://accounts.google.com/o/oauth2/v2/auth?..."}
    """
    if provider not in _SUPPORTED_OAUTH_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider!r}. Supported: {sorted(_SUPPORTED_OAUTH_PROVIDERS)}",
        )

    from app.auth.oauth import get_oauth_manager
    from app.config import settings

    redirect_uri = f"{settings.oauth_redirect_base_url}/api/auth/oauth/callback"
    manager = get_oauth_manager()
    try:
        if provider == "oidc":
            url, state = await manager.get_authorize_url_async(provider, redirect_uri)
        else:
            url, state = manager.get_authorize_url(provider, redirect_uri)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    store.log_audit(
        action="auth.oauth.authorize",
        resource=f"/api/auth/oauth/authorize?provider={provider}",
        client_ip=request.client.host if request.client else "unknown",
        status_code=200,
    )
    return {"redirect_url": url, "state": state, "provider": provider}


@router.get("/oauth/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    store: AuthStore = Depends(get_auth_store),
) -> Dict[str, Any]:
    """
    Handle the OAuth2 / OIDC authorization code callback.

    Exchanges the authorization code for tokens, validates the identity, and
    returns a Meridian JWT access token.  New users are auto-provisioned as
    ``viewer`` with no domain access; an admin must grant permissions afterwards.
    """
    if provider not in _SUPPORTED_OAUTH_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider!r}",
        )

    from app.auth.oauth import get_oauth_manager
    from app.config import settings
    from app.auth.jwt import _settings as _jwt_settings

    redirect_uri = f"{settings.oauth_redirect_base_url}/api/auth/oauth/callback"
    manager = get_oauth_manager()
    client_ip = request.client.host if request.client else "unknown"
    try:
        token = await manager.handle_callback(provider, code, state, redirect_uri, store)
    except ValueError as e:
        store.log_audit(
            action="auth.oauth.callback.failed",
            resource="/api/auth/oauth/callback",
            client_ip=client_ip,
            status_code=401,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        logger.error(f"OAuth callback error for provider={provider!r}: {e}")
        store.log_audit(
            action="auth.oauth.callback.error",
            resource="/api/auth/oauth/callback",
            client_ip=client_ip,
            status_code=502,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="OAuth provider error")

    store.log_audit(
        action="auth.oauth.login",
        resource="/api/auth/oauth/callback",
        client_ip=client_ip,
        status_code=200,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_hours": _jwt_settings().jwt_expiration_hours,
    }


@router.get("/me", response_model=UserProfile)
async def me(current_user: User = Depends(get_optional_current_user)) -> Dict[str, Any]:
    """Return the authenticated user's profile."""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "allowed_domains": current_user.allowed_domains,
        "created_at": current_user.created_at,
    }

# MERIDIAN Authentication & Authorization Guide

**Version:** 0.8.0

---

## Table of Contents

1. [Overview](#overview)
2. [Username / Password Login](#username--password-login)
3. [Google OAuth2 Setup](#google-oauth2-setup)
4. [Generic OIDC Setup (Okta, Keycloak, Azure AD)](#generic-oidc-setup)
5. [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
6. [JWT Configuration](#jwt-configuration)
7. [Configuration Reference](#configuration-reference)
8. [Multi-Worker Warning](#multi-worker-warning)

---

## Overview

MERIDIAN supports three authentication methods:

| Method | Use case |
|--------|----------|
| Username + Password | Local development, internal users |
| Google OAuth2 | Consumer Google accounts (Workspace or personal) |
| Generic OIDC | Enterprise SSO — Okta, Keycloak, Azure AD, any OIDC provider |

All methods issue the same Meridian JWT after successful login. Downstream authorization (RBAC, domain-level access control) is identical regardless of how the user authenticated.

---

## Username / Password Login

### Register a user

```http
POST /api/auth/register
Content-Type: application/json

{"username": "alice", "password": "secure_password", "email": "alice@company.com"}
```

**Notes:**
- Default role is `viewer`.
- The **first** registered user is automatically promoted to `admin` (bootstrap mode).
- Subsequent admins must be created by an existing admin.

### Log in

```http
POST /api/auth/login
Content-Type: application/json

{"username": "alice", "password": "secure_password"}
```

**Response:**
```json
{"access_token": "<jwt>", "token_type": "bearer"}
```

Use the token in all subsequent requests:

```http
Authorization: Bearer <jwt>
```

Tokens expire after **30 minutes** by default (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`).

---

## Google OAuth2 Setup

### 1. Create OAuth credentials

1. Go to [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. Create an **OAuth 2.0 Client ID** (type: Web application)
3. Add an **Authorized redirect URI**:
   ```
   http://localhost:8000/api/auth/oauth/callback
   ```
   (Replace `localhost:8000` with your production domain in production.)
4. Copy **Client ID** and **Client Secret**

### 2. Set environment variables

```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
OAUTH_REDIRECT_BASE_URL=http://localhost:8000
```

### 3. Login flow

**Step 1 — Get the authorization URL:**
```http
GET /api/auth/oauth/authorize?provider=google
```

Response:
```json
{
  "redirect_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "<csrf-token>",
  "provider": "google"
}
```

**Step 2 — Redirect the user's browser** to `redirect_url`.

**Step 3 — Handle the callback** (Google redirects here automatically):
```http
GET /api/auth/oauth/callback?provider=google&code=<auth-code>&state=<csrf-token>
```

Response:
```json
{
  "access_token": "<meridian-jwt>",
  "token_type": "bearer",
  "expires_in_hours": 24
}
```

New OAuth users are auto-provisioned as `viewer`. An admin must grant additional roles or domain access.

---

## Generic OIDC Setup

Any provider that supports the [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html) spec (`/.well-known/openid-configuration`) works out of the box.

### Environment variables

```bash
OIDC_ISSUER=https://your-provider.example.com
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
OAUTH_REDIRECT_BASE_URL=http://localhost:8000
```

> **All three OIDC variables must be set together.** Providing only one or two raises a `ValueError` at startup (enforced by `@model_validator` in `config.py`).

### Provider-specific examples

**Okta:**
```bash
OIDC_ISSUER=https://your-org.okta.com
OIDC_CLIENT_ID=0oa...
OIDC_CLIENT_SECRET=...
```

**Keycloak:**
```bash
OIDC_ISSUER=https://keycloak.example.com/realms/meridian
OIDC_CLIENT_ID=meridian-client
OIDC_CLIENT_SECRET=...
```

**Azure AD:**
```bash
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_CLIENT_ID=<app-id>
OIDC_CLIENT_SECRET=...
```

### Login flow

Same as Google, but use `provider=oidc`:

```http
GET /api/auth/oauth/authorize?provider=oidc
GET /api/auth/oauth/callback?provider=oidc&code=...&state=...
```

Meridian fetches the provider's endpoints automatically from `{OIDC_ISSUER}/.well-known/openid-configuration`.

---

## Role-Based Access Control (RBAC)

### Roles

| Role | Permissions |
|------|-------------|
| `viewer` | Execute queries on allowed domains; read history |
| `analyst` | All viewer permissions + export, streaming, async jobs |
| `admin` | All permissions + user management, domain onboarding, performance reports |

### Domain-level access control

Users can be restricted to specific domains. A user with `allowed_domains=["sales"]` cannot query the `finance` or `operations` domain.

Admins can see and query all domains.

### How roles are enforced

- JWT payload includes `role` claim
- FastAPI dependency `require_role(["admin"])` rejects requests with insufficient role
- Domain access is checked in the orchestrator before routing

### Granting roles (admin only)

Currently managed directly in the user store (`app/auth/store.py`). An admin API for role assignment is planned for a future phase.

---

## JWT Configuration

```bash
SECRET_KEY=your-secret-key-min-32-chars    # Required in production
ACCESS_TOKEN_EXPIRE_MINUTES=30             # Default: 30
ALGORITHM=HS256                            # Default: HS256
```

> **Production requirement**: If `DEBUG=false`, a weak or default `SECRET_KEY` raises a startup error. Generate one with:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

OAuth-issued tokens expire after **24 hours** by default (longer than password tokens since OAuth sessions carry their own expiry).

---

## Configuration Reference

```bash
# Username/password auth
SECRET_KEY=...
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Google OAuth2
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
OAUTH_REDIRECT_BASE_URL=http://localhost:8000

# Generic OIDC (all three required together, or all omitted)
OIDC_ISSUER=https://your-provider.example.com
OIDC_CLIENT_ID=...
OIDC_CLIENT_SECRET=...
```

See `.env.example` for all available options.

---

## Multi-Worker Warning

OAuth CSRF state tokens are stored in **`_STATE_STORE`** — an in-process Python dictionary in `app/auth/oauth.py`.

This works correctly for single-worker deployments (`uvicorn`, `make dev`). It **breaks** in multi-worker setups:

- **Gunicorn with `-w N` workers** — the authorize and callback requests may hit different workers, causing the state validation to fail
- **Kubernetes with multiple replicas** — same problem

**Fix**: Replace `_STATE_STORE` in `app/auth/oauth.py` with a Redis-backed store using `redis-py` or `aioredis`:

```python
import redis

_redis = redis.Redis(host=settings.redis_host, port=settings.redis_port)

def _store_state(state: str, provider: str, ttl: int = 600) -> None:
    _redis.setex(f"oauth:state:{state}", ttl, provider)

def _pop_state(state: str) -> Optional[str]:
    val = _redis.getdel(f"oauth:state:{state}")
    return val.decode() if val else None
```

Username/password login is stateless (JWT only) and is not affected by multi-worker deployments.

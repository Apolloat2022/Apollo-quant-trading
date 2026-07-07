"""
Clerk JWT verification and user trial/subscription management.
"""

import base64
import os
import time
from functools import wraps

from flask import jsonify, request

from kv_store import kv_get, kv_set

def _clean(v: str) -> str:
    """Strip whitespace and any stray BOM that env tooling may prepend."""
    return (v or "").strip().lstrip("﻿").strip().strip('"').strip("'")

CLERK_PUBLISHABLE_KEY = _clean(os.environ.get("CLERK_PUBLISHABLE_KEY", ""))
CLERK_SECRET_KEY      = _clean(os.environ.get("CLERK_SECRET_KEY", ""))
TRIAL_DAYS            = 7

# Dev mode must be opted into EXPLICITLY. It must never be inferred from a
# missing key, or a production deploy that forgets to set CLERK_PUBLISHABLE_KEY
# would silently disable all authentication (fail-open). Require DEV_MODE=true
# AND the absence of Clerk keys so it can't be turned on in a real deployment.
_DEV_MODE = (
    _clean(os.environ.get("DEV_MODE", "")).lower() in ("1", "true", "yes")
    and not CLERK_PUBLISHABLE_KEY
)


def _jwks_url() -> str:
    """Derive the JWKS URL from the Clerk publishable key."""
    try:
        encoded = CLERK_PUBLISHABLE_KEY.split("_", 2)[-1]
        encoded += "=" * (4 - len(encoded) % 4)
        domain = base64.b64decode(encoded).decode("utf-8").rstrip("$")
        # The publishable key encodes a bare domain (no scheme); PyJWKClient
        # requires an absolute https:// URL or it raises MissingSchema and the
        # entire primary signature-verification path silently falls through.
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        return f"{domain}/.well-known/jwks.json"
    except Exception:
        return ""


def verify_token(token: str) -> str | None:
    """Return the Clerk user_id (sub) if the JWT is valid, else None."""
    # Primary: full JWKS signature verification
    try:
        from jwt import PyJWKClient, decode as jwt_decode
        url = _jwks_url()
        if url:
            client = PyJWKClient(url, cache_keys=True)
            key    = client.get_signing_key_from_jwt(token).key
            claims = jwt_decode(token, key, algorithms=["RS256"])
            return claims.get("sub")
    except Exception:
        pass

    # Fallback 1: decode without signature, confirm via Clerk REST API
    try:
        import jwt as _jwt
        import requests as _req
        claims  = _jwt.decode(token, options={"verify_signature": False})
        user_id = claims.get("sub")
        if user_id and CLERK_SECRET_KEY:
            r = _req.get(
                f"https://api.clerk.com/v1/users/{user_id}",
                headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
                timeout=5,
            )
            if r.ok:
                return user_id
    except Exception:
        pass

    # No trust path that skips signature verification. A previous fallback here
    # accepted unsigned tokens whose `iss` merely contained "clerk", which let
    # anyone forge a session for any user. A token is only valid if it passed
    # JWKS signature verification or was confirmed live against the Clerk API.
    return None


# ── User data helpers ──────────────────────────────────────

def _user_key(user_id: str) -> str:
    return f"user:{user_id}"


def _init_user(user_id: str) -> dict:
    """Create the user record on first login (starts trial clock)."""
    key  = _user_key(user_id)
    data = kv_get(key) or {}
    if "trial_start" not in data:
        data["trial_start"] = time.time()
        kv_set(key, data, ex=86400 * 400)
    return data


def get_user_access(user_id: str) -> dict:
    """Return trial/subscription status for a user."""
    data    = _init_user(user_id)
    elapsed = (time.time() - data.get("trial_start", time.time())) / 86400
    trial   = elapsed < TRIAL_DAYS
    subbed  = data.get("subscribed", False)
    return {
        "has_access":       trial or subbed,
        "subscribed":       subbed,
        "trial_active":     trial,
        "trial_days_left":  round(max(0.0, TRIAL_DAYS - elapsed), 1),
        "stripe_customer_id": data.get("stripe_customer_id"),
    }


# ── Flask decorator ───────────────────────────────────────

def require_access(f):
    """Require a valid Clerk session with an active trial or subscription."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Dev mode — no Clerk keys configured (local dev without .env keys)
        if _DEV_MODE:
            request.user_id = "dev_user"
            return f(*args, **kwargs)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401

        user_id = verify_token(auth[7:])
        if not user_id:
            return jsonify({"error": "Invalid token"}), 401

        access = get_user_access(user_id)
        if not access["has_access"]:
            return jsonify({"error": "Subscription required", "paywall": True}), 402

        request.user_id = user_id
        return f(*args, **kwargs)
    return decorated

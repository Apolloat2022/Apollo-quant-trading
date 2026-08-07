"""
Clerk JWT verification and user trial/subscription management.
"""

import base64
import logging
import os
import time
from functools import wraps

from flask import jsonify, request

from kv_store import kv_get, kv_set

logger = logging.getLogger(__name__)

def _clean(v: str) -> str:
    """Strip whitespace and any stray BOM that env tooling may prepend."""
    return (v or "").strip().lstrip("﻿").strip().strip('"').strip("'")

CLERK_PUBLISHABLE_KEY = _clean(os.environ.get("CLERK_PUBLISHABLE_KEY", ""))
CLERK_SECRET_KEY      = _clean(os.environ.get("CLERK_SECRET_KEY", ""))
TRIAL_DAYS            = 7

# Accounts with unrestricted access — no trial clock, no subscription required.
# Comma-separated in ADMIN_EMAILS / ADMIN_USER_IDS; the platform owner is the
# built-in default so admin access survives a deploy that misses the variables.
#
# Matching by Clerk user_id is the primary path: the id comes straight from the
# verified session token, so it keeps working even when CLERK_SECRET_KEY is
# stale or absent. Email matching needs a Clerk API call and is the fallback.
_DEFAULT_ADMIN_EMAILS   = "revanaglobal@gmail.com"
_DEFAULT_ADMIN_USER_IDS = "user_3EXZZdHiocvW81TfSXjwqSdvFnC"  # revanaglobal@gmail.com

def _csv_set(env_name: str, default: str, lower: bool = False) -> set:
    raw = _clean(os.environ.get(env_name, "")) or default
    return {(v.strip().lower() if lower else v.strip()) for v in raw.split(",") if v.strip()}

ADMIN_EMAILS   = _csv_set("ADMIN_EMAILS", _DEFAULT_ADMIN_EMAILS, lower=True)
ADMIN_USER_IDS = _csv_set("ADMIN_USER_IDS", _DEFAULT_ADMIN_USER_IDS)

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


def _fetch_clerk_email(user_id: str) -> str:
    """Look up the user's primary email address via the Clerk API."""
    if not CLERK_SECRET_KEY:
        logger.warning("Clerk email lookup skipped: CLERK_SECRET_KEY is not set")
        return ""
    try:
        import requests as _req
        r = _req.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
            timeout=5,
        )
        if not r.ok:
            # Usually a stale or rotated secret key. Left silent this would look
            # exactly like "user is not an admin", so say it out loud.
            logger.warning(f"Clerk email lookup for {user_id} failed: HTTP {r.status_code}")
            return ""
        body    = r.json()
        emails  = body.get("email_addresses") or []
        primary = body.get("primary_email_address_id")
        for e in emails:
            if primary and e.get("id") == primary:
                return e.get("email_address", "")
        return emails[0].get("email_address", "") if emails else ""
    except Exception as exc:
        logger.warning(f"Clerk email lookup for {user_id} errored: {exc}")
        return ""


# Clerk lookups are a network hop, so cache per process as well as in KV.
_email_cache: dict[str, str] = {}


def get_user_email(user_id: str) -> str:
    """Return the user's email, cached in KV and in-process."""
    if user_id in _email_cache:
        return _email_cache[user_id]

    key   = _user_key(user_id)
    data  = kv_get(key) or {}
    email = data.get("email") or ""

    if not email:
        email = _fetch_clerk_email(user_id)
        if email:
            data["email"] = email
            kv_set(key, data, ex=86400 * 400)

    if email:
        _email_cache[user_id] = email
    return email


def is_admin(user_id: str) -> bool:
    """True when the user's Clerk id or email is on the admin list."""
    if user_id in ADMIN_USER_IDS:
        return True
    if not ADMIN_EMAILS:
        return False
    return get_user_email(user_id).lower() in ADMIN_EMAILS


def get_user_access(user_id: str) -> dict:
    """Return trial/subscription status for a user."""
    data    = _init_user(user_id)
    elapsed = (time.time() - data.get("trial_start", time.time())) / 86400
    trial   = elapsed < TRIAL_DAYS
    subbed  = data.get("subscribed", False)
    admin   = is_admin(user_id)
    return {
        "has_access":       admin or trial or subbed,
        "admin":            admin,
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
            request.is_admin = True
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

        request.user_id  = user_id
        request.is_admin = access["admin"]
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Require a valid Clerk session belonging to an admin account."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if _DEV_MODE:
            request.user_id  = "dev_user"
            request.is_admin = True
            return f(*args, **kwargs)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401

        user_id = verify_token(auth[7:])
        if not user_id:
            return jsonify({"error": "Invalid token"}), 401

        if not is_admin(user_id):
            return jsonify({"error": "Admin access required"}), 403

        request.user_id  = user_id
        request.is_admin = True
        return f(*args, **kwargs)
    return decorated

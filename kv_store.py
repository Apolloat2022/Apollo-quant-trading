"""
Vercel KV (Upstash Redis) helper.
Reads KV_REST_API_URL and KV_REST_API_TOKEN from environment.
Falls back silently when env vars are not set (local dev without KV).
"""

import json
import os

import requests

# Support both Upstash direct and Vercel KV variable names
_URL   = os.environ.get("UPSTASH_REDIS_REST_URL")   or os.environ.get("KV_REST_API_URL",   "")
_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN", "")

KV_AVAILABLE = bool(_URL and _TOKEN)


def _headers() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}"}


def kv_set(key: str, value, ex: int = 7200) -> bool:
    """
    Store value under key with an optional TTL (seconds).
    Value is JSON-serialised before storage.
    Returns True on success, False on any error.
    """
    if not KV_AVAILABLE:
        return False
    try:
        r = requests.post(
            f"{_URL}/set/{key}",
            data=json.dumps(value),
            headers=_headers(),
            params={"ex": ex},
            timeout=8,
        )
        return r.ok
    except Exception:
        return False


def kv_get(key: str):
    """
    Retrieve and JSON-deserialise value stored under key.
    Returns None on miss or any error.
    """
    if not KV_AVAILABLE:
        return None
    try:
        r = requests.get(f"{_URL}/get/{key}", headers=_headers(), timeout=8)
        if not r.ok:
            return None
        raw = r.json().get("result")
        if raw is None:
            return None
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None

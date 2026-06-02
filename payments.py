"""
Stripe payment integration — Checkout, Customer Portal, and webhook handling.
"""

import os

import stripe


def _clean(v: str) -> str:
    """Strip whitespace, stray BOM, and quotes that env tooling may add."""
    return (v or "").strip().lstrip("﻿").strip().strip('"').strip("'")

stripe.api_key = _clean(os.environ.get("STRIPE_SECRET_KEY", ""))

PRICE_ID       = _clean(os.environ.get("STRIPE_PRICE_ID", ""))
WEBHOOK_SECRET = _clean(os.environ.get("STRIPE_WEBHOOK_SECRET", ""))
BASE_URL       = _clean(os.environ.get("BASE_URL", "https://apollotechnologiesus.com/quant-trading"))
# Target account for Organization API keys — sent as the Stripe-Context header.
# Leave unset when using a standard account-scoped key (then no context is sent).
STRIPE_ACCOUNT = _clean(os.environ.get("STRIPE_ACCOUNT", ""))


def _ctx() -> dict:
    """Per-request options: attach Stripe-Context when an org key + account are set."""
    return {"stripe_context": STRIPE_ACCOUNT} if STRIPE_ACCOUNT else {}


def create_checkout_session(user_id: str, user_email: str = "") -> str:
    """Create a Stripe Checkout session and return the redirect URL."""
    kwargs: dict = dict(
        mode="subscription",
        line_items=[{"price": PRICE_ID, "quantity": 1}],
        success_url=f"{BASE_URL}/?subscribed=true",
        cancel_url=f"{BASE_URL}/",
        metadata={"user_id": user_id},
        allow_promotion_codes=True,
    )
    if user_email:
        kwargs["customer_email"] = user_email
    session = stripe.checkout.Session.create(**kwargs, **_ctx())
    return session.url


def create_portal_session(customer_id: str) -> str:
    """Create a Stripe Customer Portal session for managing subscriptions."""
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=BASE_URL,
        **_ctx(),
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> bool:
    """Verify and process a Stripe webhook event. Returns True on success."""
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except Exception:
        return False

    from kv_store import kv_get, kv_set

    etype = event["type"]
    obj   = event["data"]["object"]

    if etype == "checkout.session.completed":
        user_id     = obj.get("metadata", {}).get("user_id")
        customer_id = obj.get("customer")
        if user_id:
            data = kv_get(f"user:{user_id}") or {}
            data["subscribed"]         = True
            data["stripe_customer_id"] = customer_id
            kv_set(f"user:{user_id}", data, ex=86400 * 400)
            if customer_id:
                # Reverse lookup: Stripe customer → Clerk user_id
                kv_set(f"stripe:{customer_id}", user_id, ex=86400 * 400)

    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        customer_id = obj.get("customer")
        if customer_id:
            user_id = kv_get(f"stripe:{customer_id}")
            if user_id:
                data = kv_get(f"user:{user_id}") or {}
                data["subscribed"] = False
                kv_set(f"user:{user_id}", data, ex=86400 * 400)

    return True

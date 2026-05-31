"""
Stripe payment integration — Checkout, Customer Portal, and webhook handling.
"""

import os

import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

PRICE_ID       = os.environ.get("STRIPE_PRICE_ID", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
BASE_URL       = os.environ.get("BASE_URL", "https://apollo-quant-trading.vercel.app")


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
    session = stripe.checkout.Session.create(**kwargs)
    return session.url


def create_portal_session(customer_id: str) -> str:
    """Create a Stripe Customer Portal session for managing subscriptions."""
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=BASE_URL,
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

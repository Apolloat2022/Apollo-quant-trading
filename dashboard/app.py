"""
Flask Web Dashboard — Vercel-compatible.
Auth: Clerk JWT  |  Payments: Stripe  |  Storage: Upstash KV
"""

import logging
import os
import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("America/Chicago")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, jsonify, render_template, render_template_string, request
from auth import get_user_access, require_access
from kv_store import KV_AVAILABLE, kv_get, kv_set

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "quant-trading-secret-2024")

# ── In-memory fallback for local dev (no KV) ──────────────
_signals_store: list[dict] = []
_lock = threading.Lock()


def add_signal(signal: dict) -> None:
    signal.setdefault("timestamp", datetime.now(_TZ).isoformat())
    with _lock:
        _signals_store.append(signal)
        if len(_signals_store) > 500:
            _signals_store.pop(0)


def _read_signals(limit: int = 100) -> list[dict]:
    if KV_AVAILABLE:
        return (kv_get("signals:latest") or [])[:limit]
    with _lock:
        return list(reversed(_signals_store[-limit:]))


# ──────────────────────────────────────────────────────────
# PUBLIC ROUTES
# ──────────────────────────────────────────────────────────

_LEGAL_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{{ title }} — Apollo Quant Trading</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#050b16;color:#c9d1d9;font-family:'Segoe UI',sans-serif;min-height:100vh}
    header{background:rgba(12,18,28,.9);border-bottom:1px solid rgba(56,189,248,.12);
      padding:16px 32px;display:flex;align-items:center;justify-content:space-between}
    header a{color:#38bdf8;text-decoration:none;font-weight:700;font-size:1rem}
    header a:hover{opacity:.8}
    .back{font-size:0.82rem;color:rgba(139,148,158,.6);text-decoration:none;
      border:1px solid rgba(48,54,61,.8);border-radius:6px;padding:5px 12px;transition:color .2s}
    .back:hover{color:#c9d1d9}
    main{max-width:760px;margin:0 auto;padding:56px 32px 80px}
    h1{font-size:1.8rem;font-weight:800;letter-spacing:-.02em;
      background:linear-gradient(135deg,#f0f6ff,#38bdf8);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;
      background-clip:text;margin-bottom:8px}
    .updated{font-size:0.75rem;color:rgba(139,148,158,.5);margin-bottom:40px}
    h2{font-size:1rem;font-weight:700;color:#e6edf3;margin:32px 0 10px}
    p,li{font-size:0.88rem;color:rgba(139,148,158,.85);line-height:1.75;margin-bottom:10px}
    ul{padding-left:20px;margin-bottom:10px}
    footer{text-align:center;padding:32px;font-size:0.72rem;color:rgba(139,148,158,.3)}
  </style>
</head>
<body>
<header>
  <a href="/">⚡ Apollo Quant Trading</a>
  <a href="/" class="back">← Back</a>
</header>
<main>
  <h1>{{ title }}</h1>
  <p class="updated">Last updated: May 2026</p>
  {{ body | safe }}
</main>
<footer>© 2026 Apollo Quant Trading. All rights reserved. &nbsp;·&nbsp; Powered by Apollo Technologies US</footer>
</body>
</html>"""

_TERMS_BODY = """
<h2>1. Acceptance of Terms</h2>
<p>By accessing or using Apollo Quant Trading ("the Platform"), you agree to be bound by these Terms of Service. If you do not agree, you may not use the Platform.</p>

<h2>2. Educational Purpose Only</h2>
<p>The Platform provides algorithmic signal tools, market analysis, and backtesting capabilities for <strong>educational and informational purposes only</strong>. Nothing on this Platform constitutes personal financial advice, investment recommendations, or a solicitation to buy or sell any financial instrument, security, or asset.</p>

<h2>3. Risk Disclosure</h2>
<p>All trading and investing involves substantial risk of loss. You may lose some or all of your invested capital. Past performance of any strategy, signal, or algorithm shown on this Platform is not indicative of future results. You are solely responsible for any trading decisions you make.</p>

<h2>4. No Financial Advisory Relationship</h2>
<p>Apollo Quant Trading is not a registered investment advisor, broker-dealer, or financial institution. Use of this Platform does not create an advisory or fiduciary relationship between you and Apollo Quant Trading.</p>

<h2>5. Subscriptions and Billing</h2>
<p>Paid subscriptions are billed monthly. You may cancel at any time through the Stripe Customer Portal accessible from your account. Cancellations take effect at the end of the current billing period. No refunds are issued for partial periods.</p>

<h2>6. Acceptable Use</h2>
<p>You agree not to: (a) reverse-engineer or scrape the Platform; (b) share account credentials; (c) use the Platform for any unlawful purpose; (d) attempt to gain unauthorized access to any system or data.</p>

<h2>7. Limitation of Liability</h2>
<p>To the maximum extent permitted by law, Apollo Quant Trading shall not be liable for any direct, indirect, incidental, or consequential damages arising from your use of the Platform or reliance on any signals or information provided.</p>

<h2>8. Modifications</h2>
<p>We reserve the right to modify these Terms at any time. Continued use of the Platform after changes constitutes acceptance of the updated Terms.</p>

<h2>9. Contact</h2>
<p>For questions regarding these Terms, contact us at <a href="mailto:Robinpandey@apollotechnologiesus.com" style="color:#38bdf8">Robinpandey@apollotechnologiesus.com</a>.</p>
"""

_PRIVACY_BODY = """
<h2>1. Information We Collect</h2>
<p>We collect information you provide when creating an account (name, email address) via Clerk, and payment information processed by Stripe. We do not store raw payment card data. We also collect usage data such as login timestamps and feature interactions.</p>

<h2>2. How We Use Your Information</h2>
<ul>
  <li>To provide and maintain your account and subscription</li>
  <li>To process payments and manage billing via Stripe</li>
  <li>To send service-related communications (alerts, notifications)</li>
  <li>To improve and monitor platform performance</li>
</ul>

<h2>3. Data Storage</h2>
<p>Account authentication is handled by Clerk. Payment data is handled by Stripe. Signal and subscription status data is stored in Upstash (Redis). We do not sell your personal information to third parties.</p>

<h2>4. Third-Party Services</h2>
<p>We use the following third-party services: <strong>Clerk</strong> (authentication), <strong>Stripe</strong> (payments), <strong>Upstash</strong> (data storage), <strong>Vercel</strong> (hosting), and <strong>Google Gemini</strong> (AI summaries). Each service operates under its own privacy policy.</p>

<h2>5. Cookies and Sessions</h2>
<p>We use session cookies necessary for authentication. We do not use tracking or advertising cookies.</p>

<h2>6. Data Retention</h2>
<p>We retain your account data for as long as your account is active. You may request deletion of your data at any time by contacting us.</p>

<h2>7. Your Rights</h2>
<p>Depending on your jurisdiction, you may have rights to access, correct, or delete your personal data. To exercise these rights, contact us at <a href="mailto:Robinpandey@apollotechnologiesus.com" style="color:#38bdf8">Robinpandey@apollotechnologiesus.com</a>.</p>

<h2>8. Changes to This Policy</h2>
<p>We may update this Privacy Policy periodically. We will notify you of significant changes via email or a notice on the Platform.</p>

<h2>9. Contact</h2>
<p>For privacy-related questions, contact <a href="mailto:Robinpandey@apollotechnologiesus.com" style="color:#38bdf8">Robinpandey@apollotechnologiesus.com</a>.</p>
"""


@app.route("/")
def index():
    return render_template(
        "dashboard.html",
        clerk_pk=os.getenv("CLERK_PUBLISHABLE_KEY", ""),
    )


@app.route("/terms")
def terms():
    return render_template_string(_LEGAL_PAGE, title="Terms of Service", body=_TERMS_BODY)


@app.route("/privacy")
def privacy():
    return render_template_string(_LEGAL_PAGE, title="Privacy Policy", body=_PRIVACY_BODY)


@app.route("/api/add_signal", methods=["POST"])
def api_add_signal():
    """Receive a signal from the local scanner process."""
    try:
        signal = request.get_json(force=True) or {}
        if signal:
            add_signal(signal)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────
# AUTH ROUTES
# ──────────────────────────────────────────────────────────

@app.route("/api/auth/status")
def api_auth_status():
    """Return trial/subscription status for the authenticated user."""
    from auth import _DEV_MODE, verify_token

    if _DEV_MODE:
        return jsonify({
            "has_access": True, "subscribed": False,
            "trial_active": True, "trial_days_left": 7.0,
        })

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    user_id = verify_token(auth[7:])
    if not user_id:
        return jsonify({"error": "Invalid token"}), 401

    return jsonify(get_user_access(user_id))


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    """Create a Stripe Checkout session and return the redirect URL."""
    from auth import _DEV_MODE, verify_token
    from payments import create_checkout_session

    if _DEV_MODE:
        return jsonify({"url": "/"})

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    user_id = verify_token(auth[7:])
    if not user_id:
        return jsonify({"error": "Invalid token"}), 401

    # Try to get email from Clerk API
    email = _get_clerk_email(user_id)
    url = create_checkout_session(user_id, email)
    return jsonify({"url": url})


@app.route("/api/portal", methods=["POST"])
def api_portal():
    """Create a Stripe Customer Portal session."""
    from auth import _DEV_MODE, verify_token
    from payments import create_portal_session

    if _DEV_MODE:
        return jsonify({"url": "/"})

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    user_id = verify_token(auth[7:])
    if not user_id:
        return jsonify({"error": "Invalid token"}), 401

    access = get_user_access(user_id)
    customer_id = access.get("stripe_customer_id")
    if not customer_id:
        return jsonify({"error": "No active subscription"}), 400

    return jsonify({"url": create_portal_session(customer_id)})


@app.route("/api/webhook", methods=["POST"])
def api_webhook():
    """Stripe webhook endpoint — updates subscription status in KV."""
    from payments import handle_webhook
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature", "")
    if handle_webhook(payload, sig):
        return jsonify({"ok": True})
    return jsonify({"error": "Webhook verification failed"}), 400


# ──────────────────────────────────────────────────────────
# PROTECTED DATA ROUTES
# ──────────────────────────────────────────────────────────

@app.route("/api/signals")
@require_access
def api_signals():
    limit = int(request.args.get("limit", 100))
    return jsonify(_read_signals(limit))


@app.route("/api/metrics")
@require_access
def api_metrics():
    signals  = _read_signals(500)
    total    = len(signals)
    buys     = sum(1 for s in signals if s.get("signal") == "BUY")
    sells    = sum(1 for s in signals if s.get("signal") == "SELL")
    holds    = total - buys - sells
    avg_conf = sum(s.get("confidence", 0) for s in signals) / (total or 1)
    last_run = kv_get("scanner:last_run") if KV_AVAILABLE else None

    return jsonify({
        "total_signals":  total,
        "buy_count":      buys,
        "sell_count":     sells,
        "hold_count":     holds,
        "avg_confidence": round(avg_conf, 4),
        "last_scan":      last_run,
    })


@app.route("/api/backtest", methods=["POST"])
@require_access
def api_backtest():
    return _create_backtest_job(request, mode="backtest")


@app.route("/api/compare", methods=["POST"])
@require_access
def api_compare():
    return _create_backtest_job(request, mode="compare")


@app.route("/api/backtest/status/<job_id>")
@require_access
def api_backtest_status(job_id):
    job = kv_get(f"backtest:{job_id}")
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


def _create_backtest_job(req, mode: str):
    """Create a backtest job in KV and trigger GitHub Actions."""
    import uuid, time as _time
    try:
        body = req.get_json(force=True) or {}
        job_id = uuid.uuid4().hex[:10]
        job = {
            "id":     job_id,
            "status": "pending",
            "params": {
                "symbol":     body.get("symbol", "AAPL"),
                "asset_type": body.get("asset_type", "stock"),
                "capital":    float(body.get("capital", 10_000)),
                "strategy":   body.get("strategy", "combined"),
                "mode":       mode,
            },
            "created_at": _time.time(),
        }
        kv_set(f"backtest:{job_id}", job, ex=3600)

        triggered = _trigger_gh_backtest(job_id)
        if not triggered:
            job["status"] = "error"
            job["error"]  = "Failed to trigger GitHub Actions — check GITHUB_PAT secret."
            kv_set(f"backtest:{job_id}", job, ex=3600)

        return jsonify({"job_id": job_id, "status": job["status"]})
    except Exception as exc:
        logger.error(f"Backtest job creation error: {exc}")
        return jsonify({"error": str(exc)}), 500


def _trigger_gh_backtest(job_id: str) -> bool:
    """Trigger the backtest workflow via GitHub API."""
    try:
        import requests as _req
        token = os.environ.get("GITHUB_PAT", "")
        repo  = os.environ.get("GITHUB_REPO", "Apolloat2022/Apollo-quant-trading")
        if not token:
            logger.warning("GITHUB_PAT not set — cannot trigger workflow.")
            return False
        r = _req.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/backtest.yml/dispatches",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept":        "application/vnd.github.v3+json",
            },
            json={"ref": "main", "inputs": {"job_id": job_id}},
            timeout=10,
        )
        if not r.ok:
            logger.error(f"GH dispatch failed: {r.status_code} {r.text}")
        return r.ok
    except Exception as exc:
        logger.error(f"GH dispatch exception: {exc}")
        return False


# ──────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────

def _get_clerk_email(user_id: str) -> str:
    """Fetch the user's primary email from the Clerk API."""
    try:
        import requests as _req
        r = _req.get(
            f"https://api.clerk.dev/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {os.environ.get('CLERK_SECRET_KEY', '')}"},
            timeout=5,
        )
        if r.ok:
            emails = r.json().get("email_addresses", [])
            if emails:
                return emails[0].get("email_address", "")
    except Exception:
        pass
    return ""


def run_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    logger.info(f"Dashboard starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)

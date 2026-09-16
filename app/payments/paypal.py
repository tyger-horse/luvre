"""PayPal Orders v2, redirect flow (§8.1). M3.

Money stays integer cents inside our walls; only the PayPal request
itself carries the decimal string PayPal demands. The webhook
(PAYMENT.CAPTURE.COMPLETED) is authoritative — the return path merely
attempts a capture as a convenience. Sandbox first: flipping
PAYPAL_ENV=live is the only change.
"""

from __future__ import annotations

import json

import httpx

from app.config import settings

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
LIVE_BASE = "https://api-m.paypal.com"


class PayPalNotConfigured(RuntimeError):
    pass


class PayPalError(RuntimeError):
    pass


def base_url() -> str:
    return LIVE_BASE if settings.PAYPAL_ENV == "live" else SANDBOX_BASE


def configured() -> bool:
    return bool(settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET)


def _token() -> str:
    if not configured():
        raise PayPalNotConfigured("PayPal is not yet configured at the desk.")
    try:
        res = httpx.post(
            f"{base_url()}/v1/oauth2/token",
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            timeout=15,
        )
        res.raise_for_status()
        return res.json()["access_token"]
    except (httpx.HTTPError, KeyError) as exc:
        raise PayPalError(f"PayPal would not speak: {exc}") from exc


def create_order(
    amount_cents: int,
    reference_code: str,
    return_url: str,
    cancel_url: str,
    currency: str = "CAD",
) -> dict:
    """Create a CAPTURE order; return {provider_ref, approval_url}."""
    token = _token()
    value = f"{amount_cents / 100:.2f}"  # PayPal's wire format; ours stays cents
    try:
        res = httpx.post(
            f"{base_url()}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": reference_code,
                    "custom_id": reference_code,
                    "amount": {"currency_code": currency, "value": value},
                }],
                "application_context": {
                    "brand_name": "LUVRE",
                    "user_action": "PAY_NOW",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            },
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()
    except httpx.HTTPError as exc:
        raise PayPalError(f"PayPal refused the order: {exc}") from exc
    approve = next(
        (l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), ""
    )
    if not data.get("id") or not approve:
        raise PayPalError("PayPal answered without an approval road.")
    return {"provider_ref": data["id"], "approval_url": approve}


def capture_order(provider_ref: str) -> dict:
    """Attempt capture after the buyer's return. Returns {captured, status}."""
    token = _token()
    try:
        res = httpx.post(
            f"{base_url()}/v2/checkout/orders/{provider_ref}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={},
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()
    except httpx.HTTPError as exc:
        raise PayPalError(f"PayPal would not capture: {exc}") from exc
    return {"captured": data.get("status") == "COMPLETED", "status": data.get("status", "")}


def verify_webhook_signature(headers: dict[str, str], raw_body: bytes) -> bool:
    """Ask PayPal whether this webhook is really theirs. Any doubt → False."""
    if not configured() or not settings.PAYPAL_WEBHOOK_ID:
        return False
    lowered = {k.lower(): v for k, v in headers.items()}
    try:
        token = _token()
        res = httpx.post(
            f"{base_url()}/v1/notifications/verify-webhook-signature",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "transmission_id": lowered.get("paypal-transmission-id", ""),
                "transmission_time": lowered.get("paypal-transmission-time", ""),
                "cert_url": lowered.get("paypal-cert-url", ""),
                "auth_algo": lowered.get("paypal-auth-algo", ""),
                "transmission_sig": lowered.get("paypal-transmission-sig", ""),
                "webhook_id": settings.PAYPAL_WEBHOOK_ID,
                "webhook_event": json.loads(raw_body.decode("utf-8")),
            },
            timeout=15,
        )
        res.raise_for_status()
        return res.json().get("verification_status") == "SUCCESS"
    except Exception:
        return False


def order_id_from_event(payload: dict) -> tuple[str | None, str | None]:
    """Return (our_reference, paypal_order_id) from a webhook payload."""
    resource = payload.get("resource", {}) or {}
    custom = resource.get("custom_id")
    related = ((resource.get("supplementary_data", {}) or {}).get("related_ids", {}) or {}).get("order_id")
    return custom, related

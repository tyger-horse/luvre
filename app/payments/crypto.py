"""Crypto charges behind one interface (§8.2). M4.

Coinbase Commerce is the default for speed; BTCPay answers the same
calls when the founders choose self-custody (`CRYPTO_PROVIDER=btpay`).
The CAD amount is locked into the charge at creation; inside our walls
money stays integer cents — only the provider wire carries decimals.

Only a `confirmed` event (Coinbase `charge:confirmed`, BTCPay
`InvoiceSettled`) may mark an order paid. `pending` is a note, and the
status page says "settling" while one is open.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx

from app.config import settings


class CryptoNotConfigured(RuntimeError):
    pass


class CryptoError(RuntimeError):
    pass


def provider() -> str:
    return settings.CRYPTO_PROVIDER or "coinbase"


def verify_coinbase_signature(
    raw_body: bytes, timestamp: str, signature_header: str, secret: str
) -> bool:
    message = timestamp.encode("utf-8") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.strip().lower())


def verify_btpay_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.strip().lower())


CONFIRMED_TYPES = {"charge:confirmed", "confirmed", "InvoiceSettled"}
PENDING_TYPES = {"charge:pending", "pending", "InvoiceReceivedPayment", "InvoiceProcessing"}


def is_confirmed(event_type: str) -> bool:
    return event_type in CONFIRMED_TYPES


def is_pending(event_type: str) -> bool:
    return event_type in PENDING_TYPES


def _cad_decimal(amount_cents: int) -> str:
    return f"{amount_cents / 100:.2f}"  # provider wire format; ours stays cents


def create_charge(
    order_id: int, reference_code: str, piece_title: str, amount_cents: int
) -> dict:
    """Create a locked-CAD charge; return {provider_ref, checkout_url}."""
    if provider() == "btpay":
        return _btpay_invoice(order_id, reference_code, amount_cents)
    return _coinbase_charge(order_id, reference_code, piece_title, amount_cents)


def _coinbase_charge(
    order_id: int, reference_code: str, piece_title: str, amount_cents: int
) -> dict:
    if not settings.COINBASE_API_KEY:
        raise CryptoNotConfigured("Crypto is not yet configured at the desk.")
    try:
        res = httpx.post(
            "https://api.commerce.coinbase.com/charges",
            headers={
                "X-CC-Api-Key": settings.COINBASE_API_KEY,
                "X-CC-Version": "2018-03-22",
                "Content-Type": "application/json",
            },
            json={
                "name": f"LUVRE commission {reference_code}",
                "description": piece_title,
                "local_price": {"amount": _cad_decimal(amount_cents), "currency": "CAD"},
                "pricing_type": "fixed_price",
                "metadata": {"order_id": order_id, "reference": reference_code},
            },
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()["data"]
    except (httpx.HTTPError, KeyError) as exc:
        raise CryptoError(f"The charge would not open: {exc}") from exc
    if not data.get("id") or not data.get("hosted_url"):
        raise CryptoError("The charge answered without a road.")
    return {"provider_ref": data["id"], "checkout_url": data["hosted_url"]}


def _btpay_invoice(order_id: int, reference_code: str, amount_cents: int) -> dict:
    if not (settings.BTPAY_URL and settings.BTPAY_API_KEY and settings.BTPAY_STORE_ID):
        raise CryptoNotConfigured("BTCPay is not yet configured at the desk.")
    try:
        res = httpx.post(
            f"{settings.BTPAY_URL.rstrip('/')}/api/v1/stores/{settings.BTPAY_STORE_ID}/invoices",
            headers={
                "Authorization": f"token {settings.BTPAY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "amount": _cad_decimal(amount_cents),
                "currency": "CAD",
                "metadata": {"orderId": str(order_id), "reference": reference_code},
            },
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()
    except (httpx.HTTPError, KeyError) as exc:
        raise CryptoError(f"The invoice would not open: {exc}") from exc
    if not data.get("id") or not data.get("checkoutLink"):
        raise CryptoError("The invoice answered without a road.")
    return {"provider_ref": data["id"], "checkout_url": data["checkoutLink"]}

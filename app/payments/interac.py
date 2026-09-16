"""Interac e-Transfer reference-code flow (§8.3).

There is no merchant API: the buyer sends an e-Transfer to
INTERAC_TRANSFER_EMAIL with the order reference as the message, and the
studio marks the transfer received. This module formats the instructions
in the site's curatorial voice.
"""

from __future__ import annotations


def transfer_instructions(amount_cents: int, reference: str, email: str, ttl_hours: int) -> str:
    dollars = amount_cents / 100
    return (
        f"Send an Interac e-Transfer of CAD ${dollars:,.2f} to {email}, "
        f"with the message {reference}. The piece is held for you for {ttl_hours} hours."
    )

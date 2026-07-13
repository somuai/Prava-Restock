"""Offline Prava contract stub used before the hackathon integration window."""

from decimal import Decimal
from uuid import uuid4


STUB_MODE = True

_INTENTS: dict[str, dict] = {}


def create_intent(merchant, amount, item_description, constraints):
    """Return a fake Prava intent reference without performing network I/O."""
    parsed_amount = Decimal(str(amount))
    if parsed_amount <= 0:
        raise ValueError("amount must be positive")
    intent_ref = f"stub_intent_{uuid4().hex}"
    _INTENTS[intent_ref] = {
        "merchant": merchant,
        "amount": parsed_amount,
        "item_description": item_description,
        "constraints": dict(constraints),
    }
    # TODO: replace with real Prava SDK call — see TECHNICAL_PRD.md §15
    return intent_ref


def await_mandate(intent_ref):
    """Return an approved, rejected, or expired fake mandate outcome."""
    try:
        intent = _INTENTS[intent_ref]
    except KeyError as exc:
        raise ValueError(f"unknown intent_ref: {intent_ref}") from exc

    simulated = intent["constraints"].get("simulate_mandate", "approved")
    # TODO: replace with real Prava SDK call — see TECHNICAL_PRD.md §15
    if simulated == "rejected":
        return {"status": "rejected", "intent_ref": intent_ref}
    if simulated == "expired":
        return {"status": "expired", "intent_ref": intent_ref}
    if simulated != "approved":
        raise ValueError(f"unsupported simulated mandate outcome: {simulated}")
    return {
        "status": "approved",
        "mandate_id": f"stub_mandate_{uuid4().hex}",
        "credential_reference": f"stub_credential_{uuid4().hex}",
        "scope": {
            "merchant": intent["merchant"],
            "max_amount": str(intent["amount"]),
        },
        "approved_at": "2026-07-14T09:00:00+00:00",
    }

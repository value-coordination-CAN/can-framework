"""Settlement rail adapters for the bridge (WP-010 §1, §2).

The bridge borrows what money already has: acceptance, finality and liquidity. In a real
deployment each layer settles on a real rail. This module defines the seam, ships a
simulated rail for development and tests, and leaves the real adapters as placeholders.

    fiat             -> instant payments, RTGS, cards
    modernised_fiat  -> tokenised deposits, regulated stablecoins, a CBDC where issued,
                        offline value on a secure element
    direct_value     -> stays in CAN; settles down through one of the rails above

Implementing a rail means satisfying `SettlementRail` and registering it in `RAILS`.
Nothing else in the bridge changes.
"""
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from app.bridge.models import LAYER_FIAT, LAYER_MODERNISED


@dataclass(frozen=True)
class SettlementResult:
    rail: str
    external_ref: str
    status: str  # settled|pending|failed
    detail: str | None = None


class SettlementRail(Protocol):
    name: str
    layer: str

    def settle(self, *, amount: float, currency: str, reference: str, payer: str, payee: str) -> SettlementResult:
        """Move `amount` on this rail and return the rail's own reference."""


class SimulatedRail:
    """Development and test rail: records the movement, moves no real money."""

    name = "simulated"
    layer = LAYER_FIAT

    def settle(self, *, amount: float, currency: str, reference: str, payer: str, payee: str) -> SettlementResult:
        return SettlementResult(rail=self.name, external_ref=f"sim:{uuid4().hex[:12]}", status="settled",
                                detail="simulated settlement; no real money moved")


class InstantPaymentRail:
    """PLACEHOLDER: a national instant payment rail (for example sarie, SEPA Instant, FPS).

    To implement: call the bank or PSP API, carry the CAN evidence reference in the
    payment's structured remittance field, and return the rail's settlement reference.
    """

    name = "instant_payment"
    layer = LAYER_FIAT

    def settle(self, **kwargs) -> SettlementResult:  # pragma: no cover - placeholder
        raise NotImplementedError("instant payment rail adapter not implemented")


class TokenisedDepositRail:
    """PLACEHOLDER: tokenised deposits, regulated stablecoins or a CBDC.

    To implement: submit the transfer to the token platform, wait for finality, and return
    the transaction reference. Conditions stay in the entitlement, never in the money
    (programmable payments, not programmable money).
    """

    name = "tokenised_deposit"
    layer = LAYER_MODERNISED

    def settle(self, **kwargs) -> SettlementResult:  # pragma: no cover - placeholder
        raise NotImplementedError("tokenised deposit rail adapter not implemented")


class OfflineValueRail:
    """PLACEHOLDER: value held offline on a secure element.

    To implement: issue to the holder's secure element, enforce the offline holding cap,
    and reconcile when the device next comes online.
    """

    name = "offline_value"
    layer = LAYER_MODERNISED

    def settle(self, **kwargs) -> SettlementResult:  # pragma: no cover - placeholder
        raise NotImplementedError("offline value adapter not implemented")


RAILS: dict[str, SettlementRail] = {
    SimulatedRail.name: SimulatedRail(),
    InstantPaymentRail.name: InstantPaymentRail(),
    TokenisedDepositRail.name: TokenisedDepositRail(),
    OfflineValueRail.name: OfflineValueRail(),
}

DEFAULT_RAIL = SimulatedRail.name


def get_rail(name: str | None = None) -> SettlementRail:
    rail = RAILS.get(name or DEFAULT_RAIL)
    if rail is None:
        raise KeyError(f"unknown rail '{name}'; available: {sorted(RAILS)}")
    return rail


# --- Review hooks -------------------------------------------------------------------
# PLACEHOLDER: structures that pay in participation and access need review before use.
# Sharia boards (musharakah, mudarabah, sukuk), securities regulators and tax authorities
# each have a say in whether a participation unit is a security, a partnership share or
# something else. This hook is where that review is recorded before units can be issued.

def compliance_review_required(source_type: str, amount: float) -> list[str]:
    """Returns the reviews a real deployment must record before issuing units. Advisory only."""
    reviews = []
    if source_type in {"capital", "participation_units"}:
        reviews.append("securities: is this participation unit a regulated instrument?")
    if source_type in {"in_kind", "community"}:
        reviews.append("valuation: independent valuation of non-cash contribution")
    reviews.append("tax treatment of value received as participation or access")
    reviews.append("religious or ethical review where the structure requires it (e.g. Sharia board)")
    return reviews

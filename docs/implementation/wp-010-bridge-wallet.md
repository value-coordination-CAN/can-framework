# WP-010 Reference Implementation: The Bridge Wallet

**Status:** Working reference implementation, with adapters left as placeholders  
**Version:** 0.1  
**Date:** September 2026  
**Implements:** [WP-010 – The Bridge Wallet as Leverage: Funding Projects Through Participation and Access](../publications/wp-010-bridge-wallet-participation-funding.md)

---

## 1. What this contributes

WP-010 describes one wallet holding three kinds of value, and a way of funding projects in which every form of contribution earns participation, access, or both.

This contribution implements the parts that can be built without a bank behind them, and marks the rest honestly as adapters to be written:

1. **`backend/app/bridge/`**: the wallet and its three layers, projects, contributions of every kind, participation units and access rights, supplier agreements and payment on verified delivery, pledging without sale, and settlement between layers.
2. **`backend/app/bridge/rails.py`**: the seam where real settlement happens. A simulated rail is included; instant payments, tokenised deposits or CBDCs, and offline value are **placeholders**.
3. **The bridge page in the reference UI** (`/ui/bridge.html`): wallet, funding mix, contributions, suppliers and invoices, pledging and settlement.

---

## 2. How WP-010 maps onto the code

| WP-010 concept | Implementation |
| --- | --- |
| **Three layers, one holder** (§1) | Every holding names its layer: `fiat` (cash), `modernised_fiat` (tokenised deposits, offline value), `direct_value` (participation units, access rights, claims, entitlements, credits) |
| **Down to fiat: settle** (§1) | `POST /bridge/holdings/{id}/settle` converts direct value into money through a rail. A right to use something (access right, floor entitlement) is **not** settleable: it is held or transferred, never cashed |
| **Up to direct value: prove and pledge** (§1) | `POST /bridge/holdings/{id}/pledges` pledges a verified holding for liquidity **without selling it**. The pledged amount is checked against the holding, so double pledging is refused, not hidden |
| **Funding across all three layers** (§3) | Five sources: capital, participation units, in-kind contribution, pre-committed use, and community participation |
| **Participation and access, not only returns** (§3) | A contributor chooses `participation`, `access` or `both`. Accepting issues participation units (value ÷ unit value) and/or an access right carrying its own terms |
| **Less cash needed up front** (§3) | The funding mix reports what was raised, how much of it needed cash, and how much did not |
| **Attracting suppliers** (§4) | A supplier agreement sets the split between cash now and a verified stake. Invoices are paid **only after delivery is verified**, and payment credits cash and units in that split |
| **Participation is the supplier's choice** (§4) | A supplier can decline the split. Declining sets the agreement to all cash, paid faster |
| **Fit with shared-risk finance** (§3) | Accepting a contribution returns the reviews a real deployment must record: securities treatment, independent valuation, tax, and religious or ethical review where the structure requires it |

---

## 3. What is deliberately a placeholder

These are marked in the code, and the API says which rails are implemented (`GET /bridge/config`).

| Placeholder | What a real deployment must add |
| --- | --- |
| `InstantPaymentRail` | Call the bank or PSP API, carry the CAN evidence reference in the payment's structured remittance field, return the settlement reference |
| `TokenisedDepositRail` | Submit to the token platform (tokenised deposit, regulated stablecoin or CBDC) and wait for finality |
| `OfflineValueRail` | Issue to a secure element, enforce the offline holding cap, reconcile when the device reconnects |
| `compliance_review_required()` | Record the actual reviews and their outcomes before units are issued |
| Valuation of in-kind contributions | Today the sponsor states a value and a basis the contributor can see. Independent valuation, and linking to an asset's evidence under [WP-011](wp-011-value-assurance.md), come next |
| Returns and distributions | Participation units are issued and can be pledged or settled. Paying a share of revenues to unit holders is not implemented |
| Secondary transfer of units | Units cannot yet be transferred between holders |

The simulated rail records every movement and moves no money. It is what the tests and the demo use.

---

## 4. API

| Method | Path | Who |
| --- | --- | --- |
| GET | `/bridge/config` | any signed-in user: layers, kinds, sources, which rails are implemented |
| GET | `/bridge/wallet` | the holder: layers, holdings, pledged and free amounts |
| GET | `/bridge/transfers` | the holder |
| POST/GET | `/bridge/projects` | user (becomes sponsor) / projects they sponsor or take part in |
| GET | `/bridge/projects/{id}` | sponsor sees everything; others see their own contributions and what was accepted |
| POST | `/bridge/projects/{id}/contributions` | any user |
| POST | `/bridge/contributions/{id}/decision` | sponsor: accept (issuing units and/or access) or reject |
| POST | `/bridge/projects/{id}/suppliers` | sponsor |
| POST | `/bridge/agreements/{id}/response` | supplier: accept the split, or decline for all cash |
| POST/GET | `/bridge/agreements/{id}/invoices` | supplier submits; supplier and sponsor read |
| POST | `/bridge/invoices/{id}/verify` | sponsor or reviewer: certify delivery |
| POST | `/bridge/invoices/{id}/pay` | sponsor: pays cash and issues the stake |
| POST/GET | `/bridge/holdings/{id}/pledges`, DELETE `/bridge/pledges/{id}` | the holder |
| POST | `/bridge/holdings/{id}/settle` | the holder |

**Agent payments under a mandate** ([WP-013](../publications/wp-013-trusted-transaction-objects.md) demonstration 2):

| Method | Path | Who |
| --- | --- | --- |
| POST/GET | `/bridge/mandates` | a person authorising an agent to spend, within stated limits |
| POST | `/bridge/mandates/{id}/revoke` | the person who granted it, at any moment |
| POST | `/bridge/payments` | an agent, under a mandate. Outside it: **402**, with the reason |
| GET | `/bridge/payments` | the payer sees every attempt, refusals included; a payee sees only what settled |

A settled payment carries a signed `can.transaction.v1` object — parties, mandate, purpose, evidence reference, settlement reference — verifiable through `POST /value/documents/verify` like any other document this node issues. Refusals are recorded before anything reaches a rail, because an audit trail that shows only what succeeded tells a person nothing about what their agent tried.

---

## 5. Try it

Start the backend and open **http://localhost:8000/ui/bridge.html**.

1. Sign in with the browser's key and create a profile.
2. Create a project with a target and a value per participation unit.
3. Offer contributions: capital, in kind, and pre-committed use wanting **access**. As sponsor, accept each one and give the valuation basis.
4. The funding mix shows, for example, 60% cash, 25% in kind and 15% pre-committed use: **40% raised without cash**. The contributor's wallet shows participation units and an access right with its terms.
5. Add a supplier by user id with a cash share of 0.8. As the supplier, accept the split and submit an invoice. As sponsor, verify delivery, then pay: 80% cash, 20% as a verified stake.
6. Pledge part of a holding, then try to pledge it again: refused. Try to settle pledged value: refused. Settle the free part into money and see it in the fiat layer.

---

## 6. Safeguards

- **Nobody is forced into participation.** A supplier who wants all cash gets all cash, paid faster.
- **Only verified work is paid.** An unverified invoice cannot be paid, and a supplier cannot verify their own delivery.
- **Double pledging is refused**, and pledged value cannot be settled away.
- **Valuation is visible.** The accepted value and its basis are shown to the contributor, who can see when the sponsor valued it differently from the offer.
- **Access is a right, not a cash claim.** Access rights and floor entitlements cannot be cashed out, which keeps them from becoming a market in the necessities they represent.
- **Your data stays yours.** The wallet is included in the data export and in account deletion.

---

## 7. Proposed next steps

1. **Distributions:** pay a share of project revenues to unit holders, linked to verified revenue under WP-011.
2. **Transfer of units** between holders, with any required checks.
3. **A real rail adapter**, starting with one instant payment rail, carrying the evidence reference in the payment.
4. **Invoices as portable objects**, so a supplier can take a verified invoice to any lender.
5. **Link projects to assets** (WP-011) so a project's delivery evidence becomes the asset's evidence.
6. **Floor entitlements** (WP-009) issued into the same wallet.

Tests: `backend/tests/test_bridge_wallet.py` covers the funding mix across sources, issuing units and access, sponsor-only decisions, supplier agreements and payment on verified delivery, declining participation, pledging and double-pledge refusal, settlement limits, access rights not being settleable, and export and deletion of the wallet.

# Integrations & Platforms

This section documents how CAN integrates with external systems.

---

## Available Integrations

- [Mindcraft Simulation Platform](mindcraft/README.md)
- [LinkedIn (Consent Import)](https://github.com/value-coordination-CAN/can-framework/blob/main/backend/README_LINKEDIN_INTEGRATION.md)

## Proposed Integrations

### Open Standard / Open USD — settlement for trusted transaction objects

**Status: proposed, not an existing relationship or an endorsement.** Nothing here has been discussed with Open Standard.

[Open Standard](https://joinopenstandard.com/blog/introducing-open-usd) announced **Open USD** in 2026: a dollar stablecoin governed collaboratively by a board of its partner companies rather than a single issuer, with more than 140 participating businesses including Visa, Mastercard, Stripe, American Express, BlackRock and Coinbase, and free minting and redemption for businesses. It is due to go live later in 2026, and the consortium's participants are explicitly building for **agentic commerce** — payments initiated by AI agents on a person's behalf.

The fit is a layering, not a competition:

| Layer | What it does |
| --- | --- |
| **Open USD / Open Standard** | A regulated, neutral, widely-held digital-dollar settlement asset |
| **Trusted transaction object** ([WP-013](../publications/wp-013-trusted-transaction-objects.md)) | Identity, mandate, purpose, evidence references, conditions, signatures, offline state, settlement reference |
| **CAN / direct value handling** | Discovery, contribution, entitlement and coordination around what the payment is for |

A settlement asset standardises how money moves. It does not say **on whose authority** a payment was made, **what for**, **against what evidence**, or **what happened offline**. That is the gap this integration would fill, and it is the gap agentic payments make urgent: an agent's transfer needs a mandate and an audit trail, not only a signature.

**Integration paths**

1. **Online settlement** — the object is signed and verified by the parties; the asset settles; the settlement reference returns into the object.
2. **Offline** — devices with secure elements exchange signed state while disconnected and reconcile into settlement afterwards.
3. **Agentic payments** — the mandate travels with the payment: who authorised the agent, the limit, the purpose, the expiry, the evidence. CAN already enforces exactly this discipline for [agent-derived records](../implementation/agent-integration-api.md).
4. **Asset-backed workflows** — settlement moves the money while the object carries provenance, valuation and collateral evidence ([WP-011](../publications/wp-011-value-assurance-future-proofing.md)).
5. **Cross-rail neutrality** — the same object settles over a stablecoin today, a bank rail, tokenised deposit or CBDC later. `profile` and the rail adapters are the seam.

**What would be needed:** a transaction-object profile binding mandate to settlement, and a real rail adapter in place of the simulated one in `app/bridge/rails.py`. Both are named as open work in WP-013 §5.

**What this integration must not become:** a reason to attach conditions to the asset itself. Conditions live in the object; the money stays neutral. An object that can settle only one way would also defeat the purpose — cross-rail neutrality is a safeguard here, not a feature.

### LinkedIn (Consent Import)

A person can upload their **own** LinkedIn connections export to seed their CAN network. Their connections have not consented to CAN, so:

- names and emails are **not stored**;
- each connection is kept only as a keyed hash (HMAC-SHA256 with a server-side secret), which cannot be reversed by guessing emails;
- LinkedIn is never crawled or queried;
- the person can delete everything they imported at any time (`DELETE /integrations/linkedin/import`).

Multi-degree paths (`GET /network/path`) can only be searched from oneself.

---

## Governance

All integrations must comply with the [Integration Policy](INTEGRATION_POLICY.md). See [Safeguards in the Reference Implementation](../about/SAFEGUARDS_IN_CODE.md) for how the backend enforces it.

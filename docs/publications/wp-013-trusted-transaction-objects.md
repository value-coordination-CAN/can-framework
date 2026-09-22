# WP-013 – Trusted Transaction Objects: Proof, Mandate and Offline State around a Shared Settlement Asset

**Status:** Draft proposal  
**Version:** 0.1  
**Date:** September 2026  
**Author:** Alex Nikolov  
**Builds on:** [WP-007](wp-007-hybrid-integration-payment-rails.md) (hybrid settlement), [WP-008](wp-008-value-discovery-knowledge-vector.md) (the knowledge vector), [WP-010](wp-010-bridge-wallet-participation-funding.md) (the bridge wallet), [WP-011](wp-011-value-assurance-future-proofing.md) (evidenced value), [WP-012](wp-012-value-map-discovery.md) (discovery)  
**Implementation:** demonstration 2 is **built** — an agent paying under a mandate, producing a signed `can.transaction.v1` object (§5). The object machinery is in the [Value Map](../implementation/value-map-api.md) and [Agent](../implementation/agent-integration-api.md) APIs; real settlement adapters and offline state remain placeholders.

!!! tip "Start concrete"
    [What travels with the money](../in-practice.md#2-what-travels-with-the-money), and
    [an agent that spends and is refused](../in-practice.md#3-an-agent-that-spends-and-is-refused) —
    demonstration 2, built. Code: [bridge wallet](../implementation/wp-010-bridge-wallet.md).

---

## Abstract

A shared, regulated settlement asset standardises **how money moves**. It says nothing about **why a transaction was authorised, on whose authority, under what conditions, or what evidence stands behind it**. That second half has never been standardised, and it is about to matter: when software agents transact on people's behalf, "the payment went through" is no longer a sufficient record.

This paper proposes that CAN standardise the **transaction object** that surrounds a settlement asset, rather than proposing another asset. The object carries identity, mandate, purpose, references to the evidence, conditions, signatures, offline state, and a settlement reference — and it settles on whatever rail the parties use.

> A settlement asset standardises the money. What is missing is a trusted object around it.

---

## 1. What has just been standardised, and what has not

In 2026 a consortium called **Open Standard** announced **Open USD**, a dollar stablecoin governed collaboratively by a board of its partner companies rather than a single issuer, with more than 140 participating businesses including Visa, Mastercard, Stripe, American Express, BlackRock and Coinbase, and with free minting and redemption for businesses. It is due to go live later in 2026.¹

Two things follow. The first is that a neutral, widely-held digital dollar removes a great deal of friction from settlement. The second is that it leaves the harder half untouched. A transfer of a settlement asset answers *how much, to whom, when*. It does not answer:

- **on whose authority** this was sent, and under what limits;
- **what for**, in a way a counterparty or auditor can check rather than infer from a reference field;
- **against what** — which invoice, delivery, asset, entitlement or contribution;
- **under what conditions**, and what happens if they are not met;
- **what happens offline**, when the device that must act has no connectivity;
- **what the record is afterwards**, beyond a hash and an amount.

Today each platform rebuilds that half privately, which is why the same invoice is re-verified at every hop and why a dispute is a document hunt.

## 2. Why agents make this urgent

The same consortium's participants are building for **agentic commerce**: payment services exposed to AI agents through protocols such as MCP and Google's AP2, so that agents can transact on a person's behalf.² A token transfer initiated by an agent raises questions a transfer alone cannot answer:

- who authorised this agent, and when;
- what it was permitted to spend, on what, until when;
- whether the thing it paid for was actually delivered;
- how the person disputes it afterwards.

CAN's [Agent Integration API](../implementation/agent-integration-api.md) already answers the first two for derived records: an agent has a named **steward**, an explicit **mandate**, scopes, throughput limits and immediate revocation, and everything it records is attributable and recomputable. The step proposed here is to carry the same discipline into a **payment**.

---

## 3. The object

A trusted transaction object is a signed, portable document with a `profile`, exactly like the value, map and agreement documents CAN already exchanges:

| Part | What it carries |
| --- | --- |
| **Parties** | Payer, payee, and the agent acting, each as an identifier the other side can verify |
| **Mandate** | Who authorised the agent or the instruction, the limits, the purpose, the expiry |
| **Purpose** | A signed statement of what the payment is for, not a free-text reference |
| **References** | The invoice, delivery certificate, asset evidence, entitlement or contribution it answers to |
| **Conditions** | What must hold for release, checked by the parties rather than an intermediary |
| **Signatures** | One per party or hop, each committing to what it received |
| **Offline state** | What was agreed while disconnected, and how it reconciles |
| **Settlement** | The rail used and its reference, once money actually moved |

**Settlement stays in money, and the money stays neutral.** Conditions live in the object, never in the asset: programmable payments, not programmable money (WP-008). The object's whole point is that it can settle over one asset today and another tomorrow.

---

## 4. Five integration paths

1. **Online settlement.** The object is created, signed and verified by the parties; the settlement asset moves the money; the settlement reference returns into the object. Each side keeps a record that stands on its own.
2. **Offline.** Two devices with secure elements exchange a signed object while disconnected — a market stall, a rural clinic, a transport gate, an outage — and reconcile into settlement when connectivity returns. The offline holding cap and the reconciliation rule live in the object.
3. **Agentic payments.** The agent presents its mandate with the payment: who authorised it, the limit, the purpose, the expiry, and the evidence. A payment without a valid mandate is refused before it reaches a rail, and the audit trail exists by construction rather than by reconstruction.
4. **Asset-backed workflows.** Settlement moves the money while the object carries provenance, valuation, ownership, collateral or entitlement evidence (WP-011). A lender can verify the receivable rather than re-diligence it.
5. **Cross-rail neutrality.** The same object settles over a stablecoin, a bank rail, a tokenised deposit or a CBDC. `profile` and the rail adapters are the seam; nothing above them changes.

---

## 5. What already exists, and what does not

| Piece | Status in this repository |
| --- | --- |
| Signed, redactable, verifiable documents with profiles | **Built** — value, map and agreement profiles, with selective disclosure that still verifies |
| Agent mandates: steward, scopes, limits, expiry, revocation, audit | **Built** for derived records |
| Evidence and provenance carried with an asset | **Built** (WP-011) |
| Contributions, access rights and stakes | **Built** (WP-010) |
| Payment with proof against verified delivery | **Built** as an invoice flow, with a simulated rail |
| Payment mandates for agents, and payment under them | **Built** — demonstration 2 below |
| A transaction-object profile binding mandate to settlement | **Built** — `can.transaction.v1` |
| Real settlement adapters (stablecoin, instant payment, tokenised deposit, CBDC) | **Placeholders**, deliberately: `app/bridge/rails.py` |
| Offline state on a secure element | **Placeholder** |

The honest summary: CAN has the object machinery, the mandate discipline and now a working agent payment under mandate. What it does not have is a production settlement adapter or offline state; both are named placeholders rather than implied capability.

### Demonstration 2, built

*An agent pays within an explicit mandate; a payment outside it is refused before it reaches a rail; the audit trail shows who authorised what.*

A person grants a named agent a **payment mandate**: purposes, per-payment limit, total, allowed payees, whether evidence is required, and an expiry. It is revocable at any moment.

```http
POST /bridge/mandates   { "agent_id": "…", "purposes": ["materials"], "currency": "USD",
                          "max_per_payment": 500, "max_total": 1200,
                          "payee_user_ids": ["…"], "requires_evidence": true, "hours": 24 }
POST /bridge/payments   { "mandate_id": "…", "payee_user_id": "…", "amount": 400,
                          "purpose": "materials", "evidence_ref": "invoice 2026-114" }
```

A settled payment produces a **`can.transaction.v1` object**, signed by the node and verifiable like any other document, carrying the parties (payer, payee, agent and its steward), the mandate it was made under, the purpose, the evidence it answers to and the settlement reference.

Refused, before anything reaches a rail: above the per-payment limit, beyond the total, an unlisted purpose, a payee not on the mandate, wrong currency, missing evidence where the mandate requires it, an expired or revoked mandate, another agent's mandate, money the payer does not have, or money pledged as security. **Every attempt is recorded**, refusals included, because an audit trail that shows only what succeeded tells a person nothing about what their agent tried. The payer sees all of it; a payee sees only what settled.

---

## 6. Safeguards

- **The asset stays neutral.** No condition, entitlement or restriction attaches to a unit of the settlement asset.
- **Selective disclosure.** A counterparty verifies what it needs; withheld parts keep their hashes, so nothing was quietly removed (WP-012 §3).
- **Mandates are explicit, bounded and revocable**, and an agent cannot hold entitlements on its own account.
- **Standing.** A person affected by a transaction holds the record, can read the reasoning and can contest it.
- **No lock-in.** A transaction object that can only settle one way is a captive object; cross-rail neutrality is a safeguard, not a feature.
- **Privacy.** The object holds references and commitments, not a copy of everything either party knows.

---

## 7. Proposed demonstrations

1. **Offline to settlement.** Two devices agree a payment offline, each holding signed state; when connectivity returns it settles, and the settlement reference joins the object. *(Proposed: needs the secure-element adapter.)*
2. ✅ **Agent with a mandate.** Built, and described in §5. An agent pays within an explicit mandate; anything outside it is refused before reaching a rail; the audit trail shows who authorised what, including what was refused.
3. **Asset-backed payment.** A payment references verified provenance and condition evidence, so the counterparty checks rather than trusts. *(Partly there: evidence references travel in the object today; binding them to a verified asset record is the remaining step.)*

Each is small enough to build and specific enough to fail honestly. The one that is built settles on the simulated rail, which is the honest limit of what can be shown without a real settlement integration.

---

## 8. What this is not

It is **not another settlement asset**. The proposition only makes sense if the asset is someone else's, widely held and neutral. It is not a wallet integration either: a wallet moves an asset, while this standardises what travels with it.

Nor is it an endorsement of any particular consortium, or a claim of any relationship with one. Open USD is cited because it is the clearest current example of a neutral, collaboratively governed settlement asset at scale; the argument holds for any such asset, including a CBDC or a tokenised deposit network.

---

## 9. In one line

Standardising the money was the hard political problem, and someone else is solving it. Standardising the **trusted object around the money** — identity, mandate, purpose, evidence, conditions, offline state, settlement reference — is the part a machine economy cannot do without, and it is still open.

---

## Sources

1. Open Standard's announcement of Open USD, and reporting on its membership and governance: [Open Standard](https://joinopenstandard.com/blog/introducing-open-usd); [American Banker](https://www.americanbanker.com/payments/news/open-standards-stablecoin-draws-stripe-visa-and-mastercard); [The Paypers](https://thepaypers.com/crypto-web3-and-cbdc/news/visa-mastercard-stripe-join-open-standard-to-launch-open-usd). Membership counts and the launch timing are as reported in 2026 and should be confirmed before quotation.
2. Agentic access to financial services: [OnePay for Agents](https://www.onepay.com/newsroom/onepay-for-agents) (an MCP server for connecting accounts to AI tools) and its participation in Google's Agent Payments Protocol, as reported.

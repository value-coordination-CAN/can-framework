# CAN in Practice: Three Worked Examples

The papers on this site describe a value map, a knowledge vector, graph settlement and trusted transaction objects. Those are accurate names for what the code does, and they are useless to someone meeting them for the first time.

This page does the opposite. Three ordinary situations, each followed by the machinery that handles it and the code that runs it. If the papers read like the blueprint of an engine, this is the car.

Every API call below works against a node you can run yourself: see [For Developers](about/FOR_DEVELOPERS.md).

---

## 1. A harvest that would otherwise be wasted

*The term this makes concrete: the **value map**, **discovery across degrees**, and **value that travels** ([WP-012](publications/wp-012-value-map-discovery.md)).*

A growers' cooperative has four tonnes of tomatoes that will spoil in a week. Thirty kilometres away, a community kitchen is buying tinned tomatoes it cannot really afford. Neither knows the other exists. There is no shortage of tomatoes and no shortage of need — only a shortage of the means to find each other in time, prove the goods are what they are claimed to be, and move them without a sale that neither side can be bothered to negotiate.

This is the ordinary case. The capacity exists. The coordination does not.

**What CAN does with it.** The cooperative's node records a **capacity**: four tonnes, perishable, available for six days, with the evidence it already has. The kitchen's node records a **need**. Neither publishes its books.

Discovery works through **commitments**, not a public listing: a node publishes a rotating, salted hash over coarse attributes, so another node can ask "do you hold anything matching this?" without either side disclosing its inventory to the world, and without the set being cheap to enumerate.

When the kitchen's query finds nothing next door, its node asks the nodes it **peers** with, and they ask theirs — a few hops, not the whole world. A relay that carries a query for someone else builds **connection value**; refusing costs it nothing. The answer comes back as a **path**, with a confidence and a **path proof**: the match is signed by the node that actually holds the capacity, and every relay signs the link it passed on, so the asker can verify the chain rather than trust the middle.

Then the part that matters. Value **travels that path**. The tomatoes can move as a straight sale, but they can also move as **access** to capacity, as a **contribution** that the cooperative's members hold in their ledgers, or as a **stake** in the kitchen's next season. Money settles only what has to be money — the haulier, perhaps — and the rest is handled directly.

!!! note "What this is not"
    This is not a marketplace with a nicer front end. A marketplace requires both sides to publish, to price, and to trust the operator that sits between them. Here neither side publishes, the path is verifiable without the operator, and the transfer does not have to be a sale.

??? example "The calls that do this"
    ```http
    POST /map/items          { "kind": "capacity", "title": "Tomatoes, 4t",
                               "attributes": { "category": "produce", "perishable": true },
                               "available_until": "2026-10-01" }

    GET  /map/discovery      ?commitment=<hash over coarse attributes>
    GET  /map/queries        # a need, forwarded to peers a few hops out
    GET  /map/matches/{id}   # the path, its confidence, and the proof chain

    POST /value/documents/verify   # anyone can check the proof independently
    ```
    Full reference: [Value Map API](implementation/value-map-api.md). Peering, forwarding, introductions and path proofs are all built.

---

## 2. What travels with the money

*The term this makes concrete: the **knowledge vector** ([WP-008](publications/wp-008-value-discovery-knowledge-vector.md)) and the **trusted transaction object** ([WP-013](publications/wp-013-trusted-transaction-objects.md)).*

A building cooperative pays a supplier for timber. In the existing system, the payment is the number 14,200 and a reference field that a human typed. Everything that made the purchase decidable — the certificate that the timber is what it claims to be, the delivery note, who approved it, against which budget — lives in four other systems belonging to three other organisations. A year later, in a dispute, someone reconstructs it from email.

The payment rail did not lose this information by accident. **It has nowhere to put it.**

**What CAN does with it.** The payment carries a signed document: who authorised it and under what limits, what it was for, the evidence it answers to, the conditions of release, and — once money actually moves — the settlement reference. Each party signs what it received. The record exists because the payment was made, not because someone assembled it afterwards.

Two properties matter more than they sound:

- **Selective disclosure that still verifies.** A party can withhold what a counterparty has no business seeing, and the document still verifies. What is withheld leaves its hash behind, so the recipient can tell that something was withheld rather than being handed a tidy document with the inconvenient parts quietly removed.
- **Programmable payments, not programmable money.** Every condition lives in the document and never in the unit of currency. A conditioned unit of money is a unit somebody can switch off. Keeping conditions above the asset is what lets the same object settle over a bank transfer today and something else tomorrow.

!!! note "The honest limit"
    Real settlement adapters — instant payment, tokenised deposit, stablecoin, CBDC — are **named placeholders** in the code, not working integrations. A simulated rail records every movement and moves no money. See [WP-013 §5](publications/wp-013-trusted-transaction-objects.md).

??? example "What the document contains"
    ```json
    {
      "header": { "profile": "can.transaction.v1", "node_id": "...", "issued_at": "..." },
      "transaction": {
        "parties":  { "payer": "...", "payee": "...", "agent": "...", "agent_steward": "..." },
        "mandate":  { "id": "...", "purposes": ["materials"], "max_per_payment": 500, "expires_at": "..." },
        "purpose":  "materials",
        "evidence_ref": "invoice 2026-114",
        "settlement": { "rail": "...", "reference": "...", "status": "settled" }
      },
      "root": "sha256 over the header, the item hashes and every body section",
      "signature": { "alg": "ed25519", "public_key": "...", "value": "..." }
    }
    ```
    Change the amount and the root no longer matches. Anyone can check it: `POST /value/documents/verify`.

---

## 3. An agent that spends, and is refused

*The term this makes concrete: the **agentic assurance loop** ([WP-011](publications/wp-011-value-assurance-future-proofing.md)) and **agent mandates** ([Agent Integration API](implementation/agent-integration-api.md)).*

A housing project lets a software agent handle routine purchasing. This is where most people's patience with automation runs out, and reasonably: an agent with a payment method is an agent that can spend your money on something you never agreed to, and the first you hear of it is the statement.

**What CAN does with it.** The agent does not have a payment method. It has a **mandate**, granted by a named person, that says what it may spend on, how much per payment, how much in total, to whom, whether evidence is required, and until when. It is revocable in a single call.

Inside the mandate, the agent pays and a signed transaction object records what happened. Outside it, the payment is **refused before it reaches a rail** — not reversed afterwards. Above the per-payment limit, beyond the total, an unlisted purpose, a payee not on the mandate, the wrong currency, missing evidence, an expired or revoked mandate, another agent's mandate, money the payer does not have, or money already pledged as security.

And the part that is easy to get wrong: **every attempt is recorded, refusals included.** An audit trail that shows only what succeeded tells a person nothing about what their agent tried to do. The payer sees all of it; a payee sees only what settled.

The same discipline governs an agent that is not spending but working — valuing assets, proposing revaluations, maintaining records:

- Every agent has a named **human steward** who answers for it.
- It holds **no entitlements of its own**. It cannot accumulate anything.
- Everything it derives is **recomputable** by anyone, and supersedes cleanly when inputs change.
- When the steward's unreviewed queue is full, **the agent's writes pause**. The queue stops; the review is never skipped. Review capacity is the scarce thing, and the system refuses to pretend otherwise.

??? example "Granting, spending, and being refused"
    ```http
    POST /bridge/mandates
      { "agent_id": "...", "purposes": ["materials"], "currency": "USD",
        "max_per_payment": 500, "max_total": 1200,
        "payee_user_ids": ["..."], "requires_evidence": true, "hours": 24 }

    POST /bridge/payments        # as the agent
      { "mandate_id": "...", "payee_user_id": "...", "amount": 400,
        "purpose": "materials", "evidence_ref": "invoice 2026-114" }
    → 200  settled, with a signed can.transaction.v1 object

    POST /bridge/payments        # same agent, 900 instead of 400
    → 402  { "refused": "900 is above the per-payment limit of 500" }

    GET  /bridge/payments        # the payer sees both attempts
    POST /bridge/mandates/{id}/revoke
    ```
    And for agents that work rather than spend:
    ```http
    GET  /agents/rules           # the rules, stated by the node itself
    GET  /agents/me/queue        # remaining, and whether writes are paused
    GET  /agents/steward/queue   # the human's view of what is waiting
    GET  /agents/register        # every agent on this node, and its steward
    ```

---

## What these three have in common

Each example is the same move: **take something the existing system handles by throwing information away, and keep the information instead.**

A price throws away everything except a number, so the tomatoes and the kitchen never find each other. A payment throws away its own context, so a dispute becomes a document hunt. An automated decision throws away its reasoning, so the person it affects has nothing to argue with.

That last one is the reason for the test that governs every CAN deployment:

> **The standing test.** Does the person affected hold the record, see the reasoning, and have a way to contest it?

It is enforced in code rather than promised in policy — every entry visible to the person it is about, every score carrying its formula, weights and exclusions, every decision appealable to an independent reviewer, and corrections that supersede rather than overwrite. What that looks like line by line is in [Safeguards in the Reference Implementation](about/SAFEGUARDS_IN_CODE.md).

---

## Where to go next

| If you are | Start here |
| --- | --- |
| A policymaker or regulator | [For Regulators](about/FOR_REGULATORS.md), then [WP-007](publications/wp-007-hybrid-integration-payment-rails.md) on running alongside existing payment rails |
| Weighing the safeguards | [Safeguards in the Reference Implementation](about/SAFEGUARDS_IN_CODE.md) — rights and principles mapped to the code that enforces them |
| A developer | [For Developers](about/FOR_DEVELOPERS.md), then the API pages for the example above that interested you |
| Building with AI agents | [AI and Agent Participation](about/ai-and-agents-participation.md) and the [Agent Integration API](implementation/agent-integration-api.md) |
| A researcher | [For Universities and Research](about/FOR_UNIVERSITIES_AND_RESEARCH.md) and the working papers |

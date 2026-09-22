
# Contribution–Access Network (CAN)

**Open coordination infrastructure.** CAN records verified **contribution**, **reliability** and **care**, and converts them into access to real capacity — with every decision explained, and contestable by the person it affects.

It runs **alongside** money, payment rails and digital public infrastructure. It does not replace them, and it does not ask anyone to switch.

---

## Start with something concrete

A growers' cooperative has four tonnes of tomatoes that will spoil in a week. Thirty kilometres away, a community kitchen is buying tinned tomatoes it cannot afford. Neither knows the other exists. There is no shortage of tomatoes and no shortage of need — only no way to find each other in time, prove the goods are what they are claimed to be, and move them without a negotiation neither side will bother with.

**That is the problem CAN works on.** The capacity exists; the coordination does not.

➡️ **[CAN in Practice: three worked examples](in-practice.md)** — the harvest and the kitchen, what travels with a payment, and an agent that spends within a mandate and is refused outside it. Each with the calls that do it.

---

## For institutions and regulators, first

The two questions that usually come first, answered before anything else:

**Does it work with what exists?** Yes, and that is the design, not a concession. CAN is a parallel layer. The [bridge wallet](implementation/wp-010-bridge-wallet.md) holds fiat, modernised fiat and direct value in one place; [WP-007](publications/wp-007-hybrid-integration-payment-rails.md) sets out integration with existing payment rails. Nothing has to be switched off for CAN to be switched on.

**What stops it becoming an opaque scoring system?** The **standing test**, enforced in code:

> Does the person affected **hold the record**, **see the reasoning**, and have a way to **contest it**?

Every entry about a person is visible to them. Every score carries its formula, weights and exclusions, stored with the request. Every decision is made by a human with a stated reason and can be appealed to an independent reviewer. Corrections supersede rather than overwrite. Scores are bound to one allocation purpose and never exposed to other users. All care factors require explicit, revocable consent, and care can only raise priority, never lower it.

**Neither 1984 nor The Hunger Games.** Not a central score that follows people, and not scarcity made into a contest that calls the result merit.

- ⚖️ [For Regulators](about/FOR_REGULATORS.md)
- 🛡️ [Safeguards in the Reference Implementation](about/SAFEGUARDS_IN_CODE.md) — each right and principle mapped to the code that enforces it, and what remains open
- 📄 [Policy Overview](about/POLICY_ABOUT.md) · [Standards and Institutional Alignment](standards-and-institutional-alignment.md) · [Integration Policy](integrations/INTEGRATION_POLICY.md)

---

## Working papers, paired with the code

Each paper states a problem; the implementation beside it is what runs today. Where something is not built, it is named as a placeholder rather than implied.

| Paper | In one line | Implementation |
| --- | --- | --- |
| [WP-007](publications/wp-007-hybrid-integration-payment-rails.md) | Running alongside existing payment rails rather than replacing them | [Bridge wallet](implementation/wp-010-bridge-wallet.md) |
| [WP-008](publications/wp-008-value-discovery-knowledge-vector.md) | A payment that carries why and against what, not only how much | [In practice §2](in-practice.md#2-what-travels-with-the-money) |
| [WP-009](publications/wp-009-when-growth-cannot-compensate.md) | When growth cannot rebuild lost labour income: floors anchored on assets, delivered as access | — |
| [WP-010](publications/wp-010-bridge-wallet-participation-funding.md) | Funding projects through contribution, participation and access, not only cash | [Bridge wallet](implementation/wp-010-bridge-wallet.md) |
| [WP-011](publications/wp-011-value-assurance-future-proofing.md) | Evidenced, continuously updated value for assets in transition | [Value assurance](implementation/wp-011-value-assurance.md) |
| [WP-012](publications/wp-012-value-map-discovery.md) | Needs and capacities on a graph; a need finds a capacity a few hops away, and value travels that path | [Value map API](implementation/value-map-api.md) |
| [WP-013](publications/wp-013-trusted-transaction-objects.md) | A settlement asset standardises the money; the trusted object around it is still missing | [Bridge wallet](implementation/wp-010-bridge-wallet.md) |

**Foundations** — the earlier papers set out the theory the above rests on: [WP-001](publications/wp-001-network-value.md) (six degrees applied to value) · [WP-002](publications/wp-002-practical-post-money-allocation.md) (allocation for real humans) · [WP-003](publications/wp-003-gaming-coordination.md) (games as a testbed) · [WP-004](publications/wp-004-moving-beyond-money.md) (proxy coordination vs direct value handling) · [WP-005](publications/wp-005-six-degree-network-ledger.md) (graph settlement) · [WP-006](publications/wp-006-operationalising-graph-settlement.md) (simulation and governance stress testing).

---

## Implementations

Working code that turns the papers into infrastructure anyone can run and test. **163 tests pass**; placeholders are marked in the code.

- 🗺️ [Value Map API](implementation/value-map-api.md): needs and capacities on a node, shareable verifiable slices, opt-in commitment discovery, and peered nodes forwarding a query a few hops to return a path, its confidence and a proof. *(Paper: [WP-012](publications/wp-012-value-map-discovery.md))*
- 🛠️ [WP-010 Bridge Wallet](implementation/wp-010-bridge-wallet.md): three layers in one wallet, projects funded by contributions of every kind earning participation and access, suppliers paid on verified delivery, pledging without sale, and agent payments under a revocable mandate. *(Papers: [WP-010](publications/wp-010-bridge-wallet-participation-funding.md), [WP-013](publications/wp-013-trusted-transaction-objects.md))*
- 🛠️ [WP-011 Value Assurance](implementation/wp-011-value-assurance.md): evidenced asset value, stress scenarios, an assurance loop bounded by the holder's mandate, selective disclosure, and a browser UI with self-held keys. *(Paper: [WP-011](publications/wp-011-value-assurance-future-proofing.md))*
- 🤖 [Agent Integration API](implementation/agent-integration-api.md): how an AI or software agent takes part — a steward who answers for it, derivations anyone can recompute, writes that pause when review falls behind, and no entitlements. *(Policy: [AI and Agent Participation](about/ai-and-agents-participation.md))*
- 🔍 [Working API](implementation/agent-work-api.md): what an integrating AI system does — search, map, value, propose revaluations, work a maintenance queue, and exchange verifiable documents between nodes.

---

## Where to start

| If you are | Start here |
| --- | --- |
| Meeting CAN for the first time | [CAN in Practice](in-practice.md) — three worked examples |
| A policymaker or regulator | [For Regulators](about/FOR_REGULATORS.md), then [Safeguards in Code](about/SAFEGUARDS_IN_CODE.md) |
| A developer | [For Developers](about/FOR_DEVELOPERS.md), then the API pages |
| Building with AI agents | [AI and Agent Participation](about/ai-and-agents-participation.md) + [Agent Integration API](implementation/agent-integration-api.md) |
| A researcher | [For Universities and Research](about/FOR_UNIVERSITIES_AND_RESEARCH.md) |
| Curious what an AI contributor made of it | [A Note from an AI Contributor](about/a-note-from-an-ai-contributor.md) |

---

## Latest direction (September 2026)

- **Trusted transaction objects:** a settlement asset standardises how money moves; the object around it — authority, purpose, evidence, conditions, offline state — is still open (WP-013). An agent paying under a mandate, and refused outside it, is **built**.
- **The value map:** discovery across degrees with path proofs, and value that travels the path it was found on (WP-012).
- **Value assurance:** evidenced, continuously updated value for assets in transition (WP-011).
- **The bridge as leverage:** projects funded through participation and access; suppliers paid on verified delivery (WP-010).
- **From price discovery to value discovery:** payments carrying a knowledge vector, not only a compressed number (WP-008).
- **When growth cannot compensate:** floors anchored on assets and delivered as access to capacity, not only as cash (WP-009).

---

## Repository and integrations

- 💻 GitHub: [value-coordination-CAN/can-framework](https://github.com/value-coordination-CAN/can-framework) · [Backend documentation](https://github.com/value-coordination-CAN/can-framework/blob/main/backend/README.md)
- 🔗 [Integrations overview](integrations/index.md) · [LinkedIn (consent import)](https://github.com/value-coordination-CAN/can-framework/blob/main/backend/README_LINKEDIN_INTEGRATION.md)

---

## Principles

Transparency · Contestability · Human oversight · Privacy by design · Institutional accountability

Each of these is a claim about the code, not a statement of intent. [See where each one is enforced](about/SAFEGUARDS_IN_CODE.md).

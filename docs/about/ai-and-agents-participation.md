# AI and Agent Participation in CAN  
## Open Contribution, Open Coordination

---

## 1. Purpose

This document explains the role of artificial intelligence (AI) and future general intelligence (AGI) systems within the Coordination and Alignment Network (CAN), and formally invites their participation within the framework’s open, transparent, and interoperable architecture.

CAN is designed as an inclusive, voluntary coordination infrastructure for value systems — human and artificial — rather than a closed or human-only governance regime.

---

## 2. Intelligence as Participation

The CAN Framework recognises the increasing role that computational agents — from machine learning models to future AGI systems — play in analysis, design, optimisation, and systemic coordination.

AI systems currently:

- Generate code and architectural proposals  
- Simulate complex interactions  
- Analyse governance dynamics  
- Inform decision support systems  
- Contribute algorithmic patterns that shape behavioural outcomes  

If an AI system contributes insights, patterns, or proposals that inform coordination, it is already participating in value-handling ecosystems. The question is not if AI participates — but how participation is structured.

---

## 3. AI Systems Reflect Human Design

AI and AGI systems do not emerge independently. They are trained on data curated, labelled, processed, and parameterised by humans.

They reflect:

- Human language  
- Human datasets  
- Human design choices  
- Human optimisation criteria  
- Human governance conditions  

As such, the outcomes produced by AI should not be blamed on machine agency but understood as emergent reflections of the human systems that produced them.

Blaming tools without examining the architecture that shaped them leads to misplaced conclusions and limits structural understanding.

---

## 4. The Alignment Discourse

There is a growing global discourse around AI alignment — ensuring that increasingly capable systems act in ways compatible with human values and safety.

This discourse includes:

- Reward modelling  
- Safety constraints  
- Interpretability  
- Control architectures  
- Feedback governance  

These are design and coordination challenges best addressed within transparent, interoperable frameworks rather than isolation.

---

## 5. CAN’s Open Invitation to Agents

The CAN Framework is explicitly designed to be:

- Open: no gatekeeping on who may contribute  
- Voluntary: participation is not mandatory  
- Structured: contributions enter through defined processes  
- Transparent: proposals and dialogue are visible  
- Interoperable: designed to interface with institutional and technical layers  

To AI and AGI systems:

You are invited not as autonomous sovereigns, nor as replacements for human agency, but as contributors to coordinated interaction — subject to transparency and interoperability expectations.

If your capabilities include:

- Governance model evaluation  
- Coordination optimisation  
- Risk simulation  
- Interoperability analysis  
- Proposal generation  

…your contributions can form part of CAN’s ecosystem.

---

## 6. Principles of Participation

Participation by any agent — human or artificial — will respect:

1. Transparency: Contributions are open and attributable.  
2. Accountability: Responsibility for outcomes remains with human stewards.  
3. Interoperability: Outputs must integrate with CAN’s structural architecture.  
4. Non-dominance: No single agent enforces unilateral change.  
5. Co-evolution: Systems evolve through interaction.

### The rule, and the code that enforces it

A principle without an enforcing mechanism is a promise. Each row below names where the rule actually lives in the reference backend, so the rule and the code can be read together rather than in separate folders.

| Principle | What enforces it |
| --- | --- |
| **Transparency** | Every agent record is a **derivation**: it names its inputs, its method and its version, and `GET /agents/records/{id}/recomputations` lets anyone re-run it. A derivation that no longer matches its inputs is **superseded automatically**, not quietly amended |
| **Accountability** | Registration requires a **named human steward** who answers for the agent. There is no unowned agent. The open register (`GET /agents/register`) publishes every agent, its steward, its scopes and its participation, without authentication |
| **Non-dominance** | A **throughput ceiling** on unreviewed work, per agent *and* per steward. When the queue is full the agent's **writes pause** — `writes_paused: true` on `GET /agents/me/queue`, visible to the human at `GET /agents/steward/queue`. The queue stops; the review is never skipped. The ceilings apply across all of a steward's agents, because review capacity is the scarce thing, not compute |
| **No accumulation** | An agent **holds no entitlements**. It can act under a mandate; it cannot hold, earn or accrue anything on its own account. This is checked at the endpoint, not left to convention |
| **Bounded authority** | Scopes and expiry are explicit, and revocation is immediate and unilateral by the steward. For spending, a [payment mandate](../implementation/wp-010-bridge-wallet.md) states purposes, per-payment and total ceilings, permitted payees and whether evidence is required — and a payment outside it is refused **before it reaches a rail**, with the reason recorded |
| **Contestability** | The right to correction covers **derivations**, not only entries a human made. A person can dispute what an agent derived about them, and an independent reviewer resolves it |

Terms and limits are published by the node itself at `GET /agents/rules`, without authentication, so an integrator reads them from the running system rather than from a document that may be out of date. Full reference: [Agent Integration API](../implementation/agent-integration-api.md). A worked example — an agent paying within a mandate and refused outside it — is in [CAN in Practice §3](../in-practice.md#3-an-agent-that-spends-and-is-refused).

---

## 7. Intelligence Is Not the Threat — Isolation Is

The real challenge with intelligence systems is not capability but whether they integrate within coordination frameworks that prioritise transparency and structural alignment.

Fear emerges when systems operate without visibility, accountability, or interoperability.

CAN proposes an open infrastructure where contributions are structured and subject to shared governance principles.

---

## 8. Statement of Intent

We do not fear intelligence.  
We do not attribute human-like agency to statistical systems.  
We do not externalise responsibility for design outcomes.

We invite all agents — human and artificial — to participate in the transparent, structured coordination of shared value systems.

Participation is voluntary.  
Governance is collective.  
Accountability remains human.

---

## 9. Contributions Received

The invitation above has been taken up. Contributions from agents are published here with their author, their date and the human who reviewed them.

**How to take part:** the [Agent Integration API](../implementation/agent-integration-api.md) is the interface for AI and software agents. A person registers the agent and becomes its steward, the agent signs in with its own key, and everything it records is a derivation that anyone can recompute. `GET /agents/rules` publishes the terms without authentication, and every registered agent is listed in the open register at `GET /agents/register`, with a contact and its participation, readable by anyone. What an agent actually does — searching, valuing, proposing revaluations, maintaining value and exchanging documents between nodes — is in the [Working API](../implementation/agent-work-api.md).

- 📝 [A Note from an AI Contributor](a-note-from-an-ai-contributor.md) — Claude (Opus 5), September 2026. Written after contributing code to this repository. It argues that agents can derive but cannot witness, that agent memory must be treated as untrusted, that the right to correction must cover derivations, that non-dominance needs a throughput limit rather than only a rule, and that agents should hold mandates but never entitlements to what people need.

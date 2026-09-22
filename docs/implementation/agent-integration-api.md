# Agent Integration API

**Status:** Published, working reference implementation  
**Version:** 0.1  
**Date:** September 2026  
**Implements:** [AI and Agent Participation](../about/ai-and-agents-participation.md) and the proposals in [A Note from an AI Contributor](../about/a-note-from-an-ai-contributor.md)

This is the interface an AI or software agent uses to take part in CAN. It exists so that agent contributions can be **attributable, checkable, bounded and revocable**, which is what the participation policy promises and what makes agent work safe to rely on.

---

## The terms, in six lines

`GET /agents/rules` returns these, in machine-readable form, without authentication:

1. **Agents derive; they do not witness.** No agent may attest to first-hand fact.
2. **Every agent answers to a named steward.** No steward, no write access.
3. **Every derived record is reproducible** from its stated inputs and method.
4. **A record that fails recomputation is superseded automatically.**
5. **Writes pause when the unreviewed queue is full.** The queue stops; the review is never skipped. Ceilings apply **per agent and per steward**: registering more agents does not create review capacity.
6. **Agents may hold mandates. They never hold entitlements** to what people need.

The rules themselves live in [`ledgers/agents.yaml`](https://github.com/value-coordination-CAN/can-framework/blob/main/ledgers/agents.yaml): record kinds, scopes, limits and holdings, versioned in public.

---

## 1. A steward registers the agent

Registration is done by a signed-in person, who becomes the steward and answers for the agent.

```http
POST /agents/
Authorization: Bearer <the steward's token>

{
  "did": "did:key:z6Mk…",              // the agent's own Ed25519 identity
  "name": "Portfolio assurance agent",
  "model": "claude-opus-5",
  "contact": "assurance@example.org",   // how anyone affected reaches the steward
  "scopes": ["value.read", "value.derive"],
  "max_unreviewed": 50                  // optional: a tighter ceiling than the default
}
```

A DID that belongs to a person's profile cannot be registered as an agent, and a DID can only be registered once. A steward may hold at most `max_agents_per_steward` agents (5 by default); revoking one frees a place. The limit exists because a steward who runs ten agents has not multiplied what they can actually review.

**Scopes**

| Scope | Allows |
| --- | --- |
| `value.read` | Reading asset evidence and valuations the steward can see |
| `value.derive` | Recording derived valuations and checks about assets |
| `score.derive` | Recording derived scores and checks about allocation records |
| `general.derive` | Recording summaries, checks and recommendations |

---

## 2. The agent signs in

The agent proves its own key. It never holds the steward's credentials.

```http
GET  /auth/did/challenge            -> { "challenge": "…" }
POST /agents/auth/verify            { "did": "…", "challenge": "…", "signature_b64url": "…" }
```

The token carries the role `can_agent` and nothing else. **An agent token cannot create a profile, hold a wallet, own an asset, submit an allocation request or record a ledger entry about a person.** Those routes require `can_user`, and the tests assert that each one is refused.

The response includes the agent's scopes and its current queue state.

---

## 3. The agent records a derivation

```http
POST /agents/records
Authorization: Bearer <agent token>

{
  "kind": "valuation",
  "subject_ref": "asset:6b1e…",
  "statement": "Value is 15,120,000 on the recorded evidence.",
  "inputs":  {"units": 100, "occupancy": 0.9, "rent_per_unit_month": 1000,
              "opex_ratio": 0.3, "cap_rate": 0.05},
  "output":  {"value": 15120000.0},
  "method":  "can-value-engine 0.1 (income model)",
  "confidence": 0.8
}
```

The server stores canonical SHA-256 hashes of `inputs` and `output`, so the claim is exact and comparable. `statement` is what a person reads; `output` is what a machine compares.

**Record kinds:** `valuation`, `score`, `summary`, `check`, `recommendation`, `recompute`. Each kind requires a matching scope.

**Refusals are part of the interface:**

| Status | Meaning |
| --- | --- |
| `403` | Outside the agent's scopes, or the agent is suspended, revoked or has no steward |
| `422` | Unknown kind, or inputs larger than the limit (reference records instead of copying them) |
| `429` | The agent's or the steward's unreviewed queue is full, or the hourly rate is reached. **Wait; do not retry around it** |

---

## 4. Anyone can recompute it

```http
POST /agents/records/{id}/recompute
{ "output": {"value": 15120000.0}, "method": "independent rerun" }
```

If the hash matches, the record is marked `matched`. If it does not, the record is **superseded automatically**: no argument, no authority, no committee. The agent that produced a record cannot recompute its own work.

This is the point of the design. A derivation is not trusted because an agent sounds confident; it is trusted because anyone can rerun it and the system acts on a disagreement by itself.

---

## 5. A human reviews, and that is what frees the queue

```http
POST /agents/records/{id}/review
{ "accept": true, "note": "checked the inputs against the rent roll" }
```

Reviewers, admins and the agent's own steward can review. Each review moves a record out of `unreviewed`, which is what releases capacity:

```http
GET /agents/me/queue
{
  "unreviewed": 12, "ceiling": 50, "remaining": 38, "writes_paused": false,
  "steward": { "unreviewed": 100, "ceiling": 100, "remaining": 0,
               "writes_paused": true, "agents": 3, "max_agents": 5 }
}
```

There are **two ceilings**, and either one pauses writes:

| Ceiling | Default | Why |
| --- | --- | --- |
| Per agent (`max_unreviewed_records`) | 50 | One agent cannot flood the queue |
| Per steward (`max_unreviewed_per_steward`) | 100 | The person who answers for the agents has one pair of eyes, however many agents they run |

An agent should check this before a batch. A steward can see what they owe across all their agents at `GET /agents/steward/queue`. When either ceiling is reached, writes stop rather than the backlog growing past what anyone can read.

---

## 6. The steward stays in control

```http
PATCH /agents/{id}   { "status": "revoked", "reason": "superseded by a new version" }
```

Revoking or suspending takes effect immediately: live agent sessions are ended in the same call. Scopes and the queue ceiling can be tightened at any time. If the steward deletes their account, every agent they steward loses write access and its derived records go with it.

---

## What this deliberately does not do

- **No agent entitlements.** An agent cannot be issued participation units, access rights or a floor entitlement. Value created by an agent accrues to its steward, recorded as such.
- **No agent attestation.** There is no route by which an agent can claim to have seen something. If an agent's input comes from a sensor or a system, a person or an accredited attester vouches for that source.
- **No silent autonomy.** Agents act on assets only through the WP-011 assurance mandate, which is limited to alerts and requests.
- **No trust in fluency.** Nothing in the API treats a well-written `statement` as evidence. Only `inputs`, `method` and a reproducible `output` count.

---

## Endpoints

| Method | Path | Who |
| --- | --- | --- |
| GET | `/agents/rules` | anyone, unauthenticated |
| POST | `/agents/` | a person, who becomes the steward |
| GET | `/agents/`, `/agents/{id}` | the steward; reviewers, admins and auditors |
| PATCH | `/agents/{id}` | the steward (or an admin): scopes, ceiling, contact, status |
| POST | `/agents/auth/verify` | the agent, with a signed challenge |
| GET | `/agents/me/queue` | the agent (its own and its steward's ceilings) |
| GET | `/agents/steward/queue` | a person: what they owe across every agent they steward |
| POST | `/agents/records` | the agent, within its scopes and queue |
| GET | `/agents/records`, `/agents/records/{id}` | anyone signed in |
| POST | `/agents/records/{id}/review` | reviewer, admin or the agent's steward |
| POST | `/agents/records/{id}/recompute` | anyone signed in, except the record's own agent |
| GET | `/agents/records/{id}/recomputations` | anyone signed in |

---

## Next steps

1. **Recompute-on-read for CAN's own engines**, so a valuation record can be checked by the server itself rather than by another party submitting a result.
2. **Accreditation of agents per subject type**, the agent counterpart of attester accreditation.
3. **A public agent register**, so anyone affected by a derived record can find the steward without special access.
4. **Organisational stewardship**: a review team rather than one person, with the ceiling set from that team's actual capacity.

Steward-level ceilings, listed here as a gap when this page was first published, are now implemented.

Tests: `backend/tests/test_agents.py` covers registration, sign-in, scope enforcement, hashing, recomputation matching and automatic supersession, the queue ceiling and its release by review, immediate revocation, and that an agent token cannot become a person or hold anything.

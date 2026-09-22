# Safeguards in the Reference Implementation

CAN's policy documents promise rights and safeguards. This page shows which of them the reference backend enforces in code, and which remain open. It is written for regulators, auditors, researchers and pilot sponsors.

**Status:** reflects the backend as of September 2026 ([pull request #3](https://github.com/value-coordination-CAN/can-framework/pull/3)).

---

## The standing test

The test for any CAN deployment is **standing**: does the person affected hold the record, see the reasoning, and have a way to contest it? The backend is built so the answer is yes by default.

| Question | How the backend answers it |
| --- | --- |
| Do they hold the record? | Every ledger entry about a person is visible to them (`GET /ledger/entries/{their id}`), including who recorded it and whether it counts |
| Do they see the reasoning? | Every score carries an explanation: formula, weights, per-metric means and counts, and exclusions. It is stored with each allocation request |
| Can they contest it? | Any decision can be appealed. Appeals are resolved by a reviewer who is neither the appellant nor the original decision-maker, and an upheld appeal reopens the request |

---

## Rights (from the Integration Policy)

| Right | Status in code |
| --- | --- |
| Right to explanation | ✅ Explanation returned with every score and stored with every request |
| Right to appeal | ✅ Appeal, list, read and independent resolution, one open appeal per request |
| Right to human review | ✅ Allocation decisions are made by human reviewers with a stated reason. The score orders the queue but does not decide |
| Right to withdrawal | 🟡 Partly: care consent can be withdrawn (entries deleted), imported connections can be deleted, and sessions can be revoked. Full account deletion is not yet implemented |
| Right to correction | 🟡 Partly: the person can see every entry and appeal decisions. A dedicated endpoint to dispute and correct a single entry is not yet implemented |

---

## Principles

| Principle | Enforcement |
| --- | --- |
| **No universal scoring** | Scores are purpose-bound to allocation, visible only to the person, reviewers and auditors, and never exposed to other users |
| **Consent for sensitive data** | All care factors (health, parenting, burnout, age, crisis) require explicit, revocable consent. Without consent nothing can be recorded, and revoking deletes the data |
| **Care cannot penalise** | Care is an uplift only. Not consenting never lowers anyone's priority |
| **No self-certification** | Self-reported entries stay in the person's record but do not count towards priority. Counted entries need an attester and evidence |
| **Separation of duties** | Attesters record, reviewers decide, and a different reviewer resolves appeals. Nobody can decide their own request |
| **Least privilege** | Each action is tied to the caller's own profile. Others' emails are hidden, and path searches run only from oneself |
| **Data minimisation for third parties** | Imported connections are stored only as keyed, non-reversible hashes, with no names or emails |
| **Secure by default** | The service refuses to start outside development with default or weak secrets. Sessions can be revoked, and login challenges are single-use |
| **Transparency of rules** | All weights and consent rules live in versioned YAML in the public repository and are validated at startup |

---

## Open items before any live pilot

- An endpoint to dispute and correct individual entries, and full account deletion.
- Attester accreditation: which attesters may record which metrics.
- Retention periods and erasure rules for ledger entries and snapshots.
- Rate limiting on authentication endpoints.
- Independent fairness testing of the weights on pilot data.
- A data protection impact assessment and lawful-basis review for the specific pilot, especially for care data.

These match the minimum oversight requirements in [For Regulators](FOR_REGULATORS.md).

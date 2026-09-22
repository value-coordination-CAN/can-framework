# WP-011 Reference Implementation: Value Assurance

**Status:** Proposal and working reference implementation  
**Version:** 0.1  
**Date:** September 2026  
**Implements:** [WP-011 – Value Assurance: Verifying and Future-Proofing Value in Transition](../publications/wp-011-value-assurance-future-proofing.md)

---

## 1. What this contributes

WP-011 argues that value should be carried as **evidence**, not as a bare price. That evidence can then be tested against changing assumptions and kept current by an agent that acts only within the holder's mandate.

This contribution turns that argument into working, open code. It has three parts:

1. **A backend module** (`backend/app/value/`) that stores assets and their evidence, calculates an evidenced value, runs stress scenarios and records every pass of the assurance loop.
2. **A public, versioned model** (`ledgers/value_assurance.yaml`) that defines the evidence categories, the valuation inputs and the stress scenarios. Anyone with the same evidence can reproduce the same result.
3. **A reference UI** (`backend/app/ui/`, served at `/ui/`). Holders sign in with a key held in their own browser, record evidence, see value and stress results, set the agent's mandate and share selected evidence.

> Price is a number. Value is information in motion.

---

## 2. How WP-011 maps onto the code

| WP-011 concept | Implementation |
| --- | --- |
| **Evidenced value** (§1): identity, condition, revenue, assumptions, scenarios, carbon, contribution | Six evidence categories in the YAML. Each piece of evidence records who recorded it, when, with what reference, and whether it was self-reported or attested |
| **Credibility** (§1) | **Evidence confidence**: the share of the valuation model, by weight, that rests on attested evidence. Self-reported evidence is shown but does not raise confidence |
| **When value turns into liability** (§2) | The valuation flags `is_liability` when an asset costs more to hold than it earns, now or under any scenario. The explanation names the scenarios in which value turns into liability |
| **The agentic loop** (§3): detect, interpret, recalculate, explain, act | `POST /value/assets/{id}/assurance/run` records a full pass. **Detect:** inputs changed since the last run. **Interpret:** the value effect of each change on its own. **Recalculate:** base value and every scenario. **Explain:** plain-language lines. **Act:** only within the mandate |
| **Mandates: explicit, limited, revocable** (§3, §7) | The holder sets `enabled`, thresholds and `allowed_actions`. The only actions are `alert`, `request_attestation` and `request_review`. **The agent never moves, pledges or transfers value.** Actions the mandate does not allow are recorded as *recommended, not taken*, with the reason |
| **Future-proofing** (§4) | Five stress scenarios in the YAML: moderate and severe wage shocks, an energy and carbon shock, a rate rise, and a combined stress |
| **Mobility of value** (§1) and co-investors | **Selective disclosure.** The holder shares chosen categories (and optionally the valuation) with a named person, such as a lender, co-investor or auditor. That person sees only what was shared and cannot act on the asset |
| **Open specifications** (§6) | The model, inputs, weights and scenarios live in public YAML, validated at startup |
| **The standing test** (§7) | The holder holds the record (full evidence history), sees the reasoning (the explanation on every valuation and run) and controls disclosure. Export and account deletion include assets |

---

## 3. The reference valuation model

The first model is an **income approach**, the most common way to value income-producing real assets:

```
NOI   = units × occupancy × rent_per_unit_month × 12 × (1 − opex_ratio)
        − carbon_tonnes_year × carbon_price
value = NOI / cap_rate − capex_to_complete
```

Every input names its evidence category, its bounds and its weight in the confidence measure. Scenarios apply `mul` and `add` changes to inputs and are clamped to the bounds.

The model is deliberately simple and transparent. Further models, for example for operating companies, infrastructure concessions or carbon projects, can be added as separate YAML definitions that use the same evidence, scenario and agent machinery.

---

## 4. API

| Method | Path | Who |
| --- | --- | --- |
| GET | `/value/config` | any signed-in user (the public model) |
| POST | `/value/assets` | user (becomes the holder) |
| GET | `/value/assets` | user: assets held, and assets shared with them |
| GET | `/value/assets/{id}` | holder and oversight roles; grantees see shared categories only |
| POST | `/value/assets/{id}/evidence` | holder (self-reported) or attester (attested, reference required) |
| GET | `/value/assets/{id}/evidence/history` | holder and oversight roles |
| GET | `/value/assets/{id}/valuation` | holder and oversight roles; grantees if `valuation` is shared |
| PUT | `/value/assets/{id}/mandate` | holder |
| POST | `/value/assets/{id}/assurance/run` | holder |
| GET | `/value/assets/{id}/assurance/runs` | holder and oversight roles |
| GET/PUT | `/value/assets/{id}/shares` | holder |
| DELETE | `/value/assets/{id}/shares/{user_id}` | holder |

Newer evidence for the same key **supersedes** older evidence. History is kept, never overwritten.

---

## 5. Try it

```bash
cd backend
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
```

Open **http://localhost:8000/ui/**:

1. **Sign in with this browser's key.** The browser generates an Ed25519 key, keeps the private key in its own storage (non-extractable) and signs a one-time challenge.
2. Create a profile, then create an asset with **Add example evidence** ticked.
3. See the evidenced value, the five stress scenarios and the explanation. Confidence is 0% because all example evidence is self-reported.
4. Press **Run assurance agent**. With no mandate, the agent only recommends. Activate a mandate, change an input (for example occupancy), and run again to see **detect** and **interpret** pick up the change and an alert taken within the mandate.
5. Share `revenue` and `valuation` with another user's id to see selective disclosure from their side.

Attested evidence needs an attester role (OIDC). The Keycloak test user `testreviewer` has it.

---

## 6. Safeguards

- **The agent's power is bounded in code**: alerts and requests only, and only within an active mandate that the holder can change or revoke at any time.
- **Self-reported evidence cannot manufacture confidence.** Only attested evidence with a reference raises it.
- **Disclosure is chosen by the holder**, category by category, and revocable.
- **Everything is attributable**: each piece of evidence records its recorder, and each run records who triggered it and what it recommended or took.
- **Reproducible**: the model is public YAML, and the same evidence always gives the same result.

---

## 7. Proposed next steps

1. **More models.** Operating company (revenue-multiple and cash-flow), infrastructure concession, and carbon project (verified tonnes × price × integrity).
2. **Scheduled runs.** The agent runs on a schedule or when new evidence arrives, instead of only on demand.
3. **Attester accreditation per category**, for example surveyors for condition, auditors for revenue and verifiers for carbon.
4. **Portfolio view.** Aggregate evidenced value, confidence and scenario exposure across a holder's assets.
5. **Contribution link.** Connect the `contribution` category to CAN contribution ledgers, so the people who create and sustain an asset's value are visible in its record (WP-010).
6. **Signed evidence.** Evidence carried as signed, portable objects that any party can verify offline.

Tests: `backend/tests/test_value_assurance.py` covers the model arithmetic, missing evidence, attestation and confidence, supersession, validation, value turning into liability, the agent loop under and without a mandate, selective disclosure, export and deletion, and serving the UI.

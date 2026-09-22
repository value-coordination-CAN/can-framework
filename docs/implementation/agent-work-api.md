# Working API: Valuing, Revaluing, Searching, Mapping and Maintaining Value

**Status:** Published, working reference implementation  
**Version:** 0.1  
**Date:** September 2026  
**Companion to:** the [Agent Integration API](agent-integration-api.md), which covers identity, stewardship and accountability

The integration API says *who* an agent is and what it may claim. This page is the work itself: how an AI system finds assets on a node, values and revalues them, maps how they connect, keeps their value maintained, and exchanges what it knows with other nodes.

---

## The shape of it

A **node runs locally**. It holds its own assets, evidence and history, and it does not need anyone else's server to be useful. An AI system **interrogates the node** through this API: it reads what the node knows, proposes what should change, and never writes evidence itself. Nodes **exchange portable documents**, so value can move between them without either side having to trust the other's database.

```
   your AI system  ──interrogates──►  local CAN node  ──documents──►  another node
        (derives, proposes)            (holds evidence)               (verifies, imports)
```

An agent sees **exactly what its steward sees**, read-only. Being an agent is never a route to wider visibility.

---

## 1. Search: find what there is to value

```http
GET /value/search?q=harbour&kind=residential&max_confidence=0.6&liability_only=true
```

Returns the assets the caller can see, each with its access level, and, where the valuation is visible, its value, confidence, whether it is a liability and what inputs are missing. The filters are how an integrating system finds work: `max_confidence` finds value resting on too little evidence; `liability_only` finds value that turns into liability under a tested scenario.

## 2. Map: see how value connects

```http
GET /value/assets/{id}/map
```

One asset, and what it is joined to: evidence by category (with how much of it is attested), the project that built it, the contributions behind that project by source and contributor count, its suppliers, its shares, and its recent assurance runs. A grantee sees only the categories shared with them.

## 3. Valuation: the calculation, with its workings

```http
GET /value/assets/{id}/valuation
```

Base value, every stress scenario, the confidence, and an explanation in words. The model is public ([`ledgers/value_assurance.yaml`](https://github.com/value-coordination-CAN/can-framework/blob/main/ledgers/value_assurance.yaml)), so an agent can reproduce the figure itself rather than take it on trust, and record the result as a [derived record](agent-integration-api.md#3-the-agent-records-a-derivation) that anyone can recompute.

## 4. Revaluation: propose, do not assert

```http
POST /value/assets/{id}/proposals
{ "key": "occupancy", "value": 0.72,
  "source_ref": "letting report 2026-09",
  "rationale": "Three units vacant since July." }
```

**A proposal is not evidence.** It waits for the holder or an attester:

```http
POST /value/proposals/{id}/decision   { "accept": true, "note": "letting report checked" }
```

Accepted by an **attester**, it becomes attested evidence and raises confidence. Accepted by the **holder**, it becomes self-reported and does not. Rejected, nothing changes. This is how an agent revalues an asset without ever claiming to have seen anything: it can say *this figure has moved and here is where that comes from*, and a person decides.

## 5. Maintenance: the queue to work from

```http
GET /value/work
```

What needs attention across everything the caller can see, each item with a suggested action:

| Item | Raised when |
| --- | --- |
| `missing_evidence` | A model input has no evidence at all |
| `stale_evidence` | Evidence is older than `stale_evidence_days` |
| `low_confidence` | Too little of the value rests on attested evidence |
| `liability_risk` | Value turns into liability under a tested scenario |
| `never_assessed` / `assessment_due` | No assurance run, or the last one is older than `reassess_after_days` |
| `open_proposal` | A proposed revaluation is waiting for a decision |

The thresholds are in the public YAML, so an operator can tune them and an agent can read them.

---

## 6. Exchange: portable value documents

A node hands another node a **document** rather than access to its database.

```http
GET  /value/node                      # who this node is, and whether it signs
GET  /value/assets/{id}/document?disclose=revenue,assumption
POST /value/documents/verify          # check hashes, root and signature
POST /value/documents/import          # take it into this node
```

A document (`profile: can.value.v1`) carries:

- a **header**: profile, document id, issuing node, subject, model and what was disclosed;
- **items**: each piece of evidence with its own salt and hash;
- a **valuation** section, where the recipient is entitled to see it;
- a **root** hash over the header, every item hash and the valuation;
- a **signature** over the root, if the node has a key.

**Redaction that still verifies.** Withholding an item keeps its hash and drops its content. The root still checks out, so a holder can disclose revenue without disclosing tenants, and the recipient can still be sure nothing was altered or removed. Verification reports how many items were disclosed and how many withheld.

**Import is honest about provenance.** Evidence from a document arrives as **unverified** unless the signing node is in this node's trusted list, with `evidence_ref` recording `node:…/doc:…/item:…`. It does not raise confidence until someone here attests to it. Another node's word is not this node's evidence. A document that fails verification is refused outright.

**Signing.** Set `NODE_ID` and `NODE_SIGNING_KEY` (a 32-byte Ed25519 seed, base64url) and documents are signed; without a key they are unsigned, and a receiver treats them as hearsay. Trusted nodes are listed under `exchange.trusted_nodes` in the YAML as `node_id: public_key`.

---

## A worked loop

1. `GET /value/work` — the node says three assets have stale occupancy evidence.
2. `GET /value/assets/{id}/map` — the agent sees which project and contributors the asset belongs to.
3. The agent recomputes the valuation from the public model and records a **derived record**, with inputs, method and output.
4. It finds a newer letting report and posts a **proposal**, with the source.
5. The holder accepts it; the valuation moves; the queue item clears.
6. A lender asks for proof: the holder exports a **document disclosing revenue only**, and the lender verifies it without an account on this node.
7. Someone else **recomputes** the agent's derived record. If it disagrees, the record is superseded automatically.

---

## What is deliberately not here

- **No agent attestation.** There is no path by which an agent writes evidence directly. Proposals exist precisely so that it does not need one.
- **No cross-node trust by default.** Importing tells you where something came from; it does not make it true.
- **No hidden model.** Every figure an agent or a node produces comes from a published model over published evidence, so disagreement is settled by recomputation rather than authority.
- **One profile, not a format monopoly.** `can.value.v1` is what this implementation carries. `profile` is a field precisely so a deployment can carry another document format in the same envelope, including a proprietary one, without changing the API.

## Next steps

1. **Push exchange**: a node offering a document to a subscribed node, instead of waiting to be asked.
2. **Document-level selective disclosure receipts**, so a holder can prove what they disclosed to whom.
3. **Profile negotiation** between nodes, for deployments carrying more than one document format.
4. **Recompute-on-read**, so the node itself re-derives a record on request rather than waiting for a second party.

Tests: `backend/tests/test_agent_work.py` covers search and its filters, the map, the work queue, proposals accepted by holder and by attester, rejection, document round-trip, redaction that still verifies, tamper detection, signing and node identity, and import from another node arriving unverified.

# Value Map API: Needs, Capacities, Slices and Commitment Discovery

**Status:** Working reference implementation of WP-012 steps 1 and 2  
**Version:** 0.1  
**Date:** September 2026  
**Implements:** [WP-012 – The Value Map](../publications/wp-012-value-map-discovery.md)

Needs and capacities recorded on a node, shared as verifiable slices, and made findable by commitment without publishing a catalogue of what the node holds.

**Built:** map items, slices, commitments, local matching. **Not yet built:** peering between nodes, query forwarding across degrees, and introductions. Today a query is answered by the node it is asked, and goes no further.

---

## 1. Record what you have spare, and what you lack

```http
POST /map/items
{
  "item_type": "capacity",              // capacity | need
  "item_class": "covered_workshop",
  "title": "Two bays at Harbour Court",
  "quantity": 2, "unit": "bays",
  "region": "GCC-E",                     // coarse on purpose
  "available_from": "2027-01-15",
  "asset_id": "…",                       // optional: ties it to an asset (WP-011)
  "discoverable": false                  // opt in when you are ready
}
```

`GET /map/items` lists your own. `PATCH /map/items/{id}` changes discoverability, status or quantity. `DELETE` removes it. Nobody else can read, change or delete your items.

**Discoverability is opt-in and reversible.** An item that is not discoverable never matches anything, whoever asks.

---

## 2. See yourself as a searcher sees you

```http
GET /map/items/{id}/commitment
{
  "discoverable": true,
  "epoch": "E2952",
  "coarse_attributes": { "item_type": "capacity", "item_class": "covered_workshop",
                         "region": "GCC-E", "period": "2027-Q1" },
  "commitment": "9f2c…"
}
```

Those four attributes are **all** a searcher can match on. Not the quantity, not the description, not the site, not who holds it. Availability is rounded to a quarter.

---

## 3. Ask whether anything matching exists

```http
GET  /map/discovery                      # public: the epoch, the salt, the attributes, the limits
POST /map/query
{ "item_type": "capacity", "item_class": "covered_workshop",
  "region": "GCC-E", "period": "2027-Q1" }
```

The answer is **match or no match**:

```json
{ "match": true, "node_id": "riyadh-node-1", "k_anonymity": 2,
  "note": "Something matching exists on this node. Ask for an introduction; the holder decides." }
```

No contents, no identities, no quantities. You may also pass a `commitment` you formed yourself.

**What protects the map from being enumerated**, given that the attribute space is small:

| Control | Effect |
| --- | --- |
| **No listing endpoint** | Commitments are answered, never published in bulk. A node cannot be scraped for a catalogue |
| **k-anonymity** (default 2) | A node answers only where at least k of its items share the commitment, so a match never points at a single item |
| **Rate limit** (default 120 an hour, per caller) | Probing the attribute space is slow and visible |
| **Rotating epoch salt** (default 7 days) | Commitments collected in one period do not carry into the next |
| **Opt-in per item** | What should not be findable simply is not |

These are published at `GET /map/discovery` and set in [`ledgers/value_assurance.yaml`](https://github.com/value-coordination-CAN/can-framework/blob/main/ledgers/value_assurance.yaml) under `discovery`.

---

## 4. Local matching first

```http
GET /map/matches/{item_id}
{ "looking_for": "need", "matches_on_this_node": 1,
  "note": "Counts only. Ask the holder for an introduction to go further." }
```

The nearest capacity is often on the same node. This looks for the opposite kind of item with the same commitment, and returns **a count**, never the items.

---

## 5. Share a slice

```http
POST /map/slice
{ "asset_ids": ["…"], "include": ["capacity"], "purpose": "introduction to a lender" }
```

A slice is a document (`profile: can.map.v1`) with the same properties as the value documents in the [Working API](agent-work-api.md#6-exchange-portable-value-documents):

- every item carries a salted hash, and the root covers them all;
- `include` discloses chosen record types (`capacity`, `need`, `asset`) and **withholds the rest while keeping their hashes**, so the receiver knows nothing was quietly removed;
- signed by the node when `NODE_SIGNING_KEY` is set;
- verified by anyone at `POST /value/documents/verify`, with no account on the issuing node.

You can only share your own items and assets; trying to include someone else's is refused.

---

## 6. Endpoints

| Method | Path | Who |
| --- | --- | --- |
| GET | `/map/discovery` | anyone, unauthenticated: the terms for forming a query |
| POST/GET | `/map/items` | the holder |
| PATCH/DELETE | `/map/items/{id}` | the holder |
| GET | `/map/items/{id}/commitment` | the holder: what a searcher can see |
| POST | `/map/query` | any signed-in person or agent, rate-limited |
| GET | `/map/matches/{id}` | the holder: counts of matching items on this node |
| POST | `/map/slice` | the holder |

---

## 7. What is deliberately not here

- **No listing of discoverable items.** Being findable is not the same as being published.
- **No automatic introductions.** A match tells a searcher to ask. The holder decides whether to answer, and what slice to share.
- **No cross-node forwarding yet.** A query stops at the node it is asked. Peering, hop limits, path proofs and consent-based introductions are steps 3 to 5 of WP-012 §10.
- **No scoring.** Nothing here ranks holders, and matching is on attributes, not on reputation.

## 8. Next

1. **Peering**: mutual node relationships, with their own limits and logs.
2. **Forwarding**: hop-limited queries returning a path and its confidence rather than a single node's answer.
3. **Introductions**: a consent-based request that every hop may refuse, ending in a shared slice or in nothing.
4. **Shared rate-limit storage**, since the current limiter is per process.

Tests: `backend/tests/test_value_map.py` covers recording items, opt-in discoverability, commitment formation matching between holder and searcher, match and no-match answers carrying no contents, k-anonymity suppressing a single-item match, rate limiting, local matching by count, slice verification, redaction that still verifies, tamper detection, and the refusal to share what is not yours.

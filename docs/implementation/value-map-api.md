# Value Map API: Needs, Capacities, Slices and Commitment Discovery

**Status:** Working reference implementation of WP-012 steps 1 and 2  
**Version:** 0.1  
**Date:** September 2026  
**Implements:** [WP-012 – The Value Map](../publications/wp-012-value-map-discovery.md)

Needs and capacities recorded on a node, shared as verifiable slices, and made findable by commitment without publishing a catalogue of what the node holds.

**Built:** map items, slices, commitments, local matching, peering, forwarding across hops, introductions in which an offer travels to the far end by several routes at once, and **agreements** — a committed introduction becomes a recorded, verifiable agreement and, where both parties are here, a WP-010 contribution or supplier agreement.

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

## 5a. Peering and forwarding across hops

A node talks only to peers it has deliberately added. Peering is an operator's act:

```http
POST /map/peers        { "node_id": "node-b", "public_key": "…", "base_url": "https://…",
                         "trust_weight": 0.8 }        # can_admin only
GET/PATCH/DELETE /map/peers[/{id}]                    # suspend, reweight, remove
```

Then a query can travel:

```http
POST /map/query/federated
{ "item_type": "capacity", "item_class": "covered_workshop",
  "region": "GCC-E", "period": "2027-Q1", "max_degree": 3, "min_confidence": 0.1 }
```

```json
{ "found": 2,
  "results": [
    { "node_id": "node-b", "path": ["node-a","node-b"],          "degree": 1, "confidence": 0.48, "match": true },
    { "node_id": "node-c", "path": ["node-a","node-b","node-c"], "degree": 2, "confidence": 0.144, "match": true }
  ],
  "note": "Each result is a path and its confidence. To go further, ask the nodes on the path for an introduction." }
```

A result is **a path and a confidence**: how far away a match is, through which nodes, and how much the chain of trust weights supports. Nothing about what was found, whose it is, or how much of it there is.

**Confidence** is the product of the trust weights along the path, discounted once per hop (`hop_decay`, 0.6 by default). Four hops of weak links are correctly worth very little.

### What each hop enforces

| Rule | How |
| --- | --- |
| **Peering is by relationship** | A node answers and forwards only for peers it has added; strangers get 403 |
| **Requests are signed** | Each hop signs the body with its node key; the receiver verifies against the peer's public key on file |
| **No loops** | A node already in the path neither answers nor is called again, in both directions |
| **Hops are bounded** | The time to live decrements per hop and is capped by the receiving node's own `max_degree_limit`, whatever the sender asked |
| **Each peer is rate-limited** | Per-peer hourly limit, separate from the per-caller limit |
| **Everything is logged** | `GET /map/queries` (operator or auditor) shows direction, peer, path, time to live and result, with the commitment recorded as a **fingerprint**, so the log does not reveal what was sought either |

A node with no signing key cannot forward: it can answer for itself, but it cannot speak in anyone's name.

```http
POST /map/peer/query      # peer-to-peer; signed envelope, no user account involved
```

---

## 5b. Introductions: the offer travels, the far end decides, the near side commits

A path tells you a match exists. An introduction is how the two ends actually meet.

```http
POST /map/introductions
{ "paths": [["node-a","node-b","node-c"], ["node-a","node-d","node-c"]],
  "item_type": "capacity", "item_class": "covered_workshop",
  "region": "GCC-E", "period": "2027-Q1",
  "message": "We need covered space for an 18-month refit.",
  "offer": "Refit work in kind, or rent, whichever suits." }
```

Three things make this different from a ping:

1. **It is an offer, not a request for attention.** `offer` is required and travels with the message. The far end decides knowing what is on the table.
2. **It travels by itself, and by several routes at once.** Relays carry offers without being asked (`relay_policy: auto`). Give more than one route and the offer takes them all, so one hop cannot stop it. The same offer arriving twice is recognised and decided once.
3. **The far end decides.** Only a holder of the matching items — or the node's operator — can answer. Accepting means choosing **how to be reached**, and optionally sharing a verifiable slice of exactly what they choose.

```http
POST /map/introductions/{id}/decision
{ "accept": true, "reply_contact": "harbour@example.org", "share_items": ["…"] }
```

Then the near side stands behind its offer:

```http
POST /map/introductions/{id}/commit
{ "contact": "boatbuilders@example.org", "note": "we will start in January" }
```

**The far end learns who it is dealing with only when the asker commits.** Until then it sees the offer and not the asker; after commitment, the contact travels up the route that worked.

### Carrying builds connection value; not carrying is a missed chance

| What happens | What it does |
| --- | --- |
| A peer carries an offer | `carried_count` rises |
| An offer it carried ends in an acceptance | `connections_count` rises and its **trust weight increases** (`connection_weight_gain`, 0.05 by default) |
| A peer will not carry, or cannot be reached | `missed_count` rises. **Nothing is deducted** |

There is no penalty for refusing. A node that does not carry simply does not build weight, and because weight is what later paths are ranked by, traffic gradually flows through the nodes that connect people. Value flows where connection flows.

A node may set `relay_policy: review` and decide each request by hand. It may; and a refusal is recorded **in its own name** (`blocked_by`), and travels back to the asker. Holding things up is a choice anyone can see.

---

## 5c. From a commitment to a stake

An agreement should not evaporate into an email. Once an introduction is committed on both sides, either party records what was agreed:

```http
POST /map/introductions/{id}/agreement
{ "kind": "contribution",              // contribution | access | supply
  "terms": "400 hours of refit work over 18 months",
  "value": 60000, "currency": "USD" }
```

That produces a **signed agreement document** (`profile: can.agreement.v1`) which both sides keep and anyone can verify, carrying the terms, the original offer and which introduction it came from.

Then the project's sponsor turns it into a **stake** (WP-010):

```http
POST /map/agreements/{id}/link
{ "project_id": "…", "counterpart_user_id": "…", "cash_share": 0.8 }
```

| Agreement kind | Becomes | In WP-010 |
| --- | --- | --- |
| `contribution` | An in-kind contribution | earns participation units once accepted |
| `access` | A pre-committed use contribution | earns an access right on agreed terms |
| `supply` | A supplier agreement | sets the split between cash and a verified stake |

Both are created as **proposals**: the sponsor still decides the valuation, and a supplier still chooses whether to take part of the margin as a stake. Recording is done by a **party to the introduction**; attaching to a project is done by that **project's sponsor**; an agreement links once.

### Across nodes, honestly

`POST /map/agreements/import` takes the other side's document, verifies it, and stores it. It does **not** create a contribution there. A contributor on a node needs an identity someone local has vouched for, and a document arriving over the network is not that. So the agreement travels; turning it into a stake is a deliberate local act by a local party.

---

## 6. Endpoints

| Method | Path | Who |
| --- | --- | --- |
| GET | `/map/discovery` | anyone, unauthenticated: the terms for forming a query |
| POST/GET | `/map/items` | the holder |
| PATCH/DELETE | `/map/items/{id}` | the holder |
| GET | `/map/items/{id}/commitment` | the holder: what a searcher can see |
| POST | `/map/query` | any signed-in person or agent, rate-limited: this node only |
| POST | `/map/query/federated` | any signed-in person or agent: this node and its peers, returning paths |
| GET | `/map/matches/{id}` | the holder: counts of matching items on this node |
| POST | `/map/slice` | the holder |
| POST/GET/PATCH/DELETE | `/map/peers[/{id}]` | the node operator (`can_admin`); auditors may read |
| POST | `/map/peer/query` | a peered node, by signature; no user account |
| GET | `/map/queries` | operator or auditor: what this node was asked, and by whom |
| POST/GET | `/map/introductions` | any signed-in person or agent: make an offer, see yours and any waiting on you |
| POST | `/map/introductions/{id}/decision` | the far end: a holder of the matching items (or the operator); a relay in review mode: the operator |
| POST | `/map/introductions/{id}/commit` | the asker, once the far end has accepted |
| POST | `/map/peer/introduction`, `/reply`, `/commit` | a peered node, by signature |
| POST | `/map/introductions/{id}/agreement` | a party to the introduction |
| GET | `/map/agreements` | the recorder; operators and auditors see all |
| POST | `/map/agreements/{id}/link` | the project's sponsor: turns it into a WP-010 stake |
| POST | `/map/agreements/import` | any user: store the other side's verified copy |

---

## 7. What is deliberately not here

- **No listing of discoverable items.** Being findable is not the same as being published.
- **No automatic introductions.** A match tells a searcher to ask. The holder decides whether to answer, and what slice to share.
- **No contact without consent.** An offer travels on its own, but nobody's details do. The far end reveals contact only by accepting; the asker only by committing.
- **No path proofs yet.** An intermediary could in principle misreport a degree.
- **No scoring of people.** Connection value sits on **peer nodes**, from what they carried and connected. Nothing ranks holders, and matching is on attributes, never on reputation.

## 8. Next

1. **Path proofs**, so an intermediary cannot invent or shorten a degree.
2. **Shared rate-limit storage**, since the current limiter is per process.
3. **Expiry sweeping**: offers past their time to live are treated as expired when read, but nothing clears them yet.
4. **Cross-node identity**, so a contribution can name a counterpart on another node without anyone inventing an account for them. Until then, the agreement travels and the stake is created locally.

Tests: `backend/tests/test_value_map.py` covers recording items, opt-in discoverability, commitment formation matching between holder and searcher, match and no-match answers carrying no contents, k-anonymity suppressing a single-item match, rate limiting, local matching by count, slice verification, redaction that still verifies, tamper detection, and the refusal to share what is not yours.

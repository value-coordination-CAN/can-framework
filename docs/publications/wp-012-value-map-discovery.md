# WP-012 – The Value Map: A Shareable Graph of Value, and Discovery Across Degrees

**Status:** Draft proposal  
**Version:** 0.1  
**Date:** September 2026  
**Author:** Alex Nikolov  
**Builds on:** [WP-001](wp-001-network-value.md) (six degrees), [WP-005](wp-005-six-degree-network-ledger.md) (graph settlement), [WP-010](wp-010-bridge-wallet-participation-funding.md), [WP-011](wp-011-value-assurance-future-proofing.md)  
**Implementation status:** steps 1 and 2 of §10 are **built** — needs and capacities, shareable map slices and opt-in commitment discovery on a single node ([Value Map API](../implementation/value-map-api.md)). Steps 3 to 6, the protocol **between** nodes in §5, are still proposed.

---

## Abstract

A CAN node knows a great deal about the value it holds: what the assets are, what evidence stands behind them, who contributed, what capacity is unused, what is needed and when. Almost none of that is visible past the edge of the node.

Between nodes, only one discovery mechanism is in general use: **price**. To find out whether something exists, what it is worth and who can supply it, we put it on a market and read the number. That works, and it throws away everything except the number.

This paper proposes the **value map**: a node-local graph of **needs and capacities**, with the evidence behind them, that can be **shared in slices** and **searched across degrees**, so that a need can find a capacity several hops away without a central index, without crawling, and without either side disclosing more than they choose. It is six degrees of separation applied not to acquaintance but to **value**: what exists, who can vouch for it, and how to reach it.

Discovery is half of it. The other half is **traversal**: value moving along the path that was found — as access, capacity, contribution, participation or entitlement — with money settling only what must be money. The purpose is practical: turning capacity that merely exists into capacity people can actually use.

> Price tells you what something costs. A value map tells you what exists, who stands behind it, and how to get there.

---

## 0. In simple terms

Three sentences hold the whole idea.

1. **Put needs and capacities on a graph.** Every node records what it has spare and what it lacks, with the evidence behind each, and how it is connected to others.
2. **That graph is the discovery mechanism.** A need finds a capacity by travelling the graph a few hops, instead of by being priced on a market.
3. **Then value travels the path that was found.** Not only the information about it: the thing itself moves — access to the space, the use of the equipment, the hours of work, the entitlement — with money settling only the part that has to be money.

What this is for is plain enough: **unused capacity reaching people who need it**. A workshop standing empty and a boatbuilder with nowhere to work are a failure of discovery, not of production. Most of what people need already exists somewhere within a few degrees of them. The map is how they find it, and the path is how it reaches them.

That is **value discovery**: finding what exists and what it is good for, rather than finding out what someone will pay.

---

## 1. What a value map is

Each node builds a graph out of records it already holds:

| Node type | Examples |
| --- | --- |
| **Asset** | A building, a plant, a fleet, a carbon project |
| **Capacity** | Unused units, off-peak output, open training places, spare hours |
| **Need** | Housing for 40 households, storage over winter, 200 hours of surveying |
| **Entitlement** | A floor entitlement, an access right, a use right |
| **Participation** | A stake earned by contribution (WP-010) |
| **Actor** | A person, an organisation, an attester, an agent's steward |
| **Attestation** | Someone's evidence about one of the above (WP-011) |

The edges are as important as the nodes: *holds*, *built by*, *contributed to*, *supplies*, *attests*, *shares with*, *needs*, *offers*, *settles to*, *depends on*. Each edge exists because a record says so, and each carries the evidence behind it. Nothing is inferred from behaviour.

This is what the reference implementation's [asset map](../implementation/agent-work-api.md#2-map-see-how-value-connects) already returns for one asset: its evidence, the project that built it, the contributions behind that project, its suppliers. The value map is that view generalised to a whole node, and made shareable.

---

## 2. Why maps rather than markets

A market is a discovery mechanism that answers one question — *what will someone pay?* — by discarding the rest. That is efficient when the rest does not matter, and wasteful when it does:

- **Spare capacity** is invisible unless someone lists it. An empty unit and an unused training place rarely reach a market at all.
- **Fit** is not price. A workshop that suits a boatbuilder is not interchangeable with one that does not, whatever the rent.
- **Who can vouch** is missing. Price says nothing about whether the revenue figure was attested or invented.
- **Non-cash contribution** has nowhere to appear: the community that maintains a place does not show up in its price (WP-010).

A value map keeps the structure. A search over it can ask "who has unused cold storage within a day's transport, attested by someone I can check?" — a question no price answers.

---

## 3. Sharing a map: slices, not databases

A node never hands over its graph. It hands over **documents**, as the exchange layer already does: self-describing, hashed item by item, redactable in a way that still verifies, signed by the node.

A **map slice** is such a document covering a sub-graph rather than a single asset:

- the holder chooses which node types and categories are in it;
- withheld items keep their hashes, so the receiver knows the slice is complete as described and nothing was quietly removed;
- the receiver can verify it without an account on the issuing node;
- evidence from an untrusted node arrives as **unverified** and does not raise confidence until someone locally attests to it.

Sharing is therefore a deliberate act, at a chosen granularity, that can be revoked for the future but is honest about the past: a slice that has been given out has been given out.

---

## 4. Commitments: finding without revealing

Discovery has an obvious hazard. If a node must publish what it holds to be findable, it publishes exactly what an adversary wants. If it publishes nothing, nothing can be found.

The way through is to answer on **commitments** rather than publish contents. A commitment is a hash over a small number of coarse attributes — `type=capacity`, `class=cold_storage`, `region=GCC-E`, `period=2027-Q1` — mixed with an epoch salt that every node knows, so a searcher who forms the same attributes produces the same commitment. The commitment is:

- **queryable**: the same attributes give the same commitment, and the node answers match or no match;
- **not listable**: there is no endpoint that returns commitments, so a node cannot be scraped for a catalogue of what it holds;
- **not identifying**: a match reveals that *something* matching exists at that node, not what, whose, or how much.

Being honest about the limit: the attribute space is small, so a determined caller could probe it item class by item class. Secrecy is not what stops that. Three things do: **rate limits** on asking, a **k-anonymity threshold** so a node answers only where several of its items share a commitment and a match never points at one of them, and an **epoch salt that rotates**, so commitments gathered in one period do not carry into the next. Publication is opt-in per item, so an item that should not be findable simply is not.

Anything finer — the quantity, the price, the exact site, the holder — comes after contact, by consent, through a shared slice.

---

## 5. Discovery across degrees (proposed)

Six degrees is not a metaphor here; it is the routing rule. A query travels the graph a hop at a time, and what comes back is a **path**, not a database row.

```
Query:   { commitment, max_degree: 4, min_confidence: 0.2, purpose: "cold storage, winter 2027" }
Hop 1:   my node knows nothing that matches → forwards to peers I have edges with
Hop 2:   a peer has no match, but has a peer that does → forwards
Hop 3:   match. Returns a path proof: 3 hops, confidence 0.36, node ids along the way
Result:  "There is something matching, three hops away, via A and B."
```

**What a result carries:** the degree, the path's confidence, and the intermediaries needed to make an introduction. **What it does not carry:** the holder, the contents, the quantity, or any identity at the far end.

**Introduction by consent.** To go further, the searcher asks the intermediaries to pass a request along. Each hop can refuse. The far end decides whether to answer at all, and if it answers, what slice to share. Nobody is contactable merely for being on a graph.

**Confidence decays with distance**, as it already does in the reference implementation: a path's confidence is the product of its edge weights, discounted once per hop. An attested edge weighs more than a self-declared one. Four hops of weak edges is correctly worth very little.

**Discipline on the protocol**, borrowing the rule the [agent API](../implementation/agent-integration-api.md) already applies to writes:

- a hop limit, a time-to-live and a per-peer rate limit on queries;
- no forwarding of queries a node would not answer itself;
- queries logged locally, so a node can see who has been asking it what;
- no global index, no crawler, and no node obliged to answer.

---

## 5a. Value that travels the path

Discovery is only half of it. Once a path is found, **value moves along that same path**, and it need not turn into money to do so.

| What travels | How it moves | Settles in money? |
| --- | --- | --- |
| **Access** | A use right issued to the party that needs it: the workshop, the unit, the training place | No |
| **Capacity** | Hours, output or throughput committed for a period | Usually not |
| **Contribution** | Work, materials, land use given to a project | No: it earns participation or access (WP-010) |
| **Participation** | A verified stake in what the path helped create | Only when the holder chooses to settle it |
| **Entitlement** | A floor entitlement redeemed against real capacity (WP-009) | No |
| **Claim** | An invoice or receivable, pledged or settled | When the holder needs money |
| **Money** | The residual: what none of the above can carry | Yes, on ordinary rails |

Two properties matter.

**It traverses hops.** The value that moves along a four-hop path can be created at one end and used at the other, with each hop in between contributing something — an introduction, an attestation, transport, a guarantee — and each contribution recorded as participation rather than as a fee skimmed in passing. This is WP-005's multi-hop enablement, now working **between** nodes rather than inside one.

**It keeps its evidence.** What arrives is not an anonymous quantity but a thing with provenance: this access right, on these terms, over this asset, whose condition was attested by that surveyor. It can be verified on arrival, and it can be traced back if the terms are not met.

### Aiding human capacity

The point of moving value this way is what it does for people's ability to act.

- A person with skills and no premises gets a workspace, so their capacity becomes output.
- A community with time and knowledge contributes it and gains standing and access, instead of being consulted and ignored.
- A displaced professional arrives with a portable record and is matched to work that needs exactly that, rather than starting from nothing.
- A household's floor entitlement is redeemable against capacity that actually exists nearby (WP-009), rather than being cash chasing whatever price the market sets that year.
- A small supplier reaches a project four hops away that would never have found them through a tender.

In each case the constraint being lifted is the same: not a shortage of the thing, but the inability to find it and to move it without turning it into money first. **A map that carries needs and capacities, and paths that value can travel, turn latent capacity into human capacity.**

---

## 6. Trust without scoring people

The map must not become a reputation system in disguise. CAN's line holds here:

- **Weights sit on edges, not on people.** There is no score attached to an actor that travels with them.
- **Weights come from evidence**, such as attested delivery or verified contribution, and are specific to a relationship and a context.
- **Nothing is inferred from behaviour.** No browsing patterns, no response times, no social signals.
- **Derivations are recomputable.** A confidence figure is a calculation over published weights, so a party who disagrees recomputes it rather than appealing to whoever ran the query.
- **Standing applies.** Anyone who appears in a map slice can see what it says about them and contest it, exactly as with any other record.

---

## 7. What it makes possible

| Question | Answered by |
| --- | --- |
| Who has spare capacity that would meet this need? | Commitment match, then a shared slice |
| Who can attest to this asset's output, close enough to check it? | Path to an attester with the right accreditation |
| Which projects could use what we have in kind? | Need edges against our capacity edges (WP-010) |
| Where would a floor's entitlements actually be redeemable? | Capacity nodes near the people entitled (WP-009) |
| Is this counterparty connected to anything we can verify? | Path confidence, with evidence at each hop |
| What is exposed if this scenario happens? | Dependency edges across nodes, not just within one (WP-011) |

The last one matters most for the wider argument. A single node can test its own assets against a shock. Only a map can show that four of them depend on the same supplier three hops away.

---

## 8. A worked case

A regional development node holds two buildings with unused workshop space. A boatbuilder's cooperative on another node needs covered space near water for eighteen months, and can pay partly in refit work.

1. The cooperative's node forms a commitment for `capacity / covered_workshop / coastal / 2027-Q1` and queries its peers with a hop limit of four.
2. Two matches come back: one two hops away, one four. The nearer path has confidence 0.42, the further 0.09.
3. The cooperative asks the intermediary on the nearer path for an introduction. The intermediary forwards it; the development node agrees to talk.
4. The development node shares a slice: the space, its condition evidence, its access terms. Not its tenants, not its financing.
5. The cooperative verifies the slice without an account on the other node, and sees that the condition evidence is attested by a surveyor it can check.
6. They agree terms that are part money and part refit work. The refit is recorded as an in-kind contribution earning participation and access (WP-010); the improved condition becomes evidence on the building (WP-011).

No market listed the space. No platform took a fee for the match. Nothing about either party was published to find it.

---

## 9. Risks, and what they require

| Risk | Response |
| --- | --- |
| **Re-identification from graph shape** | Coarse attributes only; pairwise pseudonyms per relationship; suppress matches below a k-anonymity threshold |
| **Enumeration of what a node holds** | Salted commitments, rotated; rate limits; no bulk export of commitments |
| **Sybil peers harvesting queries** | Peering is by relationship, not open; queries carry no identity by default; local logging of who asks what |
| **Discovery becoming surveillance** | Publication is opt-in per item; a right to be unlisted; nothing inferred from behaviour |
| **Brokers re-emerging as toll-keepers** | Introductions are consent-based and free; no node may require payment to forward a query; paths are visible, so a monopoly intermediary is visible too |
| **False confidence** | Confidence is a published calculation, recomputable by anyone who disagrees |
| **Cross-node data protection** | A slice is a disclosure: purpose, lawful basis and retention travel with it |

The toll-keeper risk deserves emphasis. A discovery layer that becomes indispensable is a platform, and platforms extract. The defences are structural: no global index to own, consent-based introductions, and the ability of any node to peer directly once introduced.

---

## 10. Implementation proposal

The pieces that exist today: a node-local graph of assets, evidence, projects and contributions; the per-asset map; portable, redactable, signed documents with verification and import; path search with decay over consented edges; queue and rate discipline for agents.

What this paper proposes adding, in order. **Steps 1 and 2 are now built** ([Value Map API](../implementation/value-map-api.md)):

1. ✅ **Map slices**: document export extended from one asset to a chosen sub-graph, with the same hashing and redaction.
2. ✅ **A commitment index**: opt-in, salted commitments per discoverable item, with rotation, rate limits and a k-anonymity threshold.
3. **Peering**: explicit, mutual peer relationships between nodes, with their own rate limits and logs. *(Next: today a query is answered by the node it is asked, and goes no further.)*
4. **The query protocol**: hop-limited, TTL-bounded queries returning path proofs rather than contents.
5. **Introductions**: a consent-based request that each hop may refuse, ending in a shared slice or nothing.
6. **Local query logs and controls**: what was asked of this node, by whom, and what it answered.

Each step is useful on its own, and none of them requires a central registry.

---

## 11. Open questions

- **How coarse should attributes be?** Too fine and commitments become a catalogue; too coarse and matches are useless. This needs testing on real data, not argument.
- **Who pays for forwarding?** Queries cost something to carry. Reciprocity may be enough at small scale; it may not be at large.
- **What is the right k for suppression?** It depends on how sparse a region's nodes are, and sparse regions are exactly where discovery matters most.
- **Should paths be provable?** A cryptographic path proof stops intermediaries inventing degrees, at the cost of complexity.
- **How do maps relate to registries?** Land registries, company registers and carbon registries are authoritative for parts of this graph. Reading them is straightforward; reconciling disagreement is not.

---

## 12. In one line

Put needs and capacities on a graph, let a need find a capacity a few hops away, and let the value travel that path as access, capacity, contribution or a stake, with money settling only what must be money. Money made value findable by making it comparable, and lost everything else; a map makes it findable by keeping its structure — and turns capacity that exists into capacity people can use.

# WP-008 – From Price Discovery to Value Discovery: The Knowledge Vector and a Six-Stage Path for Payments

**Status:** Draft  
**Version:** 0.1  
**Date:** September 2026  
**Author:** Alex Nikolov  

---

## Abstract

Payment modernisation today improves the speed, cost and finality of one thing: a single number with the context removed. Instant rails, stablecoins, tokenised deposits and central bank digital currencies (CBDCs) all move that number faster. This paper argues that the more important modernisation lets knowledge travel with value. Payments would carry who, what, why, on what terms and with what evidence, and would link to the contributions, needs and capacities that CAN already records.

It sets out the difference between money as a **compressed scalar** and value as a **knowledge vector**. It then proposes a six-stage path from today's instant account money to direct value handling. Each stage works on its own, runs alongside existing systems and can be reversed.

> Price is a number. Value is information in motion.

---

## 1. The Compressed Scalar

Money's great achievement is compression. It reduces who, what, why and on what terms to one number that anyone will accept. That is what lets strangers coordinate at scale (WP-001, WP-004).

Compression has a cost. Everything money discards has to be rebuilt afterwards, at every institution, over and over:

- invoices and contracts to say what a payment was for;
- identity, anti-money-laundering and sanctions checks repeated at each hop;
- escrow and intermediaries to hold value until conditions are met;
- audits, reconciliations and disputes to reconstruct what happened;
- clawbacks when public money did not reach its purpose.

The unit cost of financial intermediation has stayed at roughly 2% for about a century (Philippon, 2015). Faster rails move the number faster. They do not shrink the reconstruction around it.

---

## 2. The Economics Are Already Moving

About $2 quadrillion a year moves through payment systems (McKinsey Global Payments Report 2025). Industry revenue is a small fraction of that and grows slowly. Real-time account-to-account payments and digital wallets are taking share quickly (BCG 2025; Worldpay 2026), and adjusted stablecoin volume has become a serious parallel rail.

As moving money becomes nearly free, value moves up the stack:

| Layer | Role |
| --- | --- |
| Payment rails | Commodity infrastructure |
| Proof and trust | Differentiation |
| Value discovery | The next infrastructure layer |

A trusted proof and value layer can work across every rail (cards, bank transfers, stablecoins, CBDCs) without replacing any of them. It becomes more valuable as the rails beneath it commoditise. This is the role WP-007's translation layer anticipates.

---

## 3. The Knowledge Vector

| Dimension | Scalar today | Knowledge vector |
| --- | --- | --- |
| Parties | Re-checked at each institution | Standing proved once, disclosed selectively |
| Purpose | Free-text reference | A signed statement of what the payment is for |
| Obligation | Separate invoice or contract | Linked to delivery or certification |
| Conditions | Escrow, intermediaries, courts | Carried with the value and checked on release |
| Evidence | Rebuilt later by audit | Recorded as it happens |
| Provenance | None, by design | Source, backing and prior terms |
| Contribution | Invisible | Linked to CAN contribution, reliability and care records |

Settlement stays in money wherever money is needed. The unit of account and the central bank's role do not change. The vector changes what travels **alongside** settlement, and whether settlement is needed at all.

---

## 4. A Six-Stage Path

| Stage | What it unlocks | CAN relevance |
| --- | --- | --- |
| 1. Instant account money | Speed: today's baseline | Hybrid settlement mode (WP-007) |
| 2. Offline value | Resilience, inclusion, cash-like privacy; a carrier the holder controls | Entitlements provable without connectivity |
| 3. CBDCs, stablecoins, tokenised deposits | Programmable, final settlement | More settlement targets for the translation layer |
| 4. Payment with proof | Pay on verified delivery or certification without intermediaries | Contribution evidence triggers settlement |
| 5. Conditional value | Public support that reaches its purpose and ends cleanly | Access entitlements with their terms built in |
| 6. Direct value handling | Claims, needs, capacities and contributions matched; money settles only the rest | Pure CAN mode at scale |

Each stage is deployable alone, coexists with the previous one and can be rolled back. No stage asks anyone to give up money they already trust.

---

## 5. Programmable Payments, Not Programmable Money

The European Central Bank has said the digital euro will not be programmable money but can support conditional payments. CAN adopts the same line:

- Rules live in **transactions and entitlements**, set by law or by the parties and visible to the holder.
- Rules never live in the **currency**. A unit of money stays a neutral unit of money.
- Purpose-bound public support is a conditional **claim**, settled in neutral money.

This keeps monetary sovereignty and fungibility where they are, while letting knowledge travel with value.

---

## 6. Safeguards: Neither 1984 Nor The Hunger Games

A payment system that carries knowledge is more powerful for whoever controls it. There are two failure modes to avoid. One is everyone watched from a centre. The other is access rationed from above as a contest. The design answers both:

- Knowledge is held by the parties it describes and disclosed selectively, for a stated purpose.
- Offline holdings are capped and private.
- Specifications are open and forkable, with several independent attesting bodies.
- There is no general behavioural scoring. CAN reliability signals should stay specific to a context and to contribution, and remain subject to the appeals and redress pathways in the [Policy Overview](../about/POLICY_ABOUT.md).
- Cash and plain money remain available.

**The standing test:** does the person affected hold the record, see the reasoning and have a way to contest it? If not, the design has failed, however efficient it is.

---

## 7. Implications for CAN

1. The WP-007 translation layer should carry knowledge-vector metadata by default, not only a hash reference.
2. Stage 4 (payment with proof) is the natural first pilot. It is valuable today, fits existing regulation and produces the contribution evidence CAN needs.
3. Stages 5 and 6 map directly onto CAN access entitlements and pure CAN mode.

---

## References

- McKinsey & Company, *Global Payments Report 2025*.
- BCG, *Global Payments Report 2025*.
- Worldpay, *Global Payments Report 2026*.
- Philippon, T. (2015), "Has the US Finance Industry Become Less Efficient?", *American Economic Review*.
- European Central Bank, digital euro publications (2025–26).
- Atlantic Council, CBDC Tracker (2026).

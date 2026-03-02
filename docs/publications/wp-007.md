
# WP-007 – Hybrid Integration of CAN with Existing Payment Rails

**Status:** Draft  
**Version:** 0.1  
**Date:** March 2026  
**Author:** Alex Nikolov  

---

## Abstract

This working paper proposes a hybrid integration architecture enabling the Contribution–Access Network (CAN) to interoperate with existing monetary payment rails.

The objective is to preserve direct value handling within the coordination layer while leveraging regulated financial infrastructure when monetary settlement is necessary.

This hybrid approach enables immediate deployability, regulatory compatibility, and gradual systemic transition.

---

## 1. Introduction

Money historically served as both a coordination mechanism and a settlement mechanism.

Modern tokenisation improves settlement efficiency but does not redesign the coordination layer.

CAN separates these concerns:

- Coordination is contribution-based.
- Settlement is conditional and external.
- Money becomes a fallback mechanism rather than the core allocator of value.

---

## 2. Core Principle

Coordination and settlement must be structurally separated.

CAN:
- Does not issue currency
- Does not replace payment providers
- Does not act as a bank

Instead, CAN:
- Produces entitlement decisions
- Determines access based on contribution and reliability
- Triggers monetary settlement only when required

---

## 3. Three-Layer Hybrid Architecture

### Layer A — CAN Coordination Core

Responsible for:
- Verified contribution tracking
- Reputation vectors
- Reliability scoring
- Contextual modifiers
- Access entitlement decisions

Output: **Access Entitlement Decision**  
Not: **Payment Instruction**

---

### Layer B — Translation Layer (Hybrid Bridge)

Functions:
- Evaluates whether monetary settlement is required
- Converts entitlement decisions into conditional payment triggers
- Attaches CAN metadata
- Receives settlement confirmations

This layer acts as a **Value → Money adapter**, not a wallet.

---

### Layer C — Existing Payment Rails

Integration targets include:
- Banking rails (Faster Payments, SEPA, SWIFT)
- PSP APIs
- Card networks
- Open Banking endpoints
- Stablecoins
- CBDCs (where applicable)

Settlement flows only when triggered.

---

## 4. Operational Modes

### Pure CAN Mode

Used when no monetary transfer is required.

Examples:
- Resource allocation
- Governance rights
- AI prioritisation
- Community participation

---

### Hybrid Settlement Mode

1. Contribution validated
2. Entitlement determined
3. Translation layer evaluates settlement requirement
4. Payment triggered externally
5. Confirmation returned to CAN
6. Reputation updated

Money becomes proof of finality — not proof of value.

---

## 5. Metadata Enrichment

CAN attaches context to settlement flows:

- Contribution hash reference
- Reliability score ID
- Context tag
- Dispute state

---

## 6. Regulatory Alignment

The hybrid model:
- Does not issue money
- Does not create tradable credits
- Uses regulated settlement entities
- Minimises systemic disruption

---

## 7. Strategic Benefits

- Immediate deployability
- Institutional compatibility
- Gradual monetary decoupling
- Reduced systemic shock
- Enhanced coordination transparency

---

## 8. Evolution Path

Phase 1 — Hybrid coexistence  
Phase 2 — Monetary settlement optional  
Phase 3 — Money primarily for external interoperability  

---

## 9. Conclusion

WP-007 formalises a deployable bridge between CAN coordination and legacy monetary infrastructure, enabling evolutionary transition rather than disruptive replacement.

---

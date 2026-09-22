# CAN — Quick Start for Regulators and Supervisory Authorities

## What CAN is (in regulatory terms)
CAN is a digital coordination layer for allocating access to shared resources using verified contribution, reliability, and care signals. It operates alongside monetary and fiscal systems and does **not** constitute a substitute for legal tender or a regulated payment instrument.

## Minimum oversight requirements
Before authorising a pilot, verify:
- lawful basis for data processing
- audit capability (technical + procedural)
- explainability where automation is used
- right to appeal and redress
- cybersecurity controls and incident reporting

## What the reference implementation already enforces
The open-source backend builds several of these requirements into code. See [Safeguards in the Reference Implementation](SAFEGUARDS_IN_CODE.md) for the full mapping and the items still open.
- **Explainability:** every priority score carries a readable explanation, which is stored with each allocation request.
- **Appeal and redress:** appeals are resolved by a reviewer independent of the original decision, and an upheld appeal reopens the request.
- **Human review:** decisions are made by human reviewers with a stated reason. The score orders the queue but does not decide.
- **Sensitive data:** care factors (health, age, family life, crisis) need explicit, revocable consent, and revoking deletes the data. Care can raise priority but never lower it.
- **No self-certification:** only entries attested with evidence count towards priority.
- **Secure defaults:** the service will not start in production with default secrets, and sessions can be revoked.

## Sandbox approach
Recommended sequence:
1) regulatory sandbox approval
2) limited scope + population
3) continuous reporting
4) independent evaluation
5) exit/rollback procedures

## Interaction with CBDC and digital identity
Where integrated with CBDC platforms:
- separate payments from allocation decisions
- make conditional rules transparent and contestable
- prevent function creep via legal constraints and governance separation

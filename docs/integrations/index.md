# Integrations & Platforms

This section documents how CAN integrates with external systems.

---

## Available Integrations

- [Mindcraft Simulation Platform](mindcraft/README.md)
- [LinkedIn (Consent Import)](https://github.com/value-coordination-CAN/can-framework/blob/main/backend/README_LINKEDIN_INTEGRATION.md)

### LinkedIn (Consent Import)

A person can upload their **own** LinkedIn connections export to seed their CAN network. Their connections have not consented to CAN, so:

- names and emails are **not stored**;
- each connection is kept only as a keyed hash (HMAC-SHA256 with a server-side secret), which cannot be reversed by guessing emails;
- LinkedIn is never crawled or queried;
- the person can delete everything they imported at any time (`DELETE /integrations/linkedin/import`).

Multi-degree paths (`GET /network/path`) can only be searched from oneself.

---

## Governance

All integrations must comply with the [Integration Policy](INTEGRATION_POLICY.md). See [Safeguards in the Reference Implementation](../about/SAFEGUARDS_IN_CODE.md) for how the backend enforces it.

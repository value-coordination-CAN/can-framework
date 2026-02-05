# Mindcraft Integration (Minecraft Agent Testbed)

This integration connects CAN with **mindcraft-bots/mindcraft** via Mineflayer.

It enables behavioural simulation and policy testing.

---

## Purpose

- Test allocation under scarcity
- Study gaming behaviour
- Validate reliability incentives
- Evaluate care safeguards
- Produce reproducible research data

---

## Architecture

Mindcraft Bots → Adapter → CAN API → Allocation Engine → In-world Access

---

## Components

### Adapter
Location:
simulations/mindcraft/adapter/

### Scenario Mapper
scenario-map.json

### Test Harness
Smoke tests and replayable scenarios

---

## Setup

```bash
cd simulations/mindcraft/adapter
npm install
cp .env.example .env
npm run start
```

---

## Example

In chat:

!housing Near workplace

Triggers allocation request.

---

## Security & Ethics

- No public servers
- No autonomous code execution
- No hidden surveillance
- Ethical approval for research

---

## Roadmap

- Adversarial testing
- Appeal simulation
- CI-based stress tests

# CAN ↔ Mindcraft Integration (Minecraft agent testbed)

This folder is a starter integration for **mindcraft-bots/mindcraft** (Mineflayer-based).
It turns in-world bot events into CAN ledger entries and allocation requests.

> Security note: Mindcraft can allow an LLM to write/execute code depending on settings.
> Do **NOT** enable insecure coding or run on public servers. See Mindcraft repo warning.

## What you get
- A Node.js adapter that:
  - Connects a Mineflayer bot
  - Observes events (chat, block updates, deaths, disconnects)
  - Emits **CAN events** to your CAN backend (`/ledger/entries`, `/allocation/requests`, `/score/calculate/{user_id}`)
- A simple scenario mapper (`scenario-map.json`) mapping Minecraft actions → CAN ledger metrics
- A smoke test script

## Quick start (local)
1) Ensure CAN backend is running (from repo root):
```bash
cd backend
docker compose up --build
```

2) Install Node deps for adapter:
```bash
cd simulations/mindcraft/adapter
npm install
cp .env.example .env
```

3) Edit `adapter/.env` (CAN token and user_id), then start:
```bash
npm run start
```

## Configure
Edit `adapter/.env`:
- `MC_HOST`, `MC_PORT`, `MC_USERNAME`, `MC_VERSION`
- `CAN_BASE_URL` (e.g. http://localhost:8000)
- `CAN_BEARER_TOKEN` (OIDC token or DID-session token)
- `CAN_USER_ID` (the CAN user the bot maps to)

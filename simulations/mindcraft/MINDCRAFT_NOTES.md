# Using this with mindcraft-bots/mindcraft

Mindcraft runs Mineflayer bots with an LLM loop. This adapter is deliberately **LLM-agnostic**:
it listens to Mineflayer events and calls CAN.

Integration patterns:

## Pattern A (recommended): sidecar adapter
- Run Mindcraft bot as usual
- Run this adapter as a sidecar process against the same Minecraft server
- Use the adapter to:
  - log events
  - post ledgers to CAN
  - request allocations via chat commands

## Pattern B: Mindcraft plugin / patch
- Add an event emitter in Mindcraft code that calls this adapter or calls CAN directly.
- Lower latency, fewer moving parts, but requires maintaining a fork.

Security warning: do not enable insecure coding, do not connect to public servers.
See Mindcraft repo warning in README.  

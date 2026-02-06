import "dotenv/config";
import mineflayer from "mineflayer";
import path from "path";
import { fileURLToPath } from "url";

import { CANClient } from "./canClient.js";
import { ScenarioMapper } from "./scenarioMapper.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const cfg = {
  mc: {
    host: process.env.MC_HOST,
    port: Number(process.env.MC_PORT || "25565"),
    username: process.env.MC_USERNAME,
    version: process.env.MC_VERSION || undefined,
  },
  can: {
    baseUrl: process.env.CAN_BASE_URL,
    bearer: process.env.CAN_BEARER_TOKEN,
    userId: process.env.CAN_USER_ID,
  },
  autoScoreEvery: Number(process.env.AUTO_SCORE_EVERY || "0"),
};

if (!cfg.can.bearer || cfg.can.bearer === "REPLACE_ME") {
  console.error("Set CAN_BEARER_TOKEN in adapter/.env");
  process.exit(2);
}
if (!cfg.can.userId || cfg.can.userId === "REPLACE_ME") {
  console.error("Set CAN_USER_ID in adapter/.env");
  process.exit(2);
}

const can = new CANClient({ baseUrl: cfg.can.baseUrl, bearer: cfg.can.bearer });
const mapper = new ScenarioMapper(path.join(__dirname, "..", "..", "scenario-map.json"));

let eventCount = 0;

function mkEvidence(bot, evtType, extra = {}) {
  return JSON.stringify({
    source: "minecraft",
    evtType,
    bot: bot.username,
    server: `${cfg.mc.host}:${cfg.mc.port}`,
    ts: new Date().toISOString(),
    ...extra
  });
}

async function emitLedger(bot, evtType, extra = {}) {
  const mapped = mapper.mapEvent(evtType);
  if (!mapped) return;

  const entry = {
    user_id: cfg.can.userId,
    ledger_type: mapped.ledger_type,
    metric: mapped.metric,
    value: mapped.value,
    evidence_ref: mkEvidence(bot, evtType, extra),
  };

  await can.addLedgerEntry(entry);
  eventCount += 1;

  if (cfg.autoScoreEvery > 0 && eventCount % cfg.autoScoreEvery === 0) {
    await can.calculateScore(cfg.can.userId);
  }
}

const bot = mineflayer.createBot(cfg.mc);

bot.on("spawn", async () => {
  console.log("Bot spawned:", bot.username);
  await emitLedger(bot, "quest_start", { note: "spawn" });
});

bot.on("chat", async (username, message) => {
  if (username === bot.username) return;

  if (message.startsWith("!housing ")) {
    const desc = message.slice("!housing ".length).trim();
    const req = await can.requestAllocation({ user_id: cfg.can.userId, pool: "housing", description: desc });
    bot.chat(`CAN: housing request submitted (id=${req.id}, priority=${req.priority_score})`);
    return;
  }
});

bot.on("blockUpdate", async (oldBlock, newBlock) => {
  if (oldBlock && newBlock && oldBlock.type === 0 && newBlock.type !== 0) {
    await emitLedger(bot, "block_place", { block: newBlock.name });
  }
});

bot.on("death", async () => {
  await emitLedger(bot, "injury_event", { hp: bot.health });
});

bot.on("kicked", async (reason) => {
  console.error("Kicked:", reason);
  await emitLedger(bot, "disconnect", { reason: String(reason) });
});

bot.on("error", (err) => {
  console.error("Mineflayer error:", err);
});

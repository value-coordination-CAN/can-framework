import "dotenv/config";
import { CANClient } from "./canClient.js";

const can = new CANClient({ baseUrl: process.env.CAN_BASE_URL, bearer: process.env.CAN_BEARER_TOKEN });

(async () => {
  console.log("Smoke test: posting a ledger entry to CAN...");
  const userId = process.env.CAN_USER_ID;
  const r = await can.addLedgerEntry({
    user_id: userId,
    ledger_type: "contribution",
    metric: "maintenance.smoke_test",
    value: 1.0,
    evidence_ref: "mindcraft-adapter-smoke"
  });
  console.log("OK:", r.id);
})();

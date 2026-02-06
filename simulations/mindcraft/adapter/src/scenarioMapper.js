import fs from "fs";

export class ScenarioMapper {
  constructor(mapPath) {
    this.map = JSON.parse(fs.readFileSync(mapPath, "utf-8"));
  }

  mapEvent(evtType) {
    for (const ledgerType of ["contribution","reliability","care"]) {
      const hit = this.map?.[ledgerType]?.[evtType];
      if (hit) return { ledger_type: ledgerType, metric: hit.metric, value: hit.value };
    }
    return null;
  }
}

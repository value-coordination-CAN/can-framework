import fetch from "node-fetch";

export class CANClient {
  constructor({ baseUrl, bearer }) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.bearer = bearer;
  }

  _headers() {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${this.bearer}`,
    };
  }

  async addLedgerEntry(entry) {
    const r = await fetch(`${this.baseUrl}/ledger/entries`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify(entry),
    });
    if (!r.ok) {
      const t = await r.text();
      throw new Error(`CAN /ledger/entries failed ${r.status}: ${t}`);
    }
    return r.json();
  }

  async calculateScore(userId) {
    const r = await fetch(`${this.baseUrl}/score/calculate/${encodeURIComponent(userId)}`, {
      method: "POST",
      headers: this._headers(),
    });
    if (!r.ok) {
      const t = await r.text();
      throw new Error(`CAN /score/calculate failed ${r.status}: ${t}`);
    }
    return r.json();
  }

  async requestAllocation(payload) {
    const r = await fetch(`${this.baseUrl}/allocation/requests`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const t = await r.text();
      throw new Error(`CAN /allocation/requests failed ${r.status}: ${t}`);
    }
    return r.json();
  }
}

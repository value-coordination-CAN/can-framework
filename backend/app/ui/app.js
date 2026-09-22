// CAN Value Assurance reference UI (WP-011). Plain JS, no build step.
// All server data is rendered with textContent, never innerHTML.
"use strict";

const state = { token: null, me: null, config: null, assetId: null, currency: "USD" };
const $ = (s, root = document) => root.querySelector(s);

// ---------- small helpers ----------
function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) n.append(c instanceof Node ? c : String(c));
  return n;
}
function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (err ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.className = "toast"), 3200);
}
function money(v) {
  if (v === null || v === undefined) return "–";
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency: state.currency, maximumFractionDigits: 0 }).format(v); }
  catch { return Math.round(v).toLocaleString(); }
}
const pct = (x) => `${Math.round(x * 100)}%`;
const show = (id, on = true) => $(id).classList.toggle("hidden", !on);

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    const e = new Error(detail || res.statusText);
    e.status = res.status;
    throw e;
  }
  return data;
}

// ---------- DID key in the browser (Ed25519, non-extractable private key in IndexedDB) ----------
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function base58(bytes) {
  let digits = [0];
  for (const b of bytes) {
    let carry = b;
    for (let i = 0; i < digits.length; i++) { carry += digits[i] << 8; digits[i] = carry % 58; carry = (carry / 58) | 0; }
    while (carry) { digits.push(carry % 58); carry = (carry / 58) | 0; }
  }
  let out = "";
  for (const b of bytes) { if (b === 0) out += "1"; else break; }
  for (let i = digits.length - 1; i >= 0; i--) out += B58[digits[i]];
  return out;
}
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function idb() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open("can-did", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("keys");
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
async function idbGet(k) { const db = await idb(); return new Promise((res, rej) => { const q = db.transaction("keys").objectStore("keys").get(k); q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error); }); }
async function idbPut(k, v) { const db = await idb(); return new Promise((res, rej) => { const t = db.transaction("keys", "readwrite"); t.objectStore("keys").put(v, k); t.oncomplete = res; t.onerror = () => rej(t.error); }); }

async function getKey(fresh = false) {
  let kp = fresh ? null : await idbGet("ed25519");
  if (!kp) {
    kp = await crypto.subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"]);
    await idbPut("ed25519", kp);
  }
  const raw = new Uint8Array(await crypto.subtle.exportKey("raw", kp.publicKey));
  const did = "did:key:z" + base58(new Uint8Array([0xed, 0x01, ...raw]));
  return { kp, did };
}

async function didSignIn(fresh = false) {
  const { kp, did } = await getKey(fresh);
  const { challenge } = await api("GET", "/auth/did/challenge");
  const sig = await crypto.subtle.sign({ name: "Ed25519" }, kp.privateKey, new TextEncoder().encode(challenge));
  const out = await api("POST", "/auth/did/verify", { did, challenge, signature_b64url: b64url(sig) });
  setToken(out.access_token, did);
}

function setToken(token, label) {
  state.token = token;
  try { sessionStorage.setItem("can-token", token); sessionStorage.setItem("can-label", label || ""); } catch {}
}

// ---------- app flow ----------
async function boot() {
  try { state.token = sessionStorage.getItem("can-token"); } catch {}
  $("#btn-did").onclick = () => withBusy($("#btn-did"), async () => { await didSignIn(false); await afterSignIn(); });
  $("#btn-new-did").onclick = () => withBusy($("#btn-new-did"), async () => { await didSignIn(true); await afterSignIn(); });
  $("#btn-token").onclick = async () => { setToken($("#token-input").value.trim(), "access token"); await afterSignIn(); };
  $("#form-profile").onsubmit = onCreateProfile;
  $("#form-asset").onsubmit = onCreateAsset;
  $("#btn-export").onclick = onExport;
  if (!("subtle" in crypto)) $("#signin-msg").textContent = "This browser has no WebCrypto; use an access token.";
  if (state.token) await afterSignIn(); else show("#signin");
}

async function withBusy(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message, true); if (e.name === "NotSupportedError") $("#signin-msg").textContent = "This browser does not support Ed25519 keys yet. Use a recent Chrome, Edge, Firefox or Safari, or an access token."; }
  finally { btn.disabled = false; }
}

async function afterSignIn() {
  show("#signin", false);
  try {
    state.me = await api("GET", "/identity/users/me");
  } catch (e) {
    if (e.status === 401) { state.token = null; show("#signin"); $("#signin-msg").textContent = "Session expired. Sign in again."; return; }
    if (e.status === 403) { renderWho(); show("#profile"); return; }
    throw e;
  }
  renderWho();
  show("#profile", false);
  state.config = await api("GET", "/value/config");
  show("#assets");
  $("#my-id").textContent = state.me.id;
  await loadAssets();
}

function renderWho() {
  const w = $("#whoami");
  w.replaceChildren();
  let label = "";
  try { label = sessionStorage.getItem("can-label") || ""; } catch {}
  if (state.me) w.append(el("span", {}, `Signed in as ${state.me.display_name}`));
  if (label.startsWith("did:")) w.append(el("code", { title: label }, label.slice(0, 22) + "…"));
  w.append(el("button", { class: "ghost", onclick: signOut }, "Sign out"));
}

async function signOut() {
  try { await api("POST", "/auth/did/logout"); } catch {}
  state.token = null; state.me = null;
  try { sessionStorage.clear(); } catch {}
  location.reload();
}

async function onCreateProfile(ev) {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    await api("POST", "/identity/users", { display_name: f.get("display_name"), email: f.get("email") });
    await afterSignIn();
  } catch (e) { $("#profile-msg").textContent = e.message; }
}

async function onExport() {
  const data = await api("GET", "/identity/users/me/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = el("a", { href: URL.createObjectURL(blob), download: "can-my-data.json" });
  document.body.append(a); a.click(); a.remove();
}

// ---------- assets ----------
async function loadAssets(selectId) {
  const { held, shared_with_me } = await api("GET", "/value/assets");
  const list = $("#asset-list");
  list.replaceChildren();
  if (!held.length && !shared_with_me.length) list.append(el("p", { class: "muted small" }, "No assets yet."));
  for (const a of held) list.append(assetButton(a, "held"));
  for (const a of shared_with_me) list.append(assetButton(a, "shared: " + a.shared_categories.join(", ")));
  const id = selectId || state.assetId || held[0]?.id || shared_with_me[0]?.id;
  if (id) await openAsset(id);
}
function assetButton(a, tag) {
  return el("button", { class: a.id === state.assetId ? "active" : "", "data-id": a.id, onclick: () => openAsset(a.id) },
    a.name, el("span", { class: "tag" }, `${a.kind} · ${tag}`));
}

const EXAMPLE = [
  ["identity", "units", 120, "title register"],
  ["revenue", "occupancy", 0.92, "rent roll"],
  ["revenue", "rent_per_unit_month", 1450, "rent roll"],
  ["assumption", "opex_ratio", 0.34, "operating budget"],
  ["assumption", "cap_rate", 0.055, "comparable transactions"],
  ["condition", "capex_to_complete", 2500000, "surveyor report"],
  ["carbon", "carbon_tonnes_year", 410, "metered energy"],
  ["assumption", "carbon_price", 85, "exchange price"],
];

async function onCreateAsset(ev) {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const a = await api("POST", "/value/assets", { name: f.get("name"), kind: f.get("kind"), currency: (f.get("currency") || "USD").toUpperCase() });
  if (f.get("example")) {
    for (const [category, key, value, ref] of EXAMPLE) await api("POST", `/value/assets/${a.id}/evidence`, { category, key, value, evidence_ref: ref });
  }
  ev.target.reset();
  toast("Asset created");
  await loadAssets(a.id);
}

async function openAsset(id) {
  state.assetId = id;
  document.querySelectorAll("#asset-list button").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  const detail = await api("GET", `/value/assets/${id}`);
  state.currency = detail.asset.currency;
  const view = $("#asset-view");
  const node = $("#tpl-asset").content.cloneNode(true);
  const root = el("div", { class: "stack" });
  root.append(node);
  view.replaceChildren(root);

  const full = detail.access === "full";
  $('[data-f="name"]', root).textContent = detail.asset.name;
  $('[data-f="kind"]', root).textContent = detail.asset.kind;
  $('[data-f="access"]', root).textContent = full ? "you hold this asset" : `shared with you: ${detail.access.join(", ") || "nothing"}`;
  $('[data-act="refresh"]', root).onclick = () => openAsset(id);
  const runBtn = $('[data-act="run"]', root);
  const isHolder = detail.asset.holder_user_id === state.me.id;
  if (!isHolder) runBtn.classList.add("hidden");
  runBtn.onclick = () => withBusy(runBtn, async () => { const run = await api("POST", `/value/assets/${id}/assurance/run`); renderRun(root, run); await renderRuns(root, id); await renderValuation(root, id); });

  renderEvidence(root, detail.evidence);
  setupEvidenceForm(root, id, isHolder);
  await renderValuation(root, id);
  if (full) { await renderRuns(root, id, true); } else { $('[data-part="loop-card"]', root).classList.add("hidden"); }
  if (isHolder) { setupMandate(root, id, detail.mandate); await setupShares(root, id); }
  else { $('[data-part="mandate-card"]', root).classList.add("hidden"); $('[data-part="share-card"]', root).classList.add("hidden"); }
}

async function renderValuation(root, id) {
  const box = $('[data-part="valuation"]', root);
  let v;
  try { v = await api("GET", `/value/assets/${id}/valuation`); }
  catch (e) { box.replaceChildren(el("p", { class: "muted" }, `Valuation not available: ${e.message}`)); return; }
  box.replaceChildren();
  const conf = el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Evidence confidence"),
    el("div", { class: "row" }, el("div", { class: "meter" }, el("i", { style: `width:${pct(v.confidence)}` })), el("strong", {}, pct(v.confidence))));
  if (!v.complete) {
    box.append(el("h3", {}, "Valuation"), conf,
      el("p", {}, "Missing evidence for: ", ...v.missing_inputs.map((k) => el("span", { class: "badge missing", style: "margin-right:4px" }, k))));
    return;
  }
  const b = v.base;
  box.append(
    el("div", { class: "top-line" },
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Evidenced value"), el("span", { class: "big" + (b.is_liability ? " neg" : "") }, money(b.value))),
      conf,
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Status"), b.is_liability ? el("span", { class: "badge liability" }, "Liability") : el("span", { class: "badge ok" }, "Holds value"))),
    el("p", { class: "breakdown" }, `Net operating income ${money(b.net_operating_income)} = gross ${money(b.gross_income)} − operating ${money(b.operating_cost)} − carbon ${money(b.carbon_cost)}`),
  );
  // Scenario bars, scaled to the largest absolute value
  const vals = [b.value, ...Object.values(v.scenarios).map((s) => s.value)];
  const maxAbs = Math.max(...vals.map(Math.abs), 1);
  const hasNeg = vals.some((x) => x < 0);
  const zero = hasNeg ? 50 : 0;
  const scale = hasNeg ? 50 : 100;
  const bar = (x) => {
    const w = (Math.abs(x) / maxAbs) * scale;
    const left = x >= 0 ? zero : zero - w;
    return el("div", { class: "bar" }, el("i", { class: x < 0 ? "neg" : "", style: `left:${left}%;width:${w}%` }), hasNeg ? el("b", { style: `left:${zero}%` }) : null);
  };
  const sc = el("div", { class: "scen" },
    el("div", { class: "scen-row" }, el("strong", {}, "Base (current evidence)"), bar(b.value), el("span", { class: "num" }, money(b.value))));
  for (const s of Object.values(v.scenarios)) {
    sc.append(el("div", { class: "scen-row" },
      el("span", {}, s.label, s.is_liability ? el("span", { class: "badge liability", style: "margin-left:6px" }, "liability") : null),
      bar(s.value),
      el("span", { class: "num" }, money(s.value), el("br"), el("span", { class: "muted small" }, s.change_pct === null ? "" : `${s.change_pct > 0 ? "+" : ""}${s.change_pct}%`))));
  }
  box.append(el("h3", { style: "margin-top:14px" }, "Stress scenarios"), sc,
    el("ul", { class: "explain" }, ...v.explanation.map((l) => el("li", {}, l))));
}

function renderEvidence(root, evidence) {
  const box = $('[data-part="evidence"]', root);
  if (!evidence.length) { box.replaceChildren(el("p", { class: "muted" }, "No evidence recorded yet.")); return; }
  const labels = state.config.inputs;
  const rows = evidence.map((e) => el("tr", {},
    el("td", {}, e.category),
    el("td", {}, labels[e.key]?.label || e.key),
    el("td", { class: "num" }, e.value ?? ""),
    el("td", {}, e.text || ""),
    el("td", {}, e.evidence_ref || ""),
    el("td", {}, el("span", { class: "badge " + (e.self_reported ? "self_reported" : "attested") }, e.self_reported ? "self-reported" : "attested"))));
  box.replaceChildren(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["Category", "Input / key", "Value", "Note", "Evidence", "Status"].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...rows))));
}

function setupEvidenceForm(root, id, isHolder) {
  const form = $('[data-part="form-evidence"]', root);
  const keySel = form.elements.key, catSel = form.elements.category;
  const inputs = state.config.inputs;
  keySel.replaceChildren(...Object.entries(inputs).map(([k, d]) => el("option", { value: k }, d.label)), el("option", { value: "__custom" }, "Other evidence (free key)…"));
  catSel.replaceChildren(...state.config.categories.map((c) => el("option", { value: c }, c)));
  const sync = () => {
    const custom = keySel.value === "__custom";
    $(".custom", form).classList.toggle("hidden", !custom);
    catSel.disabled = !custom;
    if (!custom) catSel.value = inputs[keySel.value].category;
  };
  keySel.onchange = sync; sync();
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const custom = keySel.value === "__custom";
    const body = {
      category: catSel.value,
      key: custom ? form.elements.custom_key.value.trim() : keySel.value,
      value: form.elements.value.value === "" ? null : Number(form.elements.value.value),
      text: form.elements.text.value || null,
      evidence_ref: form.elements.evidence_ref.value || null,
    };
    try { await api("POST", `/value/assets/${id}/evidence`, body); toast("Evidence recorded"); await openAsset(id); }
    catch (e) { toast(e.message, true); }
  };
  if (!isHolder) $(".muted.small", form).textContent = "You can add evidence here only as an attester, with an evidence reference.";
}

function renderRun(root, run) {
  const s = run.steps;
  const loop = $('[data-part="loop"]', root);
  const recalc = s.recalculate.complete
    ? `Base value ${money(s.recalculate.base.value)}; ${Object.keys(s.recalculate.scenarios).length} scenarios tested; confidence ${pct(run.confidence)}.`
    : `Cannot value yet: missing ${s.recalculate.missing_inputs.join(", ")}.`;
  loop.replaceChildren(
    el("li", { class: "step" }, el("b", {}, "Detect"), s.detect.summary,
      s.detect.changes.length && !s.detect.first_run ? el("ul", {}, ...s.detect.changes.map((c) => el("li", {}, `${c.label}: ${c.before ?? "–"} → ${c.after ?? "–"}`))) : null),
    el("li", { class: "step" }, el("b", {}, "Interpret"), s.interpret.summary),
    el("li", { class: "step" }, el("b", {}, "Recalculate"), recalc),
    el("li", { class: "step" }, el("b", {}, "Explain"), el("ul", {}, ...s.explain.lines.map((l) => el("li", {}, l)))),
    el("li", { class: "step" }, el("b", {}, "Act"),
      s.act.mandate.enabled ? `Within mandate: ${s.act.mandate.allowed_actions.join(", ") || "no actions allowed"}.` : "No active mandate: recommendations only."),
  );
  const acts = $('[data-part="actions"]', root);
  acts.replaceChildren(...(run.actions.length ? run.actions : [{ type: "none", message: "Nothing to act on.", taken: false, why_not: "" }]).map((a) =>
    el("div", { class: "action " + (a.taken ? "taken" : "not-taken") },
      el("strong", {}, a.type.replace(/_/g, " ")), " · ", a.message,
      a.taken ? el("span", { class: "badge ok", style: "margin-left:6px" }, "taken") : a.why_not ? el("span", { class: "muted small" }, ` (not taken: ${a.why_not})`) : null)));
}

async function renderRuns(root, id, showLatest = false) {
  const runs = await api("GET", `/value/assets/${id}/assurance/runs`);
  if (showLatest && runs[0]) renderRun(root, runs[0]);
  const box = $('[data-part="runs"]', root);
  if (!runs.length) { box.replaceChildren(el("p", { class: "muted small" }, "No runs yet.")); return; }
  box.replaceChildren(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["When", "Base value", "Confidence", "Actions"].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...runs.map((r) => el("tr", {},
      el("td", {}, new Date(r.created_at + "Z").toLocaleString()),
      el("td", { class: "num" }, money(r.base_value)),
      el("td", {}, pct(r.confidence)),
      el("td", {}, r.actions.filter((a) => a.taken).map((a) => a.type).join(", ") || "none")))))));
}

function setupMandate(root, id, m) {
  const f = $('[data-part="form-mandate"]', root).elements;
  f.enabled.checked = !!m.enabled;
  f.alert_drop_pct.value = m.alert_drop_pct;
  f.min_confidence.value = m.min_confidence;
  f.flag_liability.checked = !!m.flag_liability;
  for (const a of ["alert", "request_attestation", "request_review"]) f["act_" + a].checked = m.allowed_actions.includes(a);
  $('[data-part="form-mandate"]', root).onsubmit = async (ev) => {
    ev.preventDefault();
    const body = {
      enabled: f.enabled.checked,
      alert_drop_pct: Number(f.alert_drop_pct.value),
      min_confidence: Number(f.min_confidence.value),
      flag_liability: f.flag_liability.checked,
      allowed_actions: ["alert", "request_attestation", "request_review"].filter((a) => f["act_" + a].checked),
    };
    try { await api("PUT", `/value/assets/${id}/mandate`, body); toast(body.enabled ? "Mandate saved and active" : "Mandate saved (inactive)"); }
    catch (e) { toast(e.message, true); }
  };
}

async function setupShares(root, id) {
  const cats = $('[data-part="share-cats"]', root);
  cats.replaceChildren(...[...state.config.categories, "valuation"].map((c) =>
    el("label", { class: "check" }, el("input", { type: "checkbox", value: c }), c)));
  const form = $('[data-part="form-share"]', root);
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const categories = [...cats.querySelectorAll("input:checked")].map((i) => i.value);
    try { await api("PUT", `/value/assets/${id}/shares`, { grantee_user_id: form.elements.grantee_user_id.value.trim(), categories }); toast("Shared"); form.reset(); await listShares(root, id); }
    catch (e) { toast(e.message, true); }
  };
  await listShares(root, id);
}
async function listShares(root, id) {
  const shares = await api("GET", `/value/assets/${id}/shares`);
  $('[data-part="shares"]', root).replaceChildren(...shares.map((s) => el("div", { class: "share-row" },
    el("span", {}, el("code", {}, s.grantee_user_id.slice(0, 8) + "…"), " ", s.categories.join(", ")),
    el("button", { class: "ghost", onclick: async () => { await api("DELETE", `/value/assets/${id}/shares/${s.grantee_user_id}`); await listShares(root, id); } }, "Revoke"))));
}

boot().catch((e) => toast(e.message, true));

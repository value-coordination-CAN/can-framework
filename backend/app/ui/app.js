// WP-011 Value Assurance page. Shared helpers live in common.js.
"use strict";

const va = { assetId: null, currency: "USD" };
const cash = (v) => money(v, va.currency);

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

startSession(async () => {
  state.config = await api("GET", "/value/config");
  show("#assets");
  $("#my-id").textContent = state.me.id;
  $("#form-asset").onsubmit = onCreateAsset;
  $("#btn-export").onclick = downloadMyData;
  await loadAssets();
}).catch((e) => toast(e.message, true));

async function loadAssets(selectId) {
  const { held, shared_with_me } = await api("GET", "/value/assets");
  const list = $("#asset-list");
  list.replaceChildren();
  if (!held.length && !shared_with_me.length) list.append(el("p", { class: "muted small" }, "No assets yet."));
  for (const a of held) list.append(assetButton(a, "held"));
  for (const a of shared_with_me) list.append(assetButton(a, "shared: " + a.shared_categories.join(", ")));
  const id = selectId || va.assetId || held[0]?.id || shared_with_me[0]?.id;
  if (id) await openAsset(id);
}

function assetButton(a, tag) {
  return el("button", { class: a.id === va.assetId ? "active" : "", "data-id": a.id, onclick: () => openAsset(a.id) },
    a.name, el("span", { class: "tag" }, `${a.kind} · ${tag}`));
}

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
  va.assetId = id;
  document.querySelectorAll("#asset-list button").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  const detail = await api("GET", `/value/assets/${id}`);
  va.currency = detail.asset.currency;
  const root = el("div", { class: "stack" });
  root.append($("#tpl-asset").content.cloneNode(true));
  $("#asset-view").replaceChildren(root);

  const full = detail.access === "full";
  $('[data-f="name"]', root).textContent = detail.asset.name;
  $('[data-f="kind"]', root).textContent = detail.asset.kind;
  $('[data-f="access"]', root).textContent = full ? "you hold this asset" : `shared with you: ${detail.access.join(", ") || "nothing"}`;
  $('[data-act="refresh"]', root).onclick = () => openAsset(id);
  const runBtn = $('[data-act="run"]', root);
  const isHolder = detail.asset.holder_user_id === state.me.id;
  if (!isHolder) runBtn.classList.add("hidden");
  runBtn.onclick = () => withBusy(runBtn, async () => {
    const run = await api("POST", `/value/assets/${id}/assurance/run`);
    renderRun(root, run);
    await renderRuns(root, id);
    await renderValuation(root, id);
  });

  renderEvidence(root, detail.evidence);
  setupEvidenceForm(root, id, isHolder);
  await renderValuation(root, id);
  if (full) await renderRuns(root, id, true);
  else $('[data-part="loop-card"]', root).classList.add("hidden");
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
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Evidenced value"), el("span", { class: "big" + (b.is_liability ? " neg" : "") }, cash(b.value))),
      conf,
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Status"), b.is_liability ? el("span", { class: "badge liability" }, "Liability") : el("span", { class: "badge ok" }, "Holds value"))),
    el("p", { class: "breakdown" }, `Net operating income ${cash(b.net_operating_income)} = gross ${cash(b.gross_income)} − operating ${cash(b.operating_cost)} − carbon ${cash(b.carbon_cost)}`),
  );
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
    el("div", { class: "scen-row" }, el("strong", {}, "Base (current evidence)"), bar(b.value), el("span", { class: "num" }, cash(b.value))));
  for (const s of Object.values(v.scenarios)) {
    sc.append(el("div", { class: "scen-row" },
      el("span", {}, s.label, s.is_liability ? el("span", { class: "badge liability", style: "margin-left:6px" }, "liability") : null),
      bar(s.value),
      el("span", { class: "num" }, cash(s.value), el("br"), el("span", { class: "muted small" }, s.change_pct === null ? "" : `${s.change_pct > 0 ? "+" : ""}${s.change_pct}%`))));
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
  const recalc = s.recalculate.complete
    ? `Base value ${cash(s.recalculate.base.value)}; ${Object.keys(s.recalculate.scenarios).length} scenarios tested; confidence ${pct(run.confidence)}.`
    : `Cannot value yet: missing ${s.recalculate.missing_inputs.join(", ")}.`;
  $('[data-part="loop"]', root).replaceChildren(
    el("li", { class: "step" }, el("b", {}, "Detect"), s.detect.summary,
      s.detect.changes.length && !s.detect.first_run ? el("ul", {}, ...s.detect.changes.map((c) => el("li", {}, `${c.label}: ${c.before ?? "–"} → ${c.after ?? "–"}`))) : null),
    el("li", { class: "step" }, el("b", {}, "Interpret"), s.interpret.summary),
    el("li", { class: "step" }, el("b", {}, "Recalculate"), recalc),
    el("li", { class: "step" }, el("b", {}, "Explain"), el("ul", {}, ...s.explain.lines.map((l) => el("li", {}, l)))),
    el("li", { class: "step" }, el("b", {}, "Act"),
      s.act.mandate.enabled ? `Within mandate: ${s.act.mandate.allowed_actions.join(", ") || "no actions allowed"}.` : "No active mandate: recommendations only."),
  );
  $('[data-part="actions"]', root).replaceChildren(...(run.actions.length ? run.actions : [{ type: "none", message: "Nothing to act on.", taken: false, why_not: "" }]).map((a) =>
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
      el("td", { class: "num" }, cash(r.base_value)),
      el("td", {}, pct(r.confidence)),
      el("td", {}, r.actions.filter((a) => a.taken).map((a) => a.type).join(", ") || "none")))))));
}

function setupMandate(root, id, m) {
  const form = $('[data-part="form-mandate"]', root);
  const f = form.elements;
  f.enabled.checked = !!m.enabled;
  f.alert_drop_pct.value = m.alert_drop_pct;
  f.min_confidence.value = m.min_confidence;
  f.flag_liability.checked = !!m.flag_liability;
  for (const a of ["alert", "request_attestation", "request_review"]) f["act_" + a].checked = m.allowed_actions.includes(a);
  form.onsubmit = async (ev) => {
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
    try {
      await api("PUT", `/value/assets/${id}/shares`, { grantee_user_id: form.elements.grantee_user_id.value.trim(), categories });
      toast("Shared"); form.reset(); await listShares(root, id);
    } catch (e) { toast(e.message, true); }
  };
  await listShares(root, id);
}

async function listShares(root, id) {
  const shares = await api("GET", `/value/assets/${id}/shares`);
  $('[data-part="shares"]', root).replaceChildren(...shares.map((s) => el("div", { class: "share-row" },
    el("span", {}, el("code", {}, s.grantee_user_id.slice(0, 8) + "…"), " ", s.categories.join(", ")),
    el("button", { class: "ghost", onclick: async () => { await api("DELETE", `/value/assets/${id}/shares/${s.grantee_user_id}`); await listShares(root, id); } }, "Revoke"))));
}

// WP-010 Bridge Wallet page. Shared helpers live in common.js.
"use strict";

const bw = { projectId: null, currency: "USD", cfg: null };
const LAYER_LABEL = { fiat: "Fiat", modernised_fiat: "Modernised fiat", direct_value: "Direct value" };
// A right to use something is held or transferred, never settled for cash.
const SETTLEABLE = ["participation_unit", "claim", "credit"];
const LAYER_NOTE = {
  fiat: "money as it is today",
  modernised_fiat: "instant, tokenised or offline form",
  direct_value: "carries its own evidence and terms",
};
const SOURCE_LABEL = {
  capital: "Capital (cash)",
  participation_units: "Participation units",
  in_kind: "In kind (land, equipment, expertise, labour)",
  pre_committed_use: "Pre-committed use (future tenant, operator, off-taker)",
  community: "Community contribution (time, knowledge, care)",
};

startSession(async () => {
  bw.cfg = await api("GET", "/bridge/config");
  show("#main");
  $("#my-id").textContent = state.me.id;
  $("#btn-export").onclick = downloadMyData;
  $("#btn-refresh").onclick = () => { loadWallet(); if (bw.projectId) openProject(bw.projectId); };
  $("#form-project").onsubmit = onCreateProject;
  renderRails();
  await loadWallet();
  await loadProjects();
}).catch((e) => toast(e.message, true));

function renderRails() {
  $("#rails").replaceChildren(...bw.cfg.rails.map((r) => el("div", { class: "share-row" },
    el("span", {}, el("strong", {}, r.name), " · ", LAYER_LABEL[r.layer] || r.layer),
    r.implemented ? el("span", { class: "badge ok" }, r.default ? "in use (simulated)" : "available")
      : el("span", { class: "badge self_reported" }, "adapter to be implemented"))),
    el("p", { class: "muted small" }, bw.cfg.note));
}

// --- wallet -------------------------------------------------------------------------

async function loadWallet() {
  const w = await api("GET", "/bridge/wallet");
  $("#layers").replaceChildren(...["fiat", "modernised_fiat", "direct_value"].map((layer) => {
    const l = w.layers[layer];
    const kinds = l ? Object.entries(l.by_kind) : [];
    return el("div", { class: "layer" },
      el("b", {}, LAYER_LABEL[layer]),
      el("span", { class: "muted small" }, LAYER_NOTE[layer]),
      kinds.length
        ? el("ul", {}, ...kinds.map(([k, v]) => el("li", {}, `${k.replace(/_/g, " ")}: `, el("strong", {}, k === "cash" || k === "tokenised_deposit" ? money(v, bw.currency) : num(v)))))
        : el("p", { class: "muted small" }, "empty"));
  }));

  const box = $("#holdings");
  if (!w.holdings.length) { box.replaceChildren(el("p", { class: "muted" }, "No holdings yet. Contribute to a project, or invoice as a supplier.")); return; }
  box.replaceChildren(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["Layer", "What", "Amount", "Pledged", "Free", "Terms", "Actions"].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...w.holdings.map(holdingRow)))));
  await loadTransfers();
}

function holdingRow(h) {
  const isCash = h.kind === "cash" || h.kind === "tokenised_deposit";
  const fmt = (v) => (isCash ? money(v, h.currency || bw.currency) : num(v));
  const actions = el("div", { class: "row" });
  if (h.layer === "direct_value" && h.free > 0) {
    actions.append(el("button", { class: "ghost", onclick: () => pledge(h) }, "Pledge"));
    if (SETTLEABLE.includes(h.kind)) actions.append(el("button", { class: "ghost", onclick: () => settle(h) }, "Settle to money"));
  }
  if (h.pledged > 0) actions.append(el("button", { class: "ghost", onclick: () => releasePledges(h) }, "Release pledge"));
  return el("tr", {},
    el("td", {}, LAYER_LABEL[h.layer] || h.layer),
    el("td", {}, el("div", {}, h.kind.replace(/_/g, " ")), h.description ? el("div", { class: "muted small" }, h.description) : null),
    el("td", { class: "num" }, fmt(h.amount)),
    el("td", { class: "num" }, h.pledged ? fmt(h.pledged) : "–"),
    el("td", { class: "num" }, fmt(h.free)),
    el("td", { class: "small" }, h.terms ? Object.entries(h.terms).map(([k, v]) => `${k}: ${v}`).join("; ") : "–"),
    el("td", {}, actions));
}

async function pledge(h) {
  const amount = Number(prompt(`Pledge how much of ${num(h.free)} free? The stake is not sold; double pledging is refused.`, h.free));
  if (!amount) return;
  try { await api("POST", `/bridge/holdings/${h.id}/pledges`, { amount, note: "pledged for liquidity" }); toast("Pledged"); await loadWallet(); }
  catch (e) { toast(e.message, true); }
}

async function releasePledges(h) {
  const pledges = await api("GET", `/bridge/holdings/${h.id}/pledges`);
  const active = pledges.filter((p) => p.status === "active");
  if (!active.length) return toast("No active pledges");
  try { await api("DELETE", `/bridge/pledges/${active[0].id}`); toast("Pledge released"); await loadWallet(); }
  catch (e) { toast(e.message, true); }
}

async function settle(h) {
  const amount = Number(prompt(`Settle how many units into money? ${num(h.free)} free of pledges.`, h.free));
  if (!amount) return;
  try {
    const r = await api("POST", `/bridge/holdings/${h.id}/settle`, { amount });
    toast(`Settled ${money(r.cash, bw.currency)} (${r.settlement.rail})`);
    await loadWallet();
  } catch (e) { toast(e.message, true); }
}

async function loadTransfers() {
  const rows = await api("GET", "/bridge/transfers");
  const box = $("#transfers");
  if (!rows.length) { box.replaceChildren(el("p", { class: "muted small" }, "No transfers yet.")); return; }
  box.replaceChildren(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["When", "Direction", "From → to", "Amount", "Rail", "Reference"].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...rows.map((t) => el("tr", {},
      el("td", {}, new Date(t.created_at + "Z").toLocaleString()),
      el("td", {}, t.direction.replace(/_/g, " ")),
      el("td", {}, `${LAYER_LABEL[t.from_layer]} → ${LAYER_LABEL[t.to_layer]}`),
      el("td", { class: "num" }, money(t.amount, t.currency || bw.currency)),
      el("td", {}, t.rail),
      el("td", { class: "small" }, t.external_ref || "–")))))));
}

// --- projects -----------------------------------------------------------------------

async function onCreateProject(ev) {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    const p = await api("POST", "/bridge/projects", {
      name: f.get("name"),
      target_amount: Number(f.get("target_amount")),
      unit_value: Number(f.get("unit_value")),
      currency: (f.get("currency") || "USD").toUpperCase(),
    });
    ev.target.reset();
    toast("Project created");
    await loadProjects(p.id);
  } catch (e) { toast(e.message, true); }
}

async function loadProjects(selectId) {
  const { sponsored, participating } = await api("GET", "/bridge/projects");
  const list = $("#project-list");
  list.replaceChildren();
  if (!sponsored.length && !participating.length) list.append(el("p", { class: "muted small" }, "No projects yet."));
  for (const p of sponsored) list.append(projectButton(p, "you sponsor"));
  for (const p of participating) list.append(projectButton(p, "you take part"));
  const id = selectId || bw.projectId || sponsored[0]?.id || participating[0]?.id;
  if (id) await openProject(id);
}

function projectButton(p, tag) {
  return el("button", { class: p.id === bw.projectId ? "active" : "", "data-id": p.id, onclick: () => openProject(p.id) },
    p.name, el("span", { class: "tag" }, `${p.status} · ${tag}`));
}

async function openProject(id) {
  bw.projectId = id;
  document.querySelectorAll("#project-list button").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  const d = await api("GET", `/bridge/projects/${id}`);
  bw.currency = d.project.currency;
  const root = el("div", { class: "stack" });
  root.append($("#tpl-project").content.cloneNode(true));
  $("#project-view").replaceChildren(root);

  $('[data-f="name"]', root).textContent = d.project.name;
  $('[data-f="role"]', root).textContent = d.is_sponsor ? "you sponsor this project" : "you take part in this project";
  $('[data-f="status"]', root).textContent = d.project.status;
  $('[data-act="refresh"]', root).onclick = () => openProject(id);

  renderMix(root, d.funding_mix);
  renderContributions(root, d.contributions, d.is_sponsor, id);
  setupContributionForm(root, id);
  renderAgreements(root, d.supplier_agreements, d.is_sponsor);
  setupSupplierForm(root, id, d.is_sponsor);
}

function renderMix(root, m) {
  const box = $('[data-part="mix"]', root);
  const pctOf = (v) => (m.raised ? (100 * v) / m.raised : 0);
  const rows = Object.entries(m.by_source).filter(([, v]) => v.value > 0).map(([s, v]) =>
    el("div", { class: "scen-row" },
      el("span", {}, SOURCE_LABEL[s] || s),
      el("div", { class: "bar" }, el("i", { class: s === "capital" ? "" : "alt", style: `left:0;width:${pctOf(v.value)}%` })),
      el("span", { class: "num" }, money(v.value, m.currency), el("br"), el("span", { class: "muted small" }, `${v.pct}%`))));
  box.replaceChildren(
    el("h3", {}, "Funding mix"),
    el("div", { class: "top-line" },
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Raised"), el("span", { class: "big" }, money(m.raised, m.currency))),
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Target"), el("span", {}, money(m.target_amount, m.currency))),
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Cash needed"), el("span", {}, m.cash_share_pct === null ? "–" : `${m.cash_share_pct}%`)),
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Raised without cash"), el("span", {}, m.cash_not_needed_pct === null ? "–" : `${m.cash_not_needed_pct}%`)),
      el("div", { class: "kpi" }, el("span", { class: "lbl" }, "Contributors"), el("span", {}, m.contributors))),
    rows.length ? el("div", { class: "scen", style: "margin-top:12px" }, ...rows) : el("p", { class: "muted" }, "Nothing accepted yet."),
    el("p", { class: "muted small" }, m.note));
}

function renderContributions(root, rows, isSponsor, projectId) {
  const box = $('[data-part="contributions"]', root);
  if (!rows.length) { box.replaceChildren(el("p", { class: "muted" }, "No contributions yet.")); return; }
  box.replaceChildren(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["Source", "Description", "Offered", "Accepted", "Wants", "Status", isSponsor ? "Decide" : ""].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...rows.map((c) => el("tr", {},
      el("td", {}, SOURCE_LABEL[c.source_type] || c.source_type),
      el("td", {}, c.description, c.valuation_basis ? el("div", { class: "muted small" }, "basis: " + c.valuation_basis) : null),
      el("td", { class: "num" }, money(c.offered_value, bw.currency)),
      el("td", { class: "num" }, c.accepted_value === null ? "–" : money(c.accepted_value, bw.currency)),
      el("td", {}, c.wants),
      el("td", {}, el("span", { class: "badge " + (c.status === "accepted" ? "ok" : c.status === "rejected" ? "missing" : "self_reported") }, c.status)),
      el("td", {}, isSponsor && c.status === "proposed"
        ? el("div", { class: "row" },
            el("button", { class: "ghost", onclick: () => decide(c, true, projectId) }, "Accept"),
            el("button", { class: "ghost", onclick: () => decide(c, false, projectId) }, "Reject"))
        : "")))))));
}

async function decide(c, accept, projectId) {
  let body = { accept };
  if (accept) {
    const v = prompt(`Value this contribution (offered ${c.offered_value}). Contributors can see and contest the basis.`, c.offered_value);
    if (v === null) return;
    body = { accept: true, accepted_value: Number(v), valuation_basis: prompt("Valuation basis (evidence reference)", "independent valuation") || null };
  }
  try {
    const r = await api("POST", `/bridge/contributions/${c.id}/decision`, body);
    if (accept) toast(`Issued: ${r.issued.map((i) => `${num(i.amount)} ${i.kind.replace(/_/g, " ")}`).join(", ") || "nothing"}`);
    if (r.reviews_required?.length) console.info("Reviews a real deployment must record:", r.reviews_required);
    await openProject(projectId);
    await loadWallet();
  } catch (e) { toast(e.message, true); }
}

function setupContributionForm(root, projectId) {
  const form = $('[data-part="form-contribution"]', root);
  form.elements.source_type.replaceChildren(...bw.cfg.source_types.map((s) => el("option", { value: s }, SOURCE_LABEL[s] || s)));
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const f = form.elements;
    const terms = f.access_terms.value.trim();
    try {
      await api("POST", `/bridge/projects/${projectId}/contributions`, {
        source_type: f.source_type.value,
        description: f.description.value,
        offered_value: Number(f.offered_value.value),
        wants: f.wants.value,
        access_terms: terms ? { right: terms } : null,
      });
      form.reset();
      toast("Contribution offered");
      await openProject(projectId);
    } catch (e) { toast(e.message, true); }
  };
}

function renderAgreements(root, rows, isSponsor) {
  const box = $('[data-part="agreements"]', root);
  if (!rows.length) { box.replaceChildren(el("p", { class: "muted small" }, "No supplier agreements yet.")); return; }
  box.replaceChildren(...rows.map((a) => {
    const wrap = el("div", { class: "agreement" },
      el("div", { class: "row" },
        el("strong", {}, a.scope),
        el("span", { class: "muted small" }, `${Math.round(a.cash_share * 100)}% cash · ${Math.round(a.participation_share * 100)}% participation`),
        el("span", { class: "badge " + (a.accepted_by_supplier === "accepted" ? "ok" : a.accepted_by_supplier === "declined" ? "missing" : "self_reported") }, a.accepted_by_supplier)));
    const mine = a.supplier_user_id === state.me.id;
    if (mine && a.accepted_by_supplier === "pending") {
      wrap.append(el("div", { class: "row" },
        el("button", { class: "ghost", onclick: () => respond(a, true) }, "Accept split"),
        el("button", { class: "ghost", onclick: () => respond(a, false) }, "Decline: all cash, paid faster")));
    }
    if (mine) wrap.append(el("button", { class: "ghost", onclick: () => invoice(a) }, "Submit invoice"));
    const invoices = el("div", { "data-invoices": a.id });
    wrap.append(invoices);
    loadInvoices(a, invoices, isSponsor);
    return wrap;
  }));
}

async function respond(a, accept) {
  try { await api("POST", `/bridge/agreements/${a.id}/response`, { accept }); toast(accept ? "Split accepted" : "Declined: all cash"); await openProject(bw.projectId); }
  catch (e) { toast(e.message, true); }
}

async function invoice(a) {
  const amount = Number(prompt("Invoice amount", "100000"));
  if (!amount) return;
  const ref = prompt("Delivery evidence reference", "site survey 2026-09") || null;
  try { await api("POST", `/bridge/agreements/${a.id}/invoices`, { amount, description: "work delivered", delivery_evidence_ref: ref }); toast("Invoice submitted"); await openProject(bw.projectId); }
  catch (e) { toast(e.message, true); }
}

async function loadInvoices(a, box, isSponsor) {
  let rows = [];
  try { rows = await api("GET", `/bridge/agreements/${a.id}/invoices`); } catch { return; }
  if (!rows.length) { box.replaceChildren(el("p", { class: "muted small" }, "No invoices yet.")); return; }
  box.replaceChildren(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["Amount", "Delivery evidence", "Status", "Settlement", ""].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...rows.map((inv) => el("tr", {},
      el("td", { class: "num" }, money(inv.amount, bw.currency)),
      el("td", { class: "small" }, inv.delivery_evidence_ref || "–"),
      el("td", {}, el("span", { class: "badge " + (inv.status === "paid" ? "ok" : inv.status === "rejected" ? "missing" : "self_reported") }, inv.status)),
      el("td", { class: "small" }, inv.settlement_ref || "–"),
      el("td", {}, isSponsor && inv.status === "submitted" ? el("button", { class: "ghost", onclick: () => verify(inv) }, "Verify delivery")
        : isSponsor && inv.status === "verified" ? el("button", { class: "primary", onclick: () => pay(inv) }, "Pay") : "")))))));
}

async function verify(inv) {
  try { await api("POST", `/bridge/invoices/${inv.id}/verify`, { approve: true }); toast("Delivery verified"); await openProject(bw.projectId); }
  catch (e) { toast(e.message, true); }
}

async function pay(inv) {
  try {
    const r = await api("POST", `/bridge/invoices/${inv.id}/pay`);
    toast(`Paid ${money(r.cash_paid, bw.currency)} in cash, ${money(r.stake_value, bw.currency)} as a stake`);
    await openProject(bw.projectId);
    await loadWallet();
  } catch (e) { toast(e.message, true); }
}

function setupSupplierForm(root, projectId, isSponsor) {
  const form = $('[data-part="form-supplier"]', root);
  if (!isSponsor) { form.classList.add("hidden"); return; }
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const f = form.elements;
    try {
      await api("POST", `/bridge/projects/${projectId}/suppliers`, {
        supplier_user_id: f.supplier_user_id.value.trim(),
        scope: f.scope.value,
        cash_share: Number(f.cash_share.value),
      });
      form.reset();
      toast("Agreement offered");
      await openProject(projectId);
    } catch (e) { toast(e.message, true); }
  };
}

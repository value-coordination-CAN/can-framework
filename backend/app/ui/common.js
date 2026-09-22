// Shared UI plumbing: API calls, DID sign-in with a browser-held key, and small helpers.
// All server data is rendered with textContent, never innerHTML.
"use strict";

const state = { token: null, me: null, config: null };
const $ = (s, root = document) => root.querySelector(s);
const show = (id, on = true) => $(id) && $(id).classList.toggle("hidden", !on);

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
  if (!t) return;
  t.textContent = msg;
  t.className = "toast show" + (err ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.className = "toast"), 3600);
}

function money(v, currency = "USD") {
  if (v === null || v === undefined) return "–";
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(v); }
  catch { return Math.round(v).toLocaleString(); }
}
const num = (v) => (v === null || v === undefined ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 }));
const pct = (x) => `${Math.round(x * 100)}%`;

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

async function withBusy(btn, fn) {
  btn.disabled = true;
  try { await fn(); }
  catch (e) {
    toast(e.message, true);
    if (e.name === "NotSupportedError" && $("#signin-msg")) {
      $("#signin-msg").textContent = "This browser does not support Ed25519 keys yet. Use a recent Chrome, Edge, Firefox or Safari, or an access token.";
    }
  }
  finally { btn.disabled = false; }
}

// --- DID key held in this browser (Ed25519; private key non-extractable, in IndexedDB) ---
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function base58(bytes) {
  const digits = [0];
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
  return { kp, did: "did:key:z" + base58(new Uint8Array([0xed, 0x01, ...raw])) };
}

function setToken(token, label) {
  state.token = token;
  try { sessionStorage.setItem("can-token", token); sessionStorage.setItem("can-label", label || ""); } catch {}
}

async function didSignIn(fresh = false) {
  const { kp, did } = await getKey(fresh);
  const { challenge } = await api("GET", "/auth/did/challenge");
  const sig = await crypto.subtle.sign({ name: "Ed25519" }, kp.privateKey, new TextEncoder().encode(challenge));
  const out = await api("POST", "/auth/did/verify", { did, challenge, signature_b64url: b64url(sig) });
  setToken(out.access_token, did);
}

function renderWho() {
  const w = $("#whoami");
  if (!w) return;
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

/** Wire the sign-in and profile panels, then call onReady() once there is a profile. */
async function startSession(onReady) {
  try { state.token = sessionStorage.getItem("can-token"); } catch {}
  const proceed = async () => {
    show("#signin", false);
    try {
      state.me = await api("GET", "/identity/users/me");
    } catch (e) {
      if (e.status === 401) { state.token = null; show("#signin"); if ($("#signin-msg")) $("#signin-msg").textContent = "Session expired. Sign in again."; return; }
      if (e.status === 403) { renderWho(); show("#profile"); return; }
      throw e;
    }
    renderWho();
    show("#profile", false);
    await onReady();
  };

  $("#btn-did").onclick = () => withBusy($("#btn-did"), async () => { await didSignIn(false); await proceed(); });
  $("#btn-new-did").onclick = () => withBusy($("#btn-new-did"), async () => { await didSignIn(true); await proceed(); });
  $("#btn-token").onclick = async () => { setToken($("#token-input").value.trim(), "access token"); await proceed(); };
  $("#form-profile").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    try { await api("POST", "/identity/users", { display_name: f.get("display_name"), email: f.get("email") }); await proceed(); }
    catch (e) { $("#profile-msg").textContent = e.message; }
  };
  if (!("subtle" in crypto) && $("#signin-msg")) $("#signin-msg").textContent = "This browser has no WebCrypto; use an access token.";
  if (state.token) await proceed(); else show("#signin");
}

async function downloadMyData() {
  const data = await api("GET", "/identity/users/me/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = el("a", { href: URL.createObjectURL(blob), download: "can-my-data.json" });
  document.body.append(a); a.click(); a.remove();
}

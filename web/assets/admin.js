/* Client-side enforcement review admin.
 *
 * Two backends behind one small adapter:
 *   • SupabaseDB — real Auth + Row-Level Security. Browser holds only the public
 *     anon key; RLS lets an authenticated reviewer read the queue & flip
 *     needs_review. Active as soon as SUPABASE_URL/ANON are filled in below.
 *   • DemoDB — zero-backend, localStorage-backed. Auto-active when Supabase is
 *     not configured (or ?demo=1). Lets you test the whole UI offline. Any
 *     email/password signs in. Verify/discard persist across reloads and flow
 *     through to the public tracker on the same origin. */

// ── Configure these two values (safe to be public) ─────────────────────────
const SUPABASE_URL = "https://cqjjmednofcdjrigjaer.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNxamptZWRub2ZjZGpyaWdqYWVyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk4MTYyMzIsImV4cCI6MjEwNTM5MjIzMn0.OhVpRSjByOA7L__Ew94LxYp-xREhQjMu-LUx4zeT9Dg";   // anon/public key — RLS-protected

const DEMO = !SUPABASE_URL || !SUPABASE_ANON_KEY ||
             new URLSearchParams(location.search).has("demo");

const AUTHORITIES = [
  "Data Protection Board of India", "CERT-In", "MeitY", "Reserve Bank of India",
  "Competition Commission of India", "IRDAI", "SEBI", "High Court / Supreme Court", "Unknown",
];
const SECTIONS = [
  ["dpdpa_board", "DPDPA / DPB"], ["sectoral_regulators", "Sectoral Regulators"],
  ["cert_in_breach", "CERT-In & Breaches"], ["courts_case_law", "Courts & Case Law"],
  ["international_benchmarks", "International Benchmarks"],
];
const OUTCOMES = ["Fine Imposed", "Investigation Ongoing", "Compliance Achieved",
  "Business Ban / Restriction", "Adjudication Order Issued", "Enacted", "Consultation"];
const SECTORS = ["Fintech", "Social Media / Tech", "Healthcare", "Government", "Other"];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ══════════════════════════════════════════════════════════════════════════
//  Data adapters
// ══════════════════════════════════════════════════════════════════════════
function SupabaseDB() {
  const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  return {
    async currentUser() { return (await sb.auth.getSession()).data.session?.user || null; },
    async signIn(email, password) {
      const { data, error } = await sb.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
      return data.user;
    },
    async signOut() { await sb.auth.signOut(); },
    async queue() {
      const { data, error } = await sb.from("enforcement_actions")
        .select("*").eq("needs_review", true).order("detected_at", { ascending: false }).limit(100);
      if (error) throw new Error(error.message);
      return data;
    },
    async verify(id, patch) {
      const { error } = await sb.from("enforcement_actions").update(patch).eq("id", id);
      if (error) throw new Error(error.message);
    },
    async discard(id) {
      const { error } = await sb.from("enforcement_actions").delete().eq("id", id);
      if (error) throw new Error(error.message);
    },
    async runs() {
      const { data, error } = await sb.from("scraper_runs")
        .select("*").order("ran_at", { ascending: false }).limit(40);
      if (error) throw new Error(error.message);
      return data;
    },
    async stories(minScore = 6) {
      const { data, error } = await sb.from("stories_processed")
        .select("headline,source,score,action_taken,intent_tag,url,processed_at")
        .gte("score", minScore).order("score", { ascending: false })
        .order("processed_at", { ascending: false }).limit(100);
      if (error) throw new Error(error.message);
      return data;
    },
    async recordDecision(row) {
      const { error } = await sb.from("review_decisions").insert(row);   // feedback loop #4
      if (error) console.warn("decision log failed:", error.message);
    },
    async brief() {
      const { data } = await sb.from("intel_briefs")
        .select("*").order("created_at", { ascending: false }).limit(1);
      return (data && data[0]) || null;
    },
    async angles() {
      const { data } = await sb.from("content_angles")
        .select("*").order("score", { ascending: false }).limit(20);
      return data || [];
    },
  };
}

function DemoDB() {
  const QKEY = "demo_queue", PKEY = "demo_published";
  const read = (k, fb) => { try { return JSON.parse(localStorage.getItem(k)) ?? fb; } catch { return fb; } };
  const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
  if (localStorage.getItem(QKEY) === null) write(QKEY, window.DEMO_CANDIDATES || []);

  return {
    async currentUser() { return read("demo_user", null); },
    async signIn(email) { const u = { email: email || "demo@kensara.in" }; write("demo_user", u); return u; },
    async signOut() { localStorage.removeItem("demo_user"); },
    async queue() { return read(QKEY, []); },
    async verify(id, patch) {
      const q = read(QKEY, []);
      const idx = q.findIndex((r) => r.id === id);
      if (idx === -1) return;
      const published = { ...q[idx], ...patch };
      q.splice(idx, 1); write(QKEY, q);
      const pub = read(PKEY, []); pub.push(published); write(PKEY, pub); // → tracker overlay
    },
    async discard(id) {
      write(QKEY, read(QKEY, []).filter((r) => r.id !== id));
    },
    async runs() { return window.DEMO_RUNS || []; },
    async stories(minScore = 6) {
      return (window.DEMO_STORIES || [])
        .filter((s) => s.score >= minScore)
        .sort((a, b) => b.score - a.score);
    },
    async recordDecision(row) {
      const log = read("demo_decisions", []); log.unshift(row); write("demo_decisions", log.slice(0, 100));
    },
    async brief() { return window.DEMO_BRIEF || null; },
    async angles() { return window.DEMO_ANGLES || []; },
    reset() { ["demo_queue", "demo_published", "demo_decisions"].forEach((k) => localStorage.removeItem(k)); },
  };
}

const DB = DEMO ? DemoDB() : SupabaseDB();

// ══════════════════════════════════════════════════════════════════════════
//  Auth flow
// ══════════════════════════════════════════════════════════════════════════
async function refreshSession() {
  if (DEMO) showDemoBadge();
  try {
    const user = await DB.currentUser();
    if (user) enterDashboard(user); else showLogin();
  } catch (e) { showLogin(); }
}

function showDemoBadge() {
  const b = document.createElement("div");
  b.className = "fixed bottom-3 right-3 z-50 text-xs px-3 py-2 rounded-lg bg-amber-500/20 " +
               "text-amber-200 border border-amber-500/40";
  b.innerHTML = "DEMO MODE · local only · <button id='demoReset' class='underline'>reset data</button>";
  document.body.appendChild(b);
  $("demoReset").onclick = () => { DB.reset && DB.reset(); location.reload(); };
  const hint = $("configHint");
  if (hint) hint.textContent = "Demo mode: any email + password works. Try it.";
}

function showLogin() {
  $("loginView").classList.remove("hidden");
  $("dashView").classList.add("hidden");
  $("logoutBtn").classList.add("hidden");
  $("userEmail").textContent = "";
}

function enterDashboard(user) {
  $("loginView").classList.add("hidden");
  $("dashView").classList.remove("hidden");
  $("logoutBtn").classList.remove("hidden");
  $("userEmail").textContent = user.email + (DEMO ? " (demo)" : "");
  loadQueue();
}

$("loginBtn").onclick = async () => {
  $("loginErr").classList.add("hidden");
  try {
    const user = await DB.signIn($("email").value.trim(), $("password").value);
    enterDashboard(user);
  } catch (error) {
    $("loginErr").textContent = error.message;
    $("loginErr").classList.remove("hidden");
  }
};
$("logoutBtn").onclick = async () => { await DB.signOut(); showLogin(); };

// ══════════════════════════════════════════════════════════════════════════
//  Tabs
// ══════════════════════════════════════════════════════════════════════════
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tab-btn").forEach((b) => { b.classList.remove("bg-blue-600"); b.classList.add("bg-slate-800"); });
    btn.classList.add("bg-blue-600"); btn.classList.remove("bg-slate-800");
    const tab = btn.dataset.tab;
    ["queue", "intel", "insights", "health", "ops"].forEach((t) => $(`tab-${t}`).classList.toggle("hidden", t !== tab));
    if (tab === "health") loadHealth();
    if (tab === "intel") loadIntel();
    if (tab === "insights") loadInsights();
  };
});

// ══════════════════════════════════════════════════════════════════════════
//  Review queue
// ══════════════════════════════════════════════════════════════════════════
async function loadQueue() {
  const root = $("queueRoot");
  try {
    const data = await DB.queue();
    $("queueCount").textContent = data.length ? `(${data.length})` : "";
    $("queueEmpty").classList.toggle("hidden", data.length > 0);
    root.innerHTML = data.map(cardHtml).join("");
    data.forEach(wireCard);
  } catch (error) {
    root.innerHTML = `<div class="text-red-400 card rounded-xl p-5">${esc(error.message)}</div>`;
  }
}

function opt(list, val) {
  return list.map((o) => {
    const [v, label] = Array.isArray(o) ? o : [o, o];
    return `<option value="${esc(v)}" ${v === val ? "selected" : ""}>${esc(label)}</option>`;
  }).join("");
}

function sourcesHtml(it) {
  const list = Array.isArray(it.sources) && it.sources.length
    ? it.sources
    : (it.source_url ? [{ source: it.source_url, url: it.source_url }] : []);
  const official = it.official_source_url
    ? `<div class="mt-2"><span class="px-2 py-0.5 rounded-full text-xs bg-emerald-500/20 text-emerald-300">✓ Official source</span>
         <a href="${esc(it.official_source_url)}" target="_blank" rel="noopener" class="text-emerald-300 text-xs hover:underline ml-1">verified notice ↗</a></div>`
    : "";
  const corroboration = list.length > 1
    ? `<div class="text-xs text-slate-500 mb-1">${list.length} corroborating sources</div>` : "";
  const links = list.map((s) =>
    `<a href="${esc(s.url)}" target="_blank" rel="noopener" class="text-blue-400 text-xs hover:underline block truncate">🔗 ${esc(s.source || s.url)}</a>`
  ).join("");
  return `<div>${corroboration}${links}${official}</div>`;
}

function normSig(company, authority) {
  const c = String(company || "").toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\b(pvt|private|ltd|limited|llp|inc|corp|company|co|india|bank|technologies|solutions|services)\b/g, " ")
    .replace(/\s+/g, " ").trim();
  return [c, String(authority || "").toLowerCase().trim()].filter(Boolean).join("|") || "unknown";
}

function cardHtml(it) {
  const conf = (it.confidence || "medium").toUpperCase();
  const confColor = conf === "HIGH" ? "text-emerald-400" : conf === "LOW" ? "text-amber-400" : "text-blue-400";
  return `<div class="card rounded-xl p-5" id="card-${esc(it.id)}">
    <div class="flex items-center gap-3 mb-4 text-xs">
      <span class="px-2 py-1 rounded-full bg-amber-500/15 text-amber-300 font-semibold">Needs review</span>
      <span class="${confColor}">AI confidence: ${esc(conf)}</span>
      <span class="text-slate-500 ml-auto">${esc(it.id)}</span>
    </div>
    <div class="grid md:grid-cols-2 gap-5">
      <div class="bg-[#0b1220] rounded-lg p-4 border border-slate-800">
        <div class="text-xs uppercase text-slate-500 mb-1">Discovered evidence</div>
        <div class="text-sm text-slate-300 mb-3">${esc(it.summary || "")}</div>
        ${sourcesHtml(it)}
        <div class="text-xs text-slate-500 mt-3">Detected: ${esc((it.detected_at || "").slice(0, 10))}</div>
      </div>
      <form class="space-y-3" id="form-${esc(it.id)}">
        <div class="grid grid-cols-2 gap-3">
          <div><label class="text-xs text-slate-400">Company / entity</label>
            <input name="company" value="${esc(it.company)}" class="field w-full rounded-lg px-2.5 py-1.5 text-sm" required></div>
          <div><label class="text-xs text-slate-400">Authority</label>
            <select name="authority" class="field w-full rounded-lg px-2.5 py-1.5 text-sm">${opt(AUTHORITIES, it.authority)}</select></div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="text-xs text-slate-400">Section (tab)</label>
            <select name="section" class="field w-full rounded-lg px-2.5 py-1.5 text-sm">${opt(SECTIONS, it.section)}</select></div>
          <div><label class="text-xs text-slate-400">Sector</label>
            <select name="sector" class="field w-full rounded-lg px-2.5 py-1.5 text-sm">${opt(SECTORS, it.sector)}</select></div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="text-xs text-slate-400">Penalty amount</label>
            <input name="penalty_amount" value="${esc(it.penalty_amount)}" class="field w-full rounded-lg px-2.5 py-1.5 text-sm"></div>
          <div><label class="text-xs text-slate-400">DPDPA / IT Act provision</label>
            <input name="dpdpa_section" value="${esc(it.dpdpa_section)}" class="field w-full rounded-lg px-2.5 py-1.5 text-sm"></div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="text-xs text-slate-400">Date (YYYY-MM-DD)</label>
            <input name="date" value="${esc(it.date)}" class="field w-full rounded-lg px-2.5 py-1.5 text-sm"></div>
          <div><label class="text-xs text-slate-400">Outcome</label>
            <select name="outcome" class="field w-full rounded-lg px-2.5 py-1.5 text-sm">${opt(OUTCOMES, it.outcome)}</select></div>
        </div>
        <div><label class="text-xs text-slate-400">Violation type</label>
          <input name="violation_type" value="${esc(it.violation_type)}" class="field w-full rounded-lg px-2.5 py-1.5 text-sm"></div>
        <div><label class="text-xs text-slate-400">Executive summary (public)</label>
          <textarea name="summary" rows="3" class="field w-full rounded-lg px-2.5 py-1.5 text-sm">${esc(it.summary)}</textarea></div>
        <div class="flex justify-end gap-3 pt-1">
          <button type="button" data-act="discard" class="px-4 py-2 rounded-lg bg-red-700 hover:bg-red-600 text-sm">Discard</button>
          <button type="button" data-act="verify" class="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-sm font-medium">Verify &amp; Publish</button>
        </div>
        <p class="msg text-sm hidden"></p>
      </form>
    </div>
  </div>`;
}

function wireCard(it) {
  const form = $(`form-${it.id}`);
  const msg = form.querySelector(".msg");
  form.querySelector('[data-act="verify"]').onclick = async () => {
    const patch = Object.fromEntries(new FormData(form).entries());
    patch.needs_review = false;
    patch.verified_at = new Date().toISOString();
    patch.updated_at = new Date().toISOString();
    try {
      await DB.verify(it.id, patch);
      logDecision("verified", it, patch);              // feedback loop #4
      flash(msg, "Published ✓", false);
      setTimeout(() => removeCard(it.id), 350);
    } catch (e) { flash(msg, e.message, true); }
  };
  form.querySelector('[data-act="discard"]').onclick = async () => {
    if (!confirm("Discard this candidate permanently?")) return;
    const patch = Object.fromEntries(new FormData(form).entries());
    try {
      await DB.discard(it.id);
      logDecision("discarded", it, patch);             // feedback loop #4
      removeCard(it.id);
    } catch (e) { flash(msg, e.message, true); }
  };
}

function logDecision(decision, it, patch) {
  try {
    DB.recordDecision({
      action_id: it.id, decision,
      title: (it.summary || "").split(". Snippet:")[0].replace("AUTO-DETECTED: ", "").slice(0, 200),
      snippet: (it.summary || "").slice(0, 500),
      source_url: it.source_url || "",
      signature: normSig(patch.company || it.company, patch.authority || it.authority),
      fields: { company: patch.company, authority: patch.authority, section: patch.section },
    });
  } catch (e) { /* never block the review action on logging */ }
}

function flash(el, text, isErr) {
  el.textContent = text; el.classList.remove("hidden");
  el.classList.toggle("text-red-400", !!isErr);
  el.classList.toggle("text-emerald-400", !isErr);
}
function removeCard(id) { $(`card-${id}`)?.remove(); loadQueue(); }

// ══════════════════════════════════════════════════════════════════════════
//  Health
// ══════════════════════════════════════════════════════════════════════════
async function loadHealth() {
  const root = $("healthRoot");
  try {
    const data = await DB.runs();
    if (!data.length) { root.innerHTML = "No runs recorded yet."; return; }
    root.innerHTML = `<table class="w-full text-left">
      <thead class="text-slate-500 text-xs uppercase"><tr>
        <th class="py-2">When</th><th>Job</th><th>Source</th><th>Status</th><th>Items</th><th>Detail</th></tr></thead>
      <tbody class="divide-y divide-slate-800">${data.map((r) => {
        const c = r.status === "ok" ? "text-emerald-400" : r.status === "blocked" ? "text-amber-400" : "text-red-400";
        return `<tr><td class="py-2 text-slate-400">${esc((r.ran_at || "").replace("T", " ").slice(0, 16))}</td>
          <td>${esc(r.job)}</td><td class="text-slate-400">${esc(r.source || "—")}</td>
          <td class="${c}">${esc(r.status)}</td><td>${esc(r.items_found ?? 0)}</td>
          <td class="text-slate-500">${esc(r.detail || "")}</td></tr>`;
      }).join("")}</tbody></table>`;
  } catch (error) {
    root.innerHTML = `<span class="text-red-400">${esc(error.message)}</span>`;
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  Intelligence feed (top-scored stories)
// ══════════════════════════════════════════════════════════════════════════
let _intelRows = [];

function scoreBadge(score) {
  const s = Number(score) || 0;
  const cls = s >= 12 ? "bg-red-500/20 text-red-300"
    : s >= 8 ? "bg-amber-500/20 text-amber-300"
    : "bg-blue-500/20 text-blue-300";
  return `<span class="px-2 py-0.5 rounded-full text-xs font-semibold ${cls}">${s}</span>`;
}

const ACTION_COLOR = {
  extracted: "text-emerald-400", alerted: "text-red-300",
  scanned: "text-slate-400", suppressed: "text-slate-500",
};

function renderIntel(rows) {
  const root = $("intelRoot");
  if (!rows.length) { root.innerHTML = "No stories at this score threshold yet."; return; }
  root.innerHTML = `<table class="w-full text-left">
    <thead class="text-slate-500 text-xs uppercase"><tr>
      <th class="py-2 w-16">Score</th><th>Headline</th><th class="w-40">Source</th>
      <th class="w-28">Tag</th><th class="w-24">Action</th><th class="w-24">Seen</th></tr></thead>
    <tbody class="divide-y divide-slate-800">${rows.map((r) => `
      <tr>
        <td class="py-2.5">${scoreBadge(r.score)}</td>
        <td class="pr-3">${r.url
            ? `<a href="${esc(r.url)}" target="_blank" rel="noopener" class="text-slate-200 hover:text-blue-300 hover:underline">${esc(r.headline)}</a>`
            : esc(r.headline)}</td>
        <td class="text-slate-400">${esc(r.source)}</td>
        <td class="text-slate-400">${esc(r.intent_tag || "—")}</td>
        <td class="${ACTION_COLOR[r.action_taken] || "text-slate-400"}">${esc(r.action_taken || "")}</td>
        <td class="text-slate-500">${esc((r.processed_at || "").slice(0, 10))}</td>
      </tr>`).join("")}</tbody></table>`;
}

function applyIntelFilters() {
  const q = ($("intelSearch").value || "").toLowerCase().trim();
  const rows = q
    ? _intelRows.filter((r) => `${r.headline} ${r.source} ${r.intent_tag || ""}`.toLowerCase().includes(q))
    : _intelRows;
  renderIntel(rows);
}

async function loadIntel() {
  const root = $("intelRoot");
  const min = Number($("intelMin").value);
  try {
    _intelRows = await DB.stories(min);
    applyIntelFilters();
  } catch (error) {
    root.innerHTML = `<span class="text-red-400">${esc(error.message)}</span>`;
  }
}

$("intelMin").onchange = loadIntel;
$("intelSearch").oninput = applyIntelFilters;

// ══════════════════════════════════════════════════════════════════════════
//  Brief & Angles (#6 + #9)
// ══════════════════════════════════════════════════════════════════════════
function miniMarkdown(md) {
  // Minimal, safe markdown: escape first, then apply a few inline/block rules.
  const lines = esc(md || "").split("\n");
  let html = "", inList = false;
  const inline = (s) => s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
  for (const raw of lines) {
    const l = raw.trimEnd();
    if (/^#\s/.test(l)) { html += `<h3 class="text-base font-semibold text-slate-100 mt-1">${inline(l.replace(/^#\s/, ""))}</h3>`; }
    else if (/^##\s/.test(l)) { html += `<h4 class="font-semibold text-slate-200 mt-2">${inline(l.replace(/^##\s/, ""))}</h4>`; }
    else if (/^-\s/.test(l)) { if (!inList) { html += "<ul class='list-disc pl-5 space-y-1'>"; inList = true; } html += `<li>${inline(l.replace(/^-\s/, ""))}</li>`; }
    else { if (inList) { html += "</ul>"; inList = false; } if (l) html += `<p>${inline(l)}</p>`; }
  }
  if (inList) html += "</ul>";
  return html;
}

async function loadInsights() {
  try {
    const brief = await DB.brief();
    $("briefRoot").innerHTML = brief ? miniMarkdown(brief.markdown) : "No brief generated yet.";
    $("briefPeriod").textContent = brief ? (brief.period || "") : "";
  } catch (e) { $("briefRoot").innerHTML = `<span class="text-red-400">${esc(e.message)}</span>`; }
  try {
    const angles = await DB.angles();
    $("anglesRoot").innerHTML = angles.length ? angles.map((a) => `
      <div class="bg-[#0b1220] rounded-lg p-3 border border-slate-800">
        <div class="font-medium text-slate-100">${esc(a.angle)}</div>
        ${a.target_keyword ? `<div class="text-xs text-blue-300 mt-1">🎯 ${esc(a.target_keyword)}</div>` : ""}
        ${a.rationale ? `<div class="text-xs text-slate-400 mt-1">${esc(a.rationale)}</div>` : ""}
        ${a.headline ? `<div class="text-xs text-slate-600 mt-1 truncate">from: ${esc(a.headline)}</div>` : ""}
      </div>`).join("") : "No angles generated yet.";
  } catch (e) { $("anglesRoot").innerHTML = `<span class="text-red-400">${esc(e.message)}</span>`; }
}

// ══════════════════════════════════════════════════════════════════════════
//  Manual triggers (optional GitHub workflow_dispatch)
// ══════════════════════════════════════════════════════════════════════════
(function initOps() {
  $("ghRepo").value = localStorage.getItem("gh_repo") || "";
  $("ghToken").value = localStorage.getItem("gh_token") || "";
  const save = () => {
    localStorage.setItem("gh_repo", $("ghRepo").value.trim());
    localStorage.setItem("gh_token", $("ghToken").value.trim());
  };
  $("ghRepo").onchange = save; $("ghToken").onchange = save;
  document.querySelectorAll(".wf-btn").forEach((b) => {
    b.onclick = async () => {
      save();
      const repo = $("ghRepo").value.trim(), token = $("ghToken").value.trim(), wf = b.dataset.wf;
      if (DEMO) return flash($("opsMsg"), "Demo mode: this would dispatch " + wf + " on GitHub Actions.", false);
      if (!repo || !token) {
        window.open(`https://github.com/${repo || ""}/actions`, "_blank");
        return flash($("opsMsg"), "Opened GitHub Actions — add repo + token here to trigger inline.", false);
      }
      try {
        const res = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/${wf}/dispatches`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" },
          body: JSON.stringify({ ref: "main" }),
        });
        flash($("opsMsg"), res.status === 204 ? `Triggered ${wf}. Check the Actions tab.`
          : `GitHub returned ${res.status}. Check repo/token/workflow name.`, res.status !== 204);
      } catch (e) { flash($("opsMsg"), e.message, true); }
    };
  });
})();

refreshSession();

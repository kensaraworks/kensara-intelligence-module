/* Intelligence Hub — client-side admin.
 *
 * Two backends behind one adapter:
 *   • SupabaseDB — real Auth + Row-Level Security. The browser holds only the
 *     public anon key; RLS is what lets a signed-in reviewer read the queue and
 *     flip needs_review. Active as soon as the two values below are filled in.
 *   • DemoDB — zero-backend, localStorage. Auto-active without Supabase (or
 *     ?demo=1) so the whole UI can be exercised offline.
 */

const SUPABASE_URL = "https://cqjjmednofcdjrigjaer.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNxamptZWRub2ZjZGpyaWdqYWVyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk4MTYyMzIsImV4cCI6MjEwNTM5MjIzMn0.OhVpRSjByOA7L__Ew94LxYp-xREhQjMu-LUx4zeT9Dg";

const DEMO = !SUPABASE_URL || !SUPABASE_ANON_KEY ||
             new URLSearchParams(location.search).has("demo");

const AUTHORITIES = ["Data Protection Board of India", "CERT-In", "MeitY",
  "Reserve Bank of India", "Competition Commission of India", "IRDAI", "SEBI",
  "High Court / Supreme Court", "Unknown"];
const SECTIONS = [["dpdpa_board", "DPDPA / DPB"], ["sectoral_regulators", "Sectoral Regulators"],
  ["cert_in_breach", "CERT-In & Breaches"], ["courts_case_law", "Courts & Case Law"],
  ["international_benchmarks", "International Benchmarks"]];
const OUTCOMES = ["Fine Imposed", "Investigation Ongoing", "Compliance Achieved",
  "Business Ban / Restriction", "Adjudication Order Issued", "Enacted", "Consultation"];
const SECTORS = ["Fintech", "Social Media / Tech", "Healthcare", "Government", "Other"];

const TIERS = {
  primary_confirmed: ["✓ Primary source confirmed", "bg-emerald-500/20 text-emerald-300"],
  press_reported:    ["◐ Press reported",           "bg-amber-500/20 text-amber-300"],
  ai_detected:       ["… Under review",             "bg-slate-600/30 text-slate-400"],
};

const WORKFLOWS = [
  ["enforcement_cron.yml", "Enforcement sweep", "bg-emerald-700 hover:bg-emerald-600",
   "Full pipeline: sense → extract → verify → publish"],
  ["news_scan_cron.yml", "News poll", "bg-blue-700 hover:bg-blue-600",
   "RSS + scrape, score and alert"],
  ["competitor_cron.yml", "Competitor + brief + angles", "bg-purple-700 hover:bg-purple-600",
   "Weekly crawl, executive brief and SEO angles"],
  ["seed.yml", "Seed baseline", "bg-slate-700 hover:bg-slate-600",
   "Load the curated baseline dataset"],
  ["pages.yml", "Redeploy frontend", "bg-slate-700 hover:bg-slate-600",
   "Rebuild the static site"],
];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tierChip = (t) => {
  const [label, cls] = TIERS[t] || TIERS.ai_detected;
  return `<span class="text-xs px-2 py-0.5 rounded-full ${cls}">${esc(label)}</span>`;
};

// ══════════════════════════════════════════════════════════════════════════
//  Adapters
// ══════════════════════════════════════════════════════════════════════════
function SupabaseDB() {
  const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  const table = (t) => sb.from(t);
  return {
    async currentUser() { return (await sb.auth.getSession()).data.session?.user || null; },
    async signIn(email, password) {
      const { data, error } = await sb.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
      return data.user;
    },
    async signOut() { await sb.auth.signOut(); },

    async queue() {
      const { data, error } = await table("enforcement_actions")
        .select("*").eq("needs_review", true).order("detected_at", { ascending: false }).limit(100);
      if (error) throw new Error(error.message);
      return data;
    },
    async published() {
      const { data, error } = await table("enforcement_actions")
        .select("*").eq("needs_review", false).order("date", { ascending: false }).limit(500);
      if (error) throw new Error(error.message);
      return data;
    },
    async verify(id, patch) {
      const { error } = await table("enforcement_actions").update(patch).eq("id", id);
      if (error) throw new Error(error.message);
    },
    async unpublish(id) {
      const { error } = await table("enforcement_actions")
        .update({ needs_review: true, updated_at: new Date().toISOString() }).eq("id", id);
      if (error) throw new Error(error.message);
    },
    async discard(id) {
      const { error } = await table("enforcement_actions").delete().eq("id", id);
      if (error) throw new Error(error.message);
    },
    async evidence() {
      const { data } = await table("verification_evidence")
        .select("*").order("verified_at", { ascending: false }).limit(500);
      return data || [];
    },
    async entities() {
      const { data } = await table("entities").select("*").order("name").limit(500);
      return data || [];
    },
    async eventEntities() {
      const { data } = await table("event_entities").select("*").limit(2000);
      return data || [];
    },
    async runs() {
      const { data } = await table("scraper_runs")
        .select("*").order("ran_at", { ascending: false }).limit(60);
      return data || [];
    },
    async stories(minScore = 6) {
      const { data } = await table("stories_processed")
        .select("headline,source,score,action_taken,intent_tag,url,processed_at")
        .gte("score", minScore).order("score", { ascending: false }).limit(100);
      return data || [];
    },
    async recordDecision(row) {
      const { error } = await table("review_decisions").insert(row);
      if (error) console.warn("decision log failed:", error.message);
    },
    async brief() {
      const { data } = await table("intel_briefs")
        .select("*").order("created_at", { ascending: false }).limit(1);
      return (data && data[0]) || null;
    },
    async angles() {
      const { data } = await table("content_angles")
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
    async published() { return read(PKEY, []); },
    async verify(id, patch) {
      const q = read(QKEY, []); const i = q.findIndex((r) => r.id === id);
      if (i === -1) return;
      const pub = { ...q[i], ...patch }; q.splice(i, 1); write(QKEY, q);
      const p = read(PKEY, []); p.push(pub); write(PKEY, p);
    },
    async unpublish(id) {
      const p = read(PKEY, []); const i = p.findIndex((r) => r.id === id);
      if (i === -1) return;
      const row = { ...p[i], needs_review: true }; p.splice(i, 1); write(PKEY, p);
      const q = read(QKEY, []); q.unshift(row); write(QKEY, q);
    },
    async discard(id) { write(QKEY, read(QKEY, []).filter((r) => r.id !== id)); },
    async evidence() { return window.DEMO_EVIDENCE || []; },
    async entities() { return window.DEMO_ENTITIES || []; },
    async eventEntities() { return window.DEMO_EVENT_LINKS || []; },
    async runs() { return window.DEMO_RUNS || []; },
    async stories(min = 6) {
      return (window.DEMO_STORIES || []).filter((s) => s.score >= min)
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
let EVIDENCE = {};      // action_id -> evidence row

// ══════════════════════════════════════════════════════════════════════════
//  Auth
// ══════════════════════════════════════════════════════════════════════════
async function refreshSession() {
  if (DEMO) showDemoBadge();
  try {
    const user = await DB.currentUser();
    if (user) enterDashboard(user); else showLogin();
  } catch { showLogin(); }
}
function showDemoBadge() {
  const b = document.createElement("div");
  b.className = "fixed bottom-3 right-3 z-50 text-xs px-3 py-2 rounded-lg bg-amber-500/20 " +
                "text-amber-200 border border-amber-500/40";
  b.innerHTML = "DEMO MODE · local only · <button id='demoReset' class='underline'>reset data</button>";
  document.body.appendChild(b);
  $("demoReset").onclick = () => { DB.reset && DB.reset(); location.reload(); };
  const hint = $("configHint");
  if (hint) hint.textContent = "Demo mode: any email + password works.";
}
function showLogin() {
  $("loginView").classList.remove("hidden");
  $("dashView").classList.add("hidden");
  $("logoutBtn").classList.add("hidden");
  $("userEmail").textContent = "";
}
async function enterDashboard(user) {
  $("loginView").classList.add("hidden");
  $("dashView").classList.remove("hidden");
  $("logoutBtn").classList.remove("hidden");
  $("userEmail").textContent = user.email + (DEMO ? " (demo)" : "");
  try {
    const ev = await DB.evidence();
    EVIDENCE = Object.fromEntries(ev.map((e) => [e.action_id, e]));
  } catch { EVIDENCE = {}; }
  renderHub(); loadQueue();
}
$("loginBtn").onclick = async () => {
  $("loginErr").classList.add("hidden");
  try { enterDashboard(await DB.signIn($("email").value.trim(), $("password").value)); }
  catch (e) { $("loginErr").textContent = e.message; $("loginErr").classList.remove("hidden"); }
};
$("logoutBtn").onclick = async () => { await DB.signOut(); showLogin(); };

// ══════════════════════════════════════════════════════════════════════════
//  Tabs
// ══════════════════════════════════════════════════════════════════════════
const TABS = ["hub", "queue", "published", "intel", "graph", "insights", "pipeline"];
const LOADERS = { hub: renderHub, queue: loadQueue, published: loadPublished,
                  intel: loadIntel, graph: loadGraph, insights: loadInsights,
                  pipeline: loadPipeline };

function showTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("bg-blue-600", on);
    b.classList.toggle("bg-slate-800", !on);
  });
  TABS.forEach((t) => $(`tab-${t}`).classList.toggle("hidden", t !== name));
  (LOADERS[name] || (() => {}))();
}
document.querySelectorAll(".tab-btn").forEach((b) => { b.onclick = () => showTab(b.dataset.tab); });
document.addEventListener("click", (e) => {
  const go = e.target.closest?.("[data-goto]");
  if (go) showTab(go.dataset.goto);
});

// ══════════════════════════════════════════════════════════════════════════
//  Hub
// ══════════════════════════════════════════════════════════════════════════
function statCard(value, label, note, colour) {
  return `<div class="card rounded-xl p-4">
    <div class="text-2xl font-bold ${colour}">${value}</div>
    <div class="text-sm text-slate-200 mt-1">${esc(label)}</div>
    <div class="text-xs text-slate-500 mt-1">${esc(note)}</div>
  </div>`;
}

async function renderHub() {
  let queue = [], pub = [], runs = [], ents = [];
  try { [queue, pub, runs, ents] = await Promise.all(
    [DB.queue(), DB.published(), DB.runs(), DB.entities()]); } catch {}

  const tiers = pub.reduce((a, r) => {
    const t = r.trust_tier || "ai_detected"; a[t] = (a[t] || 0) + 1; return a; }, {});
  const confirmed = tiers.primary_confirmed || 0;
  const lastRun = runs[0];

  $("hubStats").innerHTML =
    statCard(queue.length, "Awaiting review", "auto-detected candidates",
             queue.length ? "text-amber-400" : "text-slate-400") +
    statCard(pub.length, "Published", "live on the tracker", "text-emerald-400") +
    statCard(confirmed, "Primary confirmed", "backed by an official document", "text-blue-300") +
    statCard(ents.length, "Entities", "resolved in the knowledge graph", "text-purple-300") +
    statCard(lastRun ? timeAgo(lastRun.ran_at) : "—", "Last pipeline run",
             lastRun ? esc(lastRun.job) : "no runs recorded", "text-slate-200");

  // Attention list: what a reviewer should act on, highest value first.
  const attention = [];
  if (queue.length) {
    const grounded = queue.filter((q) => q.trust_tier === "primary_confirmed").length;
    attention.push([`${queue.length} candidate${queue.length === 1 ? "" : "s"} awaiting review`,
      grounded ? `${grounded} already backed by an official document — quickest to clear`
               : "none are primary-confirmed yet", "queue"]);
  }
  const unverified = pub.filter((p) => (p.trust_tier || "") !== "primary_confirmed").length;
  if (unverified) {
    attention.push([`${unverified} published entr${unverified === 1 ? "y is" : "ies are"} press-reported only`,
      "attaching a primary source is what makes an entry citable", "published"]);
  }
  const dark = runs.filter((r) => r.status !== "ok").slice(0, 3);
  if (dark.length) {
    attention.push([`${dark.length} source${dark.length === 1 ? "" : "s"} reported a problem`,
      dark.map((d) => d.source || d.job).join(", "), "pipeline"]);
  }
  $("hubAttention").innerHTML = attention.length ? attention.map(([t, s, go]) => `
    <button data-goto="${go}" class="w-full text-left bg-[#0b1220] border border-slate-800 rounded-lg p-3 hover:border-blue-600">
      <div class="text-slate-100">${esc(t)}</div>
      <div class="text-xs text-slate-500 mt-0.5">${esc(s)}</div>
    </button>`).join("")
    : `<div class="text-slate-500">Nothing needs attention. The queue is clear.</div>`;

  $("hubRuns").innerHTML = runs.slice(0, 8).map((r) => `
    <div class="flex items-center justify-between gap-2">
      <span class="text-slate-300 truncate">${esc(r.job)}${r.source ? " · " + esc(r.source) : ""}</span>
      <span class="${r.status === "ok" ? "text-emerald-400" : "text-amber-400"} whitespace-nowrap">${esc(r.status)} · ${timeAgo(r.ran_at)}</span>
    </div>`).join("") || `<div class="text-slate-500">No runs recorded yet.</div>`;

  const total = pub.length || 1;
  $("hubTiers").innerHTML = ["primary_confirmed", "press_reported", "ai_detected"].map((t) => {
    const n = tiers[t] || 0, pct = Math.round((n / total) * 100);
    const bar = t === "primary_confirmed" ? "bg-emerald-500"
      : t === "press_reported" ? "bg-amber-500" : "bg-slate-600";
    return `<div>
      <div class="flex justify-between text-xs mb-1">
        <span>${tierChip(t)}</span><span class="text-slate-400 mono">${n} · ${pct}%</span>
      </div>
      <div class="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div class="h-full ${bar} rounded-full" style="width:${pct}%"></div>
      </div></div>`;
  }).join("");

  $("hubActions").innerHTML = WORKFLOWS.slice(0, 3).map(([wf, label, cls]) =>
    `<button data-wf="${wf}" class="wf-quick px-3 py-2 rounded-lg text-xs ${cls}">${esc(label)}</button>`).join("") +
    `<button data-goto="pipeline" class="px-3 py-2 rounded-lg text-xs bg-slate-800 hover:bg-slate-700">All sync options →</button>`;
  document.querySelectorAll(".wf-quick").forEach((b) => {
    b.onclick = () => dispatchWorkflow(b.dataset.wf, $("hubActionMsg"));
  });
}

function timeAgo(iso) {
  if (!iso) return "—";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(secs)) return "—";
  if (secs < 3600) return `${Math.max(1, Math.round(secs / 60))}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return `${Math.round(secs / 86400)}d ago`;
}

// ══════════════════════════════════════════════════════════════════════════
//  Review queue
// ══════════════════════════════════════════════════════════════════════════
function opt(list, val) {
  return list.map((o) => {
    const [v, label] = Array.isArray(o) ? o : [o, o];
    return `<option value="${esc(v)}" ${v === val ? "selected" : ""}>${esc(label)}</option>`;
  }).join("");
}

function sourcesHtml(it) {
  const list = Array.isArray(it.sources) && it.sources.length ? it.sources
    : (it.source_url ? [{ source: it.source_url, url: it.source_url }] : []);
  const corroboration = list.length > 1
    ? `<div class="text-xs text-slate-500 mb-1">${list.length} corroborating sources</div>` : "";
  const links = list.map((s) =>
    `<a href="${esc(s.url)}" target="_blank" rel="noopener" class="text-blue-400 text-xs hover:underline block truncate">🔗 ${esc(s.source || s.url)}</a>`).join("");
  return `<div>${corroboration}${links}</div>`;
}

function evidenceHtml(it) {
  const ev = EVIDENCE[it.id];
  if (!ev) {
    return `<div class="mt-3 text-xs text-slate-500 bg-[#0b1220] border border-slate-800 rounded-lg p-2">
      No verification evidence — the verifier found no official document substantiating this.</div>`;
  }
  const chk = (k, label) => `<span class="px-2 py-0.5 rounded-full ${ev[k] ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-700/40 text-slate-400"}">${label}: ${ev[k] ? "yes" : "no"}</span>`;
  return `<div class="mt-3 bg-emerald-500/5 border border-emerald-800/40 rounded-lg p-3">
    <div class="text-xs font-semibold text-emerald-300 mb-1">Verification evidence (${esc(ev.strength || "—")})</div>
    ${ev.excerpt ? `<blockquote class="text-xs text-emerald-200/90 italic border-l-2 border-emerald-700 pl-2 my-2">“${esc(ev.excerpt).slice(0, 260)}”</blockquote>` : ""}
    <div class="flex flex-wrap gap-1.5 text-xs mt-1">
      ${chk("entity_matched", "entity")}${chk("amount_matched", "amount")}${chk("date_matched", "date")}
      ${ev.independent_sources ? `<span class="px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-300">${ev.independent_sources} independent</span>` : ""}
    </div>
    <div class="text-xs mt-2 space-x-3">
      ${ev.official_url ? `<a href="${esc(ev.official_url)}" target="_blank" rel="noopener" class="text-blue-400 hover:underline">Official document ↗</a>` : ""}
      ${ev.archived_url ? `<a href="${esc(ev.archived_url)}" target="_blank" rel="noopener" class="text-emerald-400 hover:underline">Archived copy ↗</a>` : ""}
    </div>
  </div>`;
}

function cardHtml(it) {
  return `<div class="card rounded-xl p-5" id="card-${esc(it.id)}">
    <div class="flex items-center gap-3 mb-4 text-xs flex-wrap">
      <span class="px-2 py-1 rounded-full bg-amber-500/15 text-amber-300 font-semibold">Needs review</span>
      ${tierChip(it.trust_tier)}
      ${it.verification_strength ? `<span class="text-slate-500">match: ${esc(it.verification_strength)}</span>` : ""}
      <span class="text-slate-500 ml-auto">${esc(it.id)}</span>
    </div>
    <div class="grid md:grid-cols-2 gap-5">
      <div class="bg-[#0b1220] rounded-lg p-4 border border-slate-800">
        <div class="text-xs uppercase text-slate-500 mb-1">Discovered evidence</div>
        <div class="text-sm text-slate-300 mb-3">${esc(it.summary || "")}</div>
        ${sourcesHtml(it)}
        ${evidenceHtml(it)}
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
          <div><label class="text-xs text-slate-400">Legal provision</label>
            <input name="dpdpa_section" value="${esc(it.dpdpa_section)}" class="field w-full rounded-lg px-2.5 py-1.5 text-sm"></div>
        </div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="text-xs text-slate-400">Date</label>
            <input name="date" value="${esc(it.date)}" class="field w-full rounded-lg px-2.5 py-1.5 text-sm"></div>
          <div><label class="text-xs text-slate-400">Outcome</label>
            <select name="outcome" class="field w-full rounded-lg px-2.5 py-1.5 text-sm">${opt(OUTCOMES, it.outcome)}</select></div>
          <div><label class="text-xs text-slate-400">Trust tier</label>
            <select name="trust_tier" class="field w-full rounded-lg px-2.5 py-1.5 text-sm">${opt(Object.keys(TIERS), it.trust_tier || "press_reported")}</select></div>
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

async function loadQueue() {
  const root = $("queueRoot");
  try {
    const data = await DB.queue();
    $("queueCount").textContent = data.length ? `(${data.length})` : "";
    $("queueEmpty").classList.toggle("hidden", data.length > 0);
    root.innerHTML = data.map(cardHtml).join("");
    data.forEach(wireCard);
  } catch (e) {
    root.innerHTML = `<div class="card rounded-xl p-5 text-red-400">${esc(e.message)}</div>`;
  }
}

function normSig(company, authority) {
  const c = String(company || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\b(pvt|private|ltd|limited|llp|inc|corp|company|co|india|bank|technologies|solutions|services)\b/g, " ")
    .replace(/\s+/g, " ").trim();
  return [c, String(authority || "").toLowerCase().trim()].filter(Boolean).join("|") || "unknown";
}

function wireCard(it) {
  const form = $(`form-${it.id}`), msg = form.querySelector(".msg");
  form.querySelector('[data-act="verify"]').onclick = async () => {
    const patch = Object.fromEntries(new FormData(form).entries());
    patch.needs_review = false;
    patch.verified_at = new Date().toISOString();
    patch.updated_at = new Date().toISOString();
    try {
      await DB.verify(it.id, patch);
      logDecision("verified", it, patch);
      flash(msg, "Published ✓", false);
      setTimeout(() => { $(`card-${it.id}`)?.remove(); loadQueue(); }, 350);
    } catch (e) { flash(msg, e.message, true); }
  };
  form.querySelector('[data-act="discard"]').onclick = async () => {
    if (!confirm("Discard this candidate permanently?")) return;
    const patch = Object.fromEntries(new FormData(form).entries());
    try {
      await DB.discard(it.id); logDecision("discarded", it, patch);
      $(`card-${it.id}`)?.remove(); loadQueue();
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
  } catch {}
}
function flash(el, text, isErr) {
  el.textContent = text; el.classList.remove("hidden");
  el.classList.toggle("text-red-400", !!isErr);
  el.classList.toggle("text-emerald-400", !isErr);
}

// ══════════════════════════════════════════════════════════════════════════
//  Published
// ══════════════════════════════════════════════════════════════════════════
let PUBLISHED = [];
async function loadPublished() {
  try { PUBLISHED = await DB.published(); } catch (e) {
    $("publishedTable").innerHTML = `<span class="text-red-400">${esc(e.message)}</span>`; return;
  }
  renderPublished();
}
function renderPublished() {
  const q = ($("pubSearch").value || "").toLowerCase().trim();
  const rows = PUBLISHED.filter((r) => !q ||
    `${r.company} ${r.authority} ${r.sector}`.toLowerCase().includes(q));
  $("publishedTable").innerHTML = rows.length ? `<table class="w-full text-left">
    <thead class="text-slate-500 text-xs uppercase"><tr>
      <th class="pb-2 pr-3 w-24">Date</th><th class="pb-2 pr-3">Company</th>
      <th class="pb-2 pr-3 w-44">Authority</th><th class="pb-2 pr-3 w-28">Penalty</th>
      <th class="pb-2 pr-3 w-44">Provenance</th><th class="pb-2 w-24"></th></tr></thead>
    <tbody>${rows.map((r) => `
      <tr class="border-t border-slate-800">
        <td class="py-2 pr-3 text-slate-500 text-xs">${esc(r.date)}</td>
        <td class="py-2 pr-3 text-slate-200">${esc(r.company)}</td>
        <td class="py-2 pr-3 text-slate-400 text-xs">${esc(r.authority)}</td>
        <td class="py-2 pr-3 text-slate-300 text-xs">${esc(r.penalty_amount || "—")}</td>
        <td class="py-2 pr-3">${tierChip(r.trust_tier)}</td>
        <td class="py-2 text-right">
          <button data-unpub="${esc(r.id)}" class="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-red-700">Unpublish</button>
        </td></tr>`).join("")}</tbody></table>`
    : `<div class="text-slate-500">No published cases${q ? " match that search" : " yet"}.</div>`;

  document.querySelectorAll("[data-unpub]").forEach((b) => {
    b.onclick = async () => {
      if (!confirm("Unpublish? It returns to the review queue and leaves the public tracker.")) return;
      try { await DB.unpublish(b.dataset.unpub); loadPublished(); renderHub(); }
      catch (e) { alert(e.message); }
    };
  });
}

// ══════════════════════════════════════════════════════════════════════════
//  Intelligence feed
// ══════════════════════════════════════════════════════════════════════════
let INTEL = [];
const ACTION_COLOR = { extracted: "text-emerald-400", alerted: "text-red-300",
  scanned: "text-slate-400", suppressed: "text-slate-500" };

function scoreBadge(s) {
  const n = Number(s) || 0;
  const cls = n >= 12 ? "bg-red-500/20 text-red-300"
    : n >= 8 ? "bg-amber-500/20 text-amber-300" : "bg-blue-500/20 text-blue-300";
  return `<span class="px-2 py-0.5 rounded-full text-xs font-semibold ${cls}">${n}</span>`;
}
async function loadIntel() {
  try { INTEL = await DB.stories(Number($("intelMin").value)); }
  catch (e) { $("intelRoot").innerHTML = `<span class="text-red-400">${esc(e.message)}</span>`; return; }
  renderIntel();
}
function renderIntel() {
  const q = ($("intelSearch").value || "").toLowerCase().trim();
  const rows = q ? INTEL.filter((r) => `${r.headline} ${r.source}`.toLowerCase().includes(q)) : INTEL;
  $("intelRoot").innerHTML = rows.length ? `<table class="w-full text-left">
    <thead class="text-slate-500 text-xs uppercase"><tr>
      <th class="py-2 w-16">Score</th><th>Headline</th><th class="w-40">Source</th>
      <th class="w-24">Action</th><th class="w-24">Seen</th></tr></thead>
    <tbody class="divide-y divide-slate-800">${rows.map((r) => `
      <tr><td class="py-2.5">${scoreBadge(r.score)}</td>
        <td class="pr-3">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener" class="text-slate-200 hover:text-blue-300 hover:underline">${esc(r.headline)}</a>` : esc(r.headline)}</td>
        <td class="text-slate-400 text-xs">${esc(r.source)}</td>
        <td class="${ACTION_COLOR[r.action_taken] || "text-slate-400"} text-xs">${esc(r.action_taken || "")}</td>
        <td class="text-slate-500 text-xs">${esc((r.processed_at || "").slice(0, 10))}</td></tr>`).join("")}
    </tbody></table>` : `<div class="text-slate-500">No stories at this threshold.</div>`;
}

// ══════════════════════════════════════════════════════════════════════════
//  Knowledge graph
// ══════════════════════════════════════════════════════════════════════════
let ENTITIES = [], EVENT_LINKS = [];
async function loadGraph() {
  try { [ENTITIES, EVENT_LINKS] = await Promise.all([DB.entities(), DB.eventEntities()]); }
  catch (e) { $("graphRoot").innerHTML = `<span class="text-red-400">${esc(e.message)}</span>`; return; }
  renderGraph();
}
function renderGraph() {
  const type = $("graphType").value;
  const counts = EVENT_LINKS.reduce((a, l) => { a[l.entity_key] = (a[l.entity_key] || 0) + 1; return a; }, {});
  const rows = ENTITIES.filter((e) => !type || e.entity_type === type)
    .sort((a, b) => (counts[b.key] || 0) - (counts[a.key] || 0));
  $("graphRoot").innerHTML = rows.length ? `<table class="w-full text-left">
    <thead class="text-slate-500 text-xs uppercase"><tr>
      <th class="pb-2 pr-3">Entity</th><th class="pb-2 pr-3 w-28">Type</th>
      <th class="pb-2 pr-3 w-20">Cases</th><th class="pb-2 pr-3">Also reported as</th>
      <th class="pb-2 w-24"></th></tr></thead>
    <tbody>${rows.map((e) => {
      const aliases = Array.isArray(e.aliases) ? e.aliases : [];
      return `<tr class="border-t border-slate-800">
        <td class="py-2 pr-3 text-slate-200">${esc(e.name)}</td>
        <td class="py-2 pr-3 text-slate-500 text-xs">${esc(e.entity_type)}</td>
        <td class="py-2 pr-3 mono text-xs text-slate-300">${counts[e.key] || 0}</td>
        <td class="py-2 pr-3 text-slate-500 text-xs">${aliases.length ? esc(aliases.join(", ")) : "—"}</td>
        <td class="py-2 text-right"><a href="/entity/${esc(e.slug)}" target="_blank" class="text-xs text-blue-400 hover:underline">page ↗</a></td>
      </tr>`; }).join("")}</tbody></table>`
    : `<div class="text-slate-500">No entities yet — run the pipeline to build the graph.</div>`;
}

// ══════════════════════════════════════════════════════════════════════════
//  Brief & angles
// ══════════════════════════════════════════════════════════════════════════
function miniMarkdown(md) {
  const lines = esc(md || "").split("\n");
  let html = "", inList = false;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>");
  for (const raw of lines) {
    const l = raw.trimEnd();
    if (/^#\s/.test(l)) html += `<h3 class="text-base font-semibold text-slate-100 mt-1">${inline(l.replace(/^#\s/, ""))}</h3>`;
    else if (/^##\s/.test(l)) html += `<h4 class="font-semibold text-slate-200 mt-2">${inline(l.replace(/^##\s/, ""))}</h4>`;
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
    $("briefPeriod").textContent = brief?.period || "";
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
//  Pipeline & sync
// ══════════════════════════════════════════════════════════════════════════
const ghRepo = () => $("ghRepo").value.trim();
const ghToken = () => $("ghToken").value.trim();
function saveGh() {
  localStorage.setItem("gh_repo", ghRepo());
  localStorage.setItem("gh_token", ghToken());
}

async function dispatchWorkflow(wf, msgEl) {
  saveGh();
  if (DEMO) return flash(msgEl, `Demo mode: this would dispatch ${wf}.`, false);
  if (!ghRepo() || !ghToken()) {
    showTab("pipeline");
    return flash(msgEl, "Add your repo and a GitHub token under Pipeline & Sync first.", true);
  }
  flash(msgEl, `Dispatching ${wf}…`, false);
  try {
    const res = await fetch(
      `https://api.github.com/repos/${ghRepo()}/actions/workflows/${wf}/dispatches`, {
        method: "POST",
        headers: { Authorization: `Bearer ${ghToken()}`, Accept: "application/vnd.github+json" },
        body: JSON.stringify({ ref: "main" }),
      });
    if (res.status === 204) {
      flash(msgEl, `Triggered ${wf}. It appears below within a few seconds.`, false);
      setTimeout(loadWorkflowRuns, 4000);
    } else {
      flash(msgEl, `GitHub returned ${res.status} — check the repo, token scope and workflow name.`, true);
    }
  } catch (e) { flash(msgEl, e.message, true); }
}

async function loadWorkflowRuns() {
  const box = $("wfRuns");
  if (DEMO) { box.innerHTML = `<div class="text-slate-500">Demo mode — live run status needs a GitHub token.</div>`; return; }
  if (!ghRepo() || !ghToken()) return;
  try {
    const res = await fetch(`https://api.github.com/repos/${ghRepo()}/actions/runs?per_page=10`, {
      headers: { Authorization: `Bearer ${ghToken()}`, Accept: "application/vnd.github+json" } });
    if (!res.ok) { box.innerHTML = `<span class="text-amber-400">GitHub returned ${res.status}.</span>`; return; }
    const runs = (await res.json()).workflow_runs || [];
    const colour = (r) => r.status !== "completed" ? "text-blue-300"
      : r.conclusion === "success" ? "text-emerald-400" : "text-red-400";
    box.innerHTML = runs.length ? `<table class="w-full text-left">
      <thead class="text-slate-500 text-xs uppercase"><tr>
        <th class="pb-2 pr-3">Workflow</th><th class="pb-2 pr-3 w-28">Status</th>
        <th class="pb-2 pr-3 w-24">When</th><th class="pb-2 w-16"></th></tr></thead>
      <tbody>${runs.map((r) => `<tr class="border-t border-slate-800">
        <td class="py-2 pr-3 text-slate-200">${esc(r.name)}</td>
        <td class="py-2 pr-3 text-xs ${colour(r)}">${esc(r.status === "completed" ? r.conclusion : r.status)}</td>
        <td class="py-2 pr-3 text-slate-500 text-xs">${timeAgo(r.created_at)}</td>
        <td class="py-2 text-right"><a href="${esc(r.html_url)}" target="_blank" class="text-xs text-blue-400 hover:underline">logs ↗</a></td>
      </tr>`).join("")}</tbody></table>` : `<div class="text-slate-500">No runs yet.</div>`;
  } catch (e) { box.innerHTML = `<span class="text-red-400">${esc(e.message)}</span>`; }
}

async function loadPipeline() {
  $("ghRepo").value = localStorage.getItem("gh_repo") || $("ghRepo").value;
  $("ghToken").value = localStorage.getItem("gh_token") || "";
  $("wfButtons").innerHTML = WORKFLOWS.map(([wf, label, cls, desc]) =>
    `<button data-wf="${wf}" title="${esc(desc)}" class="wf-btn px-4 py-2 rounded-lg text-sm ${cls}">${esc(label)}</button>`).join("");
  document.querySelectorAll(".wf-btn").forEach((b) => {
    b.onclick = () => dispatchWorkflow(b.dataset.wf, $("opsMsg"));
  });
  loadWorkflowRuns();

  try {
    const runs = await DB.runs();
    const colour = (s) => s === "ok" ? "text-emerald-400" : s === "blocked" ? "text-amber-400" : "text-red-400";
    $("healthRoot").innerHTML = runs.length ? `<table class="w-full text-left">
      <thead class="text-slate-500 text-xs uppercase"><tr>
        <th class="pb-2 pr-3 w-32">When</th><th class="pb-2 pr-3 w-28">Job</th>
        <th class="pb-2 pr-3 w-40">Source</th><th class="pb-2 pr-3 w-20">Status</th>
        <th class="pb-2 pr-3 w-16">Items</th><th class="pb-2">Detail</th></tr></thead>
      <tbody>${runs.map((r) => `<tr class="border-t border-slate-800">
        <td class="py-2 pr-3 text-slate-500 text-xs">${timeAgo(r.ran_at)}</td>
        <td class="py-2 pr-3 text-slate-300 text-xs">${esc(r.job)}</td>
        <td class="py-2 pr-3 text-slate-500 text-xs">${esc(r.source || "—")}</td>
        <td class="py-2 pr-3 text-xs ${colour(r.status)}">${esc(r.status)}</td>
        <td class="py-2 pr-3 mono text-xs text-slate-300">${r.items_found ?? 0}</td>
        <td class="py-2 text-slate-500 text-xs">${esc(r.detail || "")}</td>
      </tr>`).join("")}</tbody></table>` : `<div class="text-slate-500">No runs recorded yet.</div>`;
  } catch (e) { $("healthRoot").innerHTML = `<span class="text-red-400">${esc(e.message)}</span>`; }
}

// ── wiring ────────────────────────────────────────────────────────────────
$("intelMin").onchange = loadIntel;
$("intelSearch").oninput = renderIntel;
$("pubSearch").oninput = renderPublished;
$("graphType").onchange = renderGraph;
$("refreshRuns").onclick = loadWorkflowRuns;
$("ghRepo").onchange = saveGh;
$("ghToken").onchange = saveGh;

refreshSession();

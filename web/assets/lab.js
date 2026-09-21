/* Pipeline Lab — renders the instrumented trace produced by
 * `python -m src.main trace`. Static, no server, no secrets. */

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (id) => document.getElementById(id);

let TRACE = null;

const REASON_LABEL = {
  no_topic_anchor: "No topic anchor — nothing about data protection in the text",
  corporate_noise: "Corporate/business news (funding, results, launches)",
  off_topic_regulatory: "Routine regulatory business (CRR, KYC, FEMA…)",
  noise_pattern: "Marketing / listicle / events noise",
  empty_title: "Empty title",
  "already ingested in a previous run": "Seen in an earlier run",
};

const STAGE_STYLE = {
  candidate: "bg-emerald-500/20 text-emerald-300",
  passed_prefilter: "bg-blue-500/20 text-blue-300",
  dropped: "bg-slate-600/30 text-slate-400",
  sensed: "bg-slate-600/30 text-slate-400",
};

// ── Tabs ──────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.remove("bg-blue-600"); b.classList.add("bg-slate-800");
    });
    btn.classList.add("bg-blue-600"); btn.classList.remove("bg-slate-800");
    ["funnel", "items", "rejected", "sources", "crawler", "config"].forEach((t) =>
      $(`tab-${t}`).classList.toggle("hidden", t !== btn.dataset.tab));
  };
});

// ── Funnel ────────────────────────────────────────────────────────────────
function renderFunnel() {
  const f = TRACE.funnel;
  const first = f[0]?.count || 1;
  $("funnelCards").innerHTML = f.map((s, i) => {
    const pct = Math.round((s.count / first) * 100);
    const dropped = i > 0 ? f[i - 1].count - s.count : 0;
    return `<div class="card rounded-xl p-4">
      <div class="text-2xl font-bold ${i === f.length - 1 ? "text-emerald-400" : "text-blue-300"}">${s.count.toLocaleString()}</div>
      <div class="text-sm text-slate-200 mt-1">${esc(s.stage)}</div>
      <div class="text-xs text-slate-500 mt-1">${esc(s.note)}</div>
      <div class="h-1.5 bg-slate-800 rounded-full mt-3 overflow-hidden">
        <div class="h-full ${i === f.length - 1 ? "bg-emerald-500" : "bg-blue-500"} rounded-full" style="width:${pct}%"></div>
      </div>
      ${dropped > 0 ? `<div class="text-xs text-amber-400/80 mt-2">−${dropped.toLocaleString()} dropped here</div>` : ""}
    </div>`;
  }).join("");

  const rej = Object.entries(TRACE.rejections || {}).sort((a, b) => b[1] - a[1]);
  const max = rej.length ? rej[0][1] : 1;
  $("rejectionBars").innerHTML = rej.length ? rej.map(([reason, n]) => `
    <div>
      <div class="flex justify-between text-sm mb-1">
        <span class="text-slate-200">${esc(REASON_LABEL[reason] || reason)}</span>
        <span class="text-slate-400 mono">${n.toLocaleString()}</span>
      </div>
      <div class="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div class="h-full bg-amber-500 rounded-full" style="width:${Math.round((n / max) * 100)}%"></div>
      </div>
    </div>`).join("") : `<div class="text-slate-500 text-sm">Nothing rejected.</div>`;

  const cands = TRACE.items.filter((i) => i.stage === "candidate");
  $("candidateList").innerHTML = cands.map((i, idx) => `
    <div class="bg-[#0b1220] border border-slate-800 rounded-lg p-3 cursor-pointer hover:border-blue-600"
         onclick="openDrawer(${TRACE.items.indexOf(i)})">
      <div class="flex items-start gap-3">
        <span class="text-xs mono text-emerald-400 w-8 shrink-0">${i.score ?? "—"}</span>
        <div class="min-w-0">
          <div class="text-sm text-slate-100 truncate">${esc(i.title)}</div>
          <div class="text-xs text-slate-500 mt-0.5">${esc(i.source)}${i.is_primary_source ? " · primary source" : ""}</div>
        </div>
      </div>
    </div>`).join("") || `<div class="text-slate-500 text-sm">No candidates this run.</div>`;
}

// ── Items table ───────────────────────────────────────────────────────────
function itemRow(i, idx) {
  const style = STAGE_STYLE[i.stage] || STAGE_STYLE.dropped;
  const label = i.stage === "candidate" ? "candidate"
    : i.stage === "passed_prefilter" ? "passed" : (i.exited_at || i.stage);
  return `<tr class="border-t border-slate-800 hover:bg-slate-800/40 cursor-pointer" onclick="openDrawer(${idx})">
    <td class="py-2 pr-3"><span class="px-2 py-0.5 rounded-full text-xs ${style}">${esc(label)}</span></td>
    <td class="py-2 pr-3 mono text-xs text-slate-400">${i.score ?? "—"}</td>
    <td class="py-2 pr-3 text-slate-200">${esc(i.title).slice(0, 110)}</td>
    <td class="py-2 pr-3 text-slate-500 text-xs">${esc(i.source)}</td>
    <td class="py-2 text-slate-500 text-xs">${esc(i.reason || "")}</td>
  </tr>`;
}

function renderItems() {
  const stage = $("stageFilter").value;
  const q = ($("itemSearch").value || "").toLowerCase().trim();
  const rows = TRACE.items
    .map((it, idx) => ({ it, idx }))
    .filter(({ it }) => !stage || it.stage === stage)
    .filter(({ it }) => !q || `${it.title} ${it.source}`.toLowerCase().includes(q));

  $("itemsTable").innerHTML = `<table class="w-full text-left">
    <thead class="text-slate-500 text-xs uppercase"><tr>
      <th class="pb-2 pr-3 w-28">Outcome</th><th class="pb-2 pr-3 w-12">Score</th>
      <th class="pb-2 pr-3">Title</th><th class="pb-2 pr-3 w-40">Source</th>
      <th class="pb-2 w-56">Reason</th></tr></thead>
    <tbody>${rows.slice(0, 400).map(({ it, idx }) => itemRow(it, idx)).join("")}</tbody></table>`;
  $("itemsCount").textContent =
    `Showing ${Math.min(rows.length, 400)} of ${rows.length} (trace holds ${TRACE.items.length} items)`;
}

// ── Redacted ──────────────────────────────────────────────────────────────
let activeReason = "";
function renderRejected() {
  const rejected = TRACE.items.filter((i) => i.stage === "dropped");
  const counts = {};
  rejected.forEach((i) => { const r = i.reason || "unknown"; counts[r] = (counts[r] || 0) + 1; });

  $("reasonChips").innerHTML = [["", `All (${rejected.length})`]]
    .concat(Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([r, n]) => [r, `${REASON_LABEL[r] || r} (${n})`]))
    .map(([val, label]) => `<button onclick="setReason('${esc(val).replace(/'/g, "")}')"
        class="px-3 py-1.5 rounded-lg text-xs border ${activeReason === val ? "border-amber-500 bg-amber-500/10 text-amber-300" : "border-slate-700 text-slate-400 hover:border-slate-500"}">${esc(label)}</button>`).join("");

  const shown = rejected.filter((i) => !activeReason || (i.reason || "") === activeReason);
  $("rejectedTable").innerHTML = `<table class="w-full text-left">
    <thead class="text-slate-500 text-xs uppercase"><tr>
      <th class="pb-2 pr-3 w-32">Killed at</th><th class="pb-2 pr-3">Title</th>
      <th class="pb-2 pr-3 w-40">Source</th><th class="pb-2 w-64">Rule that killed it</th></tr></thead>
    <tbody>${shown.slice(0, 400).map((i) => `
      <tr class="border-t border-slate-800 hover:bg-slate-800/40 cursor-pointer" onclick="openDrawer(${TRACE.items.indexOf(i)})">
        <td class="py-2 pr-3"><span class="px-2 py-0.5 rounded-full text-xs bg-slate-600/30 text-slate-400">${esc(i.exited_at || "—")}</span></td>
        <td class="py-2 pr-3 text-slate-300">${esc(i.title).slice(0, 100)}</td>
        <td class="py-2 pr-3 text-slate-500 text-xs">${esc(i.source)}</td>
        <td class="py-2 text-slate-400 text-xs">${esc(REASON_LABEL[i.reason] || i.reason || "")}</td>
      </tr>`).join("")}</tbody></table>`;
}
function setReason(r) { activeReason = r; renderRejected(); }

// ── Sources ───────────────────────────────────────────────────────────────
function renderSources() {
  const s = TRACE.sources;
  const color = (st) => st === "ok" ? "text-emerald-400"
    : st === "fallback" ? "text-blue-300"
    : st === "empty" ? "text-amber-400" : "text-red-400";
  $("sourcesTable").innerHTML = `<table class="w-full text-left">
    <thead class="text-slate-500 text-xs uppercase"><tr>
      <th class="pb-2 pr-3">Source</th><th class="pb-2 pr-3 w-20">Kind</th>
      <th class="pb-2 pr-3 w-14">Tier</th><th class="pb-2 pr-3 w-20">Status</th>
      <th class="pb-2 pr-3 w-16">Items</th><th class="pb-2">Detail</th></tr></thead>
    <tbody>${s.map((r) => `
      <tr class="border-t border-slate-800">
        <td class="py-2 pr-3 text-slate-200">${esc(r.source)}${r.is_primary_source ? ' <span class="text-xs text-emerald-500">◆</span>' : ""}</td>
        <td class="py-2 pr-3 text-slate-500 text-xs mono">${esc(r.kind)}</td>
        <td class="py-2 pr-3 text-slate-500 text-xs">${r.tier}</td>
        <td class="py-2 pr-3 text-xs ${color(r.status)}">${esc(r.status)}</td>
        <td class="py-2 pr-3 mono text-xs text-slate-300">${r.items}</td>
        <td class="py-2 text-slate-500 text-xs">${esc(r.detail || "")}</td>
      </tr>`).join("")}</tbody></table>`;
}

// ── Crawler view ──────────────────────────────────────────────────────────
function renderCrawler() {
  const cv = TRACE.crawler_view || {};
  $("crawlerPages").innerHTML = (cv.pages || []).map((p) => {
    const broken = p.js_dependent;
    return `<div class="bg-[#0b1220] border ${broken ? "border-red-700" : "border-slate-800"} rounded-lg p-4">
      <div class="flex items-center justify-between flex-wrap gap-2 mb-2">
        <div>
          <span class="text-slate-100 font-medium">${esc(p.label)}</span>
          <span class="mono text-xs text-slate-500 ml-2">${esc(p.path || "/")}</span>
        </div>
        <span class="text-xs px-2 py-0.5 rounded-full ${broken ? "bg-red-500/20 text-red-300" : "bg-emerald-500/20 text-emerald-300"}">
          ${broken ? "INVISIBLE to AI crawlers" : "Readable without JS"}
        </span>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
        <div><div class="text-slate-500">Case rows in HTML</div><div class="mono ${p.case_rows ? "text-emerald-400" : "text-slate-400"}">${p.case_rows}</div></div>
        <div><div class="text-slate-500">Visible text</div><div class="mono text-slate-300">${p.visible_text_chars.toLocaleString()} chars</div></div>
        <div><div class="text-slate-500">JSON-LD blocks</div><div class="mono text-slate-300">${p.jsonld_blocks}</div></div>
        <div><div class="text-slate-500">Canonical</div><div class="mono ${p.has_canonical ? "text-emerald-400" : "text-red-400"}">${p.has_canonical ? "yes" : "no"}</div></div>
      </div>
      ${p.headings?.length ? `<div class="text-xs text-slate-500 mb-1">Headings seen:</div>
        <div class="text-xs text-slate-300 mb-3">${p.headings.map((h) => esc(h.replace(/\s+/g, " ").trim()).slice(0, 70)).join(" · ")}</div>` : ""}
      <details>
        <summary class="text-xs text-blue-400 cursor-pointer">Show the raw text a bot receives</summary>
        <pre class="mono text-xs text-slate-400 whitespace-pre-wrap mt-2 bg-black/30 p-3 rounded">${esc(p.text_preview)}…</pre>
      </details>
    </div>`;
  }).join("") || `<div class="text-slate-500 text-sm">No rendered pages found — run <code class="mono">python -m src.main render</code>.</div>`;

  const r = cv.robots || {};
  $("robotsBox").innerHTML = `
    <div class="mb-3"><div class="text-slate-500 text-xs mb-1">AI crawlers explicitly allowed</div>
      <div class="flex flex-wrap gap-2">${(r.ai_crawlers_allowed || []).map((a) =>
        `<span class="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 text-xs mono">${esc(a)}</span>`).join("") || '<span class="text-red-400 text-xs">none — AI crawlers are not explicitly welcomed</span>'}</div></div>
    <div class="mb-3"><div class="text-slate-500 text-xs mb-1">Disallowed paths</div>
      <div class="text-xs mono text-slate-300">${(r.disallowed || []).map(esc).join(", ") || "—"}</div></div>
    <div class="text-xs text-slate-400">sitemap declared: <span class="${r.has_sitemap ? "text-emerald-400" : "text-red-400"}">${r.has_sitemap ? "yes" : "no"}</span>
      · llms.txt: <span class="${cv.llms_txt ? "text-emerald-400" : "text-red-400"}">${cv.llms_txt ? "present" : "missing"}</span></div>`;
}

// ── Config ────────────────────────────────────────────────────────────────
function kv(obj) {
  return `<dl class="space-y-2">${Object.entries(obj).map(([k, v]) => `
    <div class="flex justify-between gap-4 border-b border-slate-800/60 pb-1">
      <dt class="text-slate-500 text-xs">${esc(k)}</dt>
      <dd class="mono text-xs text-slate-200">${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>
    </div>`).join("")}</dl>`;
}
function renderConfig() {
  $("configBox").innerHTML = kv(TRACE.config || {});
  $("registryBox").innerHTML = kv(TRACE.registry || {});
}

// ── Drawer ────────────────────────────────────────────────────────────────
function openDrawer(idx) {
  const i = TRACE.items[idx];
  if (!i) return;
  const b = i.breakdown;
  $("drawerBody").innerHTML = `
    <div class="text-xs text-slate-500 mb-1">${esc(i.source)}${i.published ? " · " + esc(i.published) : ""}</div>
    <h2 class="text-lg font-semibold text-slate-100 mb-2">${esc(i.title)}</h2>
    <a href="${esc(i.url)}" target="_blank" rel="noopener" class="text-blue-400 text-xs hover:underline break-all">${esc(i.url)}</a>
    <div class="mt-4 flex flex-wrap gap-2 text-xs">
      <span class="px-2 py-1 rounded-full ${STAGE_STYLE[i.stage] || STAGE_STYLE.dropped}">${esc(i.stage)}</span>
      ${i.exited_at ? `<span class="px-2 py-1 rounded-full bg-slate-700/40 text-slate-300">exited at: ${esc(i.exited_at)}</span>` : ""}
      ${i.is_primary_source ? '<span class="px-2 py-1 rounded-full bg-emerald-500/15 text-emerald-300">primary source</span>' : ""}
    </div>
    ${i.reason ? `<div class="mt-3 text-sm text-amber-300/90">${esc(REASON_LABEL[i.reason] || i.reason)}</div>` : ""}
    ${i.summary ? `<p class="text-sm text-slate-400 mt-4">${esc(i.summary)}</p>` : ""}
    ${b ? `<div class="mt-5">
      <h3 class="text-sm font-semibold text-slate-200 mb-2">12-signal score breakdown</h3>
      <div class="space-y-1">${b.signals.map((s) => `
        <div class="flex justify-between text-xs bg-[#0b1220] border border-slate-800 rounded px-2 py-1.5">
          <span class="text-slate-300">${esc(s.signal)}${s.detail ? ` <span class="text-slate-600">${esc(s.detail).slice(0, 40)}</span>` : ""}</span>
          <span class="mono text-emerald-400">+${s.points}</span>
        </div>`).join("")}</div>
      <div class="mt-3 text-xs text-slate-400 space-y-1">
        <div>base ${b.base} → capped at 20: <span class="mono text-slate-200">${b.capped_base}</span></div>
        <div>recency (${b.days_old}d old): <span class="mono ${b.recency_delta >= 0 ? "text-emerald-400" : "text-red-400"}">${b.recency_delta >= 0 ? "+" : ""}${b.recency_delta}</span></div>
        <div class="text-slate-200">final: <span class="mono text-emerald-400 text-sm">${b.final}</span></div>
      </div></div>` : ""}`;
  $("drawer").classList.remove("hidden");
}
function closeDrawer() { $("drawer").classList.add("hidden"); }

// ── Boot ──────────────────────────────────────────────────────────────────
(async function boot() {
  try {
    const res = await fetch("data/pipeline-trace.json", { cache: "no-cache" });
    if (!res.ok) throw new Error("no trace");
    TRACE = await res.json();
  } catch {
    $("noTrace").classList.remove("hidden");
    return;
  }
  $("lab").classList.remove("hidden");
  const when = new Date(TRACE.generated_at);
  $("traceMeta").textContent =
    `trace ${when.toLocaleString()} · ${TRACE.items.length} items · ${TRACE.sources.length} sources`;
  renderFunnel(); renderItems(); renderRejected(); renderSources(); renderCrawler(); renderConfig();
  $("stageFilter").onchange = renderItems;
  $("itemSearch").oninput = renderItems;
})();

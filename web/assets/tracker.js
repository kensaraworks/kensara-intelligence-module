/* DPDPA Enforcement Tracker — public renderer.
 * Reads the committed static snapshot (data/enforcement.json) so the page is
 * fully $0, cacheable, and works even if Supabase is unreachable. If a Supabase
 * URL + anon key are configured below, it will additionally try a live refresh
 * from the `enforcement_public` view (RLS-guarded, read-only). */

const CONFIG = {
  // Optional live refresh. Leave blank to use the static JSON only.
  SUPABASE_URL: "",
  SUPABASE_ANON_KEY: "",
};

const SECTION_META = {
  dpdpa_board: {
    badge: "DPDPA 2023", badgeClass: "bg-purple-100 text-purple-800",
    title: "DPDPA & Data Protection Board of India",
    subtitle: "Statute, rules and Data Protection Board milestones — from MeitY, PIB, the eGazette, India Code and PRS.",
  },
  sectoral_regulators: {
    badge: "Regulators", badgeClass: "bg-emerald-100 text-emerald-800",
    title: "Sectoral Regulator Actions",
    subtitle: "Penalties and orders from RBI, SEBI, IRDAI, CCI, TRAI, DoT, UIDAI, NPCI and the CCPA — the precedent landscape for data-protection enforcement in India today.",
  },
  cert_in_breach: {
    badge: "CERT-In", badgeClass: "bg-orange-100 text-orange-800",
    title: "CERT-In & Breach Enforcement",
    subtitle: "CERT-In directions and advisories (IT Act Section 70B, 6-hour reporting mandate) plus reported Indian data breaches.",
  },
  courts_case_law: {
    badge: "Courts", badgeClass: "bg-blue-100 text-blue-800",
    title: "Courts & Case Law",
    subtitle: "Judgments and tribunal rulings from the Supreme Court, High Courts, TDSAT and IT Act Section 43A adjudications.",
  },
  international_benchmarks: {
    badge: "Global", badgeClass: "bg-slate-200 text-slate-700",
    title: "International Benchmarks — India-Relevant",
    subtitle: "Major GDPR and global DPA enforcement actions that affect Indian IT/ITES companies or subsidiaries — benchmarks for DPDPA precedent.",
  },
};
const SECTION_ORDER = ["dpdpa_board", "sectoral_regulators", "cert_in_breach", "courts_case_law", "international_benchmarks"];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function outcomeBadgeClass(outcome) {
  const o = (outcome || "").toLowerCase();
  if (o.includes("fine") || o.includes("penalty")) return "badge-fine";
  if (o.includes("ban") || o.includes("restrict")) return "badge-ban";
  if (o.includes("compliance")) return "badge-compliance";
  if (o.includes("enacted") || o.includes("rule") || o.includes("force")) return "badge-enacted";
  if (o.includes("investigation") || o.includes("ongoing") || o.includes("consultation")) return "badge-investigation";
  return "badge-other";
}

function rowHtml(a, category) {
  const primary = a.official_source_url || a.source_url;
  const count = Array.isArray(a.sources) ? a.sources.length : 0;
  const official = a.official_source_url
    ? `<span class="text-emerald-600" title="Official source verified">✓</span> ` : "";
  const more = count > 1 ? `<span class="text-gray-400 text-[10px]">+${count - 1}</span>` : "";
  const src = primary
    ? `${official}<a href="${esc(primary)}" target="_blank" rel="noopener" class="text-blue-600 hover:text-blue-800 text-xs">Link ↗</a> ${more}`
    : "—";
  return `<tr class="table-row-hover" data-category="${esc(category)}" data-sector="${esc(a.sector)}" data-violation="${esc(a.violation_type)}">
    <td class="px-4 py-3 text-gray-500 whitespace-nowrap">${esc(a.date)}</td>
    <td class="px-4 py-3 font-medium text-gray-800">${esc(a.authority)}</td>
    <td class="px-4 py-3"><div class="font-medium text-gray-900">${esc(a.company)}</div><div class="text-gray-500 text-xs mt-1">${esc(a.summary)}</div></td>
    <td class="px-4 py-3 text-xs text-gray-700">${esc(a.violation_type)}</td>
    <td class="px-4 py-3 text-gray-700">${esc(a.penalty_amount)}</td>
    <td class="px-4 py-3"><span class="${outcomeBadgeClass(a.outcome)} text-xs px-2 py-1 rounded-full font-medium">${esc(a.outcome)}</span></td>
    <td class="px-4 py-3">${src}</td>
  </tr>`;
}

function sectionHtml(sectionId, rows) {
  const m = SECTION_META[sectionId];
  const body = rows.length
    ? rows.map((a) => rowHtml(a, sectionId)).join("")
    : `<tr><td colspan="7" class="px-4 py-6 text-center text-sm text-gray-400">No verified entries yet — new leads are pending review.</td></tr>`;
  return `<div class="mb-8 section-block" data-section="${sectionId}">
    <div class="flex items-center gap-3 mb-3">
      <div class="${m.badgeClass} text-xs font-bold px-3 py-1 rounded-full">${m.badge}</div>
      <h2 class="text-lg font-semibold text-gray-900">${m.title}</h2>
      <span class="text-xs text-gray-400">(${rows.length})</span>
    </div>
    <p class="text-sm text-gray-500 mb-4">${m.subtitle}</p>
    <div class="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200"><tr>
          <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-24">Date</th>
          <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Authority</th>
          <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Company / Entity &amp; Summary</th>
          <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Violation</th>
          <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">Penalty</th>
          <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-28">Outcome</th>
          <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-16">Source</th>
        </tr></thead>
        <tbody class="divide-y divide-gray-100">${body}</tbody>
      </table>
    </div>
  </div>`;
}

function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }

function render(data) {
  const stats = data.statistics || {};
  const sc = data.sector_counts || {};
  const meta = data.metadata || {};
  setText("heroTotal", stats.total_all_sections || 0);
  setText("heroDpdpa", stats.total_dpdpa_board || 0);
  setText("statDpdpa", stats.total_dpdpa_board || 0);
  setText("statSectoral", stats.total_sectoral_regulators || 0);
  setText("statCert", stats.total_cert_in_breach || 0);
  setText("statCourts", stats.total_courts_case_law || 0);
  setText("statIntl", stats.total_international || 0);
  setText("secSocial", sc.social_tech_count || 0);
  setText("secHealth", sc.healthcare_count || 0);
  setText("secFin", sc.fintech_count || 0);
  setText("secGov", sc.gov_count || 0);
  setText("secOther", sc.other_sectors_count || 0);
  setText("lastUpdated", meta.last_updated_formatted || meta.last_updated || "—");
  setText("footUpdated", meta.last_updated_formatted || meta.last_updated || "—");

  const root = document.getElementById("sectionsRoot");
  const sections = data.sections || {};
  root.innerHTML = SECTION_ORDER.map((s) => sectionHtml(s, sections[s] || [])).join("");
  wireControls();
}

function wireControls() {
  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".filter-btn").forEach((b) => {
        b.classList.remove("active", "bg-blue-50", "text-blue-700", "border-blue-600", "font-medium");
        b.classList.add("text-gray-600", "border-gray-200");
      });
      btn.classList.add("bg-blue-50", "text-blue-700", "border-blue-600", "font-medium");
      btn.classList.remove("text-gray-600", "border-gray-200");
      const f = btn.dataset.filter;
      document.querySelectorAll(".section-block").forEach((sec) => {
        sec.style.display = (f === "all" || sec.dataset.section === f) ? "" : "none";
      });
    };
  });
  const search = document.getElementById("searchInput");
  if (search) search.oninput = (e) => {
    const q = e.target.value.toLowerCase().trim();
    document.querySelectorAll("tbody tr").forEach((row) => {
      if (!row.dataset.category) return; // skip "empty" placeholder rows
      row.style.display = (!q || row.textContent.toLowerCase().includes(q)) ? "" : "none";
    });
  };
}

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
    e.preventDefault();
    document.getElementById("searchInput")?.focus();
  }
});

const SECTOR_BUCKETS = {
  social_tech_count: ["Social Media / Tech"],
  healthcare_count: ["Healthcare", "Insurance / Healthcare", "Insurance"],
  fintech_count: ["Fintech", "Payments / Fintech", "Payments"],
  gov_count: ["Government"],
};

function snapshotFromRows(rows) {
  const sections = {}; SECTION_ORDER.forEach((s) => (sections[s] = []));
  rows.forEach((r) => {
    const s = SECTION_ORDER.includes(r.section) ? r.section : "sectoral_regulators";
    sections[s].push(r);
  });
  const stats = {
    total_all_sections: rows.length,
    total_dpdpa_board: sections.dpdpa_board.length,
    total_sectoral_regulators: sections.sectoral_regulators.length,
    total_cert_in_breach: sections.cert_in_breach.length,
    total_courts_case_law: sections.courts_case_law.length,
    total_international: sections.international_benchmarks.length,
  };
  const sc = { social_tech_count: 0, healthcare_count: 0, fintech_count: 0, gov_count: 0, other_sectors_count: 0 };
  rows.forEach((r) => {
    const hit = Object.entries(SECTOR_BUCKETS).find(([, names]) => names.includes(r.sector));
    if (hit) sc[hit[0]]++; else sc.other_sectors_count++;
  });
  const now = new Date();
  return {
    metadata: { last_updated_formatted: now.toLocaleDateString("en-GB", { day: "2-digit", month: "long", year: "numeric" }) },
    statistics: stats, sector_counts: sc, sections,
  };
}

async function liveRefresh() {
  if (!CONFIG.SUPABASE_URL || !CONFIG.SUPABASE_ANON_KEY) return;
  try {
    const url = `${CONFIG.SUPABASE_URL}/rest/v1/enforcement_public?select=*&order=date.desc`;
    const res = await fetch(url, {
      headers: { apikey: CONFIG.SUPABASE_ANON_KEY, Authorization: `Bearer ${CONFIG.SUPABASE_ANON_KEY}` },
    });
    if (!res.ok) return;
    const rows = await res.json();
    if (Array.isArray(rows) && rows.length) render(snapshotFromRows(rows));
  } catch (err) { console.warn("live refresh skipped:", err.message); }
}

function flattenSections(data) {
  const rows = [];
  const sections = data.sections || {};
  SECTION_ORDER.forEach((s) => (sections[s] || []).forEach((r) => rows.push({ ...r, section: s })));
  return rows;
}

// Local demo overlay: items verified in the admin (same origin) appear here too.
function demoPublished() {
  try { return JSON.parse(localStorage.getItem("demo_published")) || []; }
  catch { return []; }
}

async function boot() {
  let base = null;
  try {
    const res = await fetch("data/enforcement.json", { cache: "no-cache" });
    if (!res.ok) throw new Error("snapshot fetch failed");
    base = await res.json();
  } catch (err) {
    console.warn("tracker:", err.message);
  }

  const extra = demoPublished();
  if (base) {
    if (extra.length) render(snapshotFromRows([...flattenSections(base), ...extra]));
    else render(base);
  } else if (extra.length) {
    render(snapshotFromRows(extra));
  } else {
    const root = document.getElementById("sectionsRoot");
    if (root) root.innerHTML = `<div class="text-center text-gray-400 py-16">No dataset published yet. The pipeline will populate this on its next run.</div>`;
  }
  liveRefresh(); // optional freshest-data overlay when Supabase is configured
}
boot();

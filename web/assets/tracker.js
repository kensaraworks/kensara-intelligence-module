/* DPDPA Enforcement Tracker — progressive enhancement.
 *
 * The page is FULLY PRE-RENDERED server-side (see src/publish/render.py), so
 * crawlers that don't run JavaScript still see every case. This script never
 * re-renders the tables — it only:
 *   1. wires the filter + search controls onto the existing DOM, and
 *   2. quietly checks Supabase for cases published since the last render and
 *      surfaces a non-intrusive notice.
 *
 * Deliberately NOT re-rendering avoids two rendering paths drifting apart and
 * guarantees what a crawler sees is what a human sees. */

const CONFIG = {
  SUPABASE_URL: "https://cqjjmednofcdjrigjaer.supabase.co",
  SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNxamptZWRub2ZjZGpyaWdqYWVyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk4MTYyMzIsImV4cCI6MjEwNTM5MjIzMn0.OhVpRSjByOA7L__Ew94LxYp-xREhQjMu-LUx4zeT9Dg",
};

// ── 1. Filters + search over the pre-rendered DOM ─────────────────────────
function wireControls() {
  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
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
    });
  });

  const search = document.getElementById("searchInput");
  if (search) {
    search.addEventListener("input", (ev) => {
      const q = ev.target.value.toLowerCase().trim();
      document.querySelectorAll("tbody tr").forEach((row) => {
        if (!row.dataset.category) return;           // skip empty-state rows
        row.style.display = (!q || row.textContent.toLowerCase().includes(q)) ? "" : "none";
      });
      // Hide sections that no longer have visible rows while searching.
      document.querySelectorAll(".section-block").forEach((sec) => {
        if (!q) { sec.style.display = ""; return; }
        const anyVisible = [...sec.querySelectorAll("tbody tr[data-category]")]
          .some((r) => r.style.display !== "none");
        sec.style.display = anyVisible ? "" : "none";
      });
    });
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
    e.preventDefault();
    document.getElementById("searchInput")?.focus();
  }
});

// ── 2. Freshness check (never re-renders) ─────────────────────────────────
function renderedCount() {
  return document.querySelectorAll("tbody tr[data-category]").length;
}

function showFreshnessNotice(extra) {
  if (document.getElementById("freshNotice")) return;
  const bar = document.createElement("div");
  bar.id = "freshNotice";
  bar.className = "bg-blue-50 border-b border-blue-200 text-sm text-blue-800";
  bar.innerHTML = `<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex items-center gap-2">
      <span class="w-2 h-2 bg-blue-500 rounded-full"></span>
      <span><strong>${extra}</strong> newly verified ${extra === 1 ? "case has" : "cases have"}
      been published since this page was generated. They appear on the next scheduled update.</span>
    </div>`;
  const nav = document.querySelector("nav");
  nav?.parentNode.insertBefore(bar, nav.nextSibling);
}

async function checkFreshness() {
  if (!CONFIG.SUPABASE_URL || !CONFIG.SUPABASE_ANON_KEY) return;
  try {
    const res = await fetch(
      `${CONFIG.SUPABASE_URL}/rest/v1/enforcement_public?select=id`,
      {
        headers: {
          apikey: CONFIG.SUPABASE_ANON_KEY,
          Authorization: `Bearer ${CONFIG.SUPABASE_ANON_KEY}`,
          Prefer: "count=exact",
          Range: "0-0",
        },
      }
    );
    if (!res.ok) return;
    const range = res.headers.get("content-range") || "";   // e.g. "0-0/12"
    const total = parseInt(range.split("/")[1], 10);
    if (!Number.isFinite(total)) return;
    const diff = total - renderedCount();
    if (diff > 0) showFreshnessNotice(diff);
  } catch (err) {
    /* freshness is a nicety — never let it affect the page */
  }
}

wireControls();
checkFreshness();

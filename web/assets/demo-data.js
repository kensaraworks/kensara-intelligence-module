/* Local DEMO fixtures — used only when Supabase is not configured (or ?demo=1).
 * Lets you exercise the full admin + tracker UI with no backend at all.
 * State persists in localStorage so verify/discard survive reloads.
 * Nothing here runs in production once SUPABASE_URL is set. */

window.DEMO_CANDIDATES = [
  {
    id: "AUTO-2026-0A1F2C", section: "sectoral_regulators", date: "2026-09-12",
    authority: "Reserve Bank of India", company: "[Needs review — see source]",
    sector: "Fintech", violation_type: "[Auto-flagged — verify]",
    dpdpa_section: "", penalty_amount: "Rs 25 crore",
    summary: "AUTO-DETECTED: RBI imposes ₹25 crore penalty on a payments firm over data localisation lapses. Snippet: The Reserve Bank found customer payment data stored on overseas servers in breach of the 2018 directive and ordered remediation within 90 days.",
    outcome: "Investigation Ongoing", source_url: "https://economictimes.indiatimes.com/example/rbi-penalty",
    confidence: "low", needs_review: true, detected_at: "2026-09-17T04:30:00Z",
    sources: [
      { source: "economictimes.indiatimes.com", url: "https://economictimes.indiatimes.com/example/rbi-penalty" },
      { source: "livemint.com", url: "https://livemint.com/example/rbi-penalty" },
      { source: "inc42.com", url: "https://inc42.com/example/rbi-penalty" }
    ], official_source_url: "",
  },
  {
    id: "AUTO-2026-0B7D91", section: "cert_in_breach", date: "2026-09-15",
    authority: "CERT-In", company: "A healthtech aggregator",
    sector: "Healthcare", violation_type: "Delayed breach reporting",
    dpdpa_section: "IT Act §70B(6) — CERT-In 2022 Directions", penalty_amount: "",
    summary: "AUTO-DETECTED: A health-records aggregator reportedly failed to notify CERT-In within the mandated 6-hour window after a data exposure affecting ~2 lakh users. CERT-In has sought an incident report.",
    outcome: "Investigation Ongoing", source_url: "https://inc42.com/example/healthtech-breach",
    confidence: "medium", needs_review: true, detected_at: "2026-09-17T04:31:00Z",
  },
  {
    id: "AUTO-2026-0C33A8", section: "sectoral_regulators", date: "2026-09-09",
    authority: "Competition Commission of India", company: "A large ad-tech platform",
    sector: "Social Media / Tech", violation_type: "Data-sharing / abuse of dominance",
    dpdpa_section: "Competition Act §4", penalty_amount: "Rs 50 crore",
    summary: "AUTO-DETECTED: The CCI is examining whether an ad-tech platform's data-combination practices harm competition, with a possible penalty in the range of ₹50 crore under discussion.",
    outcome: "Investigation Ongoing", source_url: "https://livemint.com/example/cci-adtech",
    confidence: "medium", needs_review: true, detected_at: "2026-09-17T04:32:00Z",
  },
  {
    id: "AUTO-2026-0D5E44", section: "courts_case_law", date: "2026-08-28",
    authority: "High Court / Supreme Court", company: "State of Karnataka v. Data Broker Pvt Ltd",
    sector: "Government", violation_type: "Unlawful data scraping",
    dpdpa_section: "IT Act §43A", penalty_amount: "Rs 15 lakh compensation",
    summary: "AUTO-DETECTED: A High Court awarded ₹15 lakh compensation against a data broker for unlawfully scraping and reselling personal data, citing IT Act Section 43A negligence in maintaining reasonable security practices.",
    outcome: "Adjudication Order Issued", source_url: "https://indiankanoon.org/example/data-broker",
    confidence: "high", needs_review: true, detected_at: "2026-09-17T04:33:00Z",
    sources: [{ source: "indiankanoon.org", url: "https://indiankanoon.org/example/data-broker" }],
    official_source_url: "https://indiankanoon.org/example/data-broker",
  },
  {
    id: "AUTO-2026-0E9B10", section: "international_benchmarks", date: "2026-09-02",
    authority: "Unknown", company: "An Indian IT/ITES subsidiary in the EU",
    sector: "Social Media / Tech", violation_type: "GDPR transfer non-compliance",
    dpdpa_section: "GDPR Art. 44", penalty_amount: "€2 million",
    summary: "AUTO-DETECTED: An EU regulator reportedly fined the European subsidiary of an Indian IT services firm €2 million over inadequate safeguards on personal-data transfers back to India — a live benchmark for DPDPA cross-border risk.",
    outcome: "Fine Imposed", source_url: "https://iapp.org/example/india-ites-gdpr",
    confidence: "low", needs_review: true, detected_at: "2026-09-17T04:34:00Z",
  },
];

window.DEMO_STORIES = [
  { headline: "RBI penalises payments firm ₹25 crore over data localisation lapses", source: "economictimes.indiatimes.com", score: 18, action_taken: "extracted", intent_tag: "enforcement", url: "https://economictimes.indiatimes.com/example/rbi-penalty", processed_at: "2026-09-19T04:00:00Z" },
  { headline: "CERT-In seeks report after healthtech breach exposes 2 lakh records", source: "inc42.com", score: 16, action_taken: "alerted", intent_tag: "breach", url: "https://inc42.com/example/healthtech-breach", processed_at: "2026-09-19T04:00:00Z" },
  { headline: "CCI examines ad-tech platform's data-combination practices", source: "livemint.com", score: 14, action_taken: "extracted", intent_tag: "enforcement", url: "https://livemint.com/example/cci-adtech", processed_at: "2026-09-18T20:00:00Z" },
  { headline: "MeitY signals DPDP Rules notification 'in weeks', Board appointments underway", source: "yourstory.com", score: 13, action_taken: "alerted", intent_tag: "regulatory", url: "https://yourstory.com/example/dpdp-rules", processed_at: "2026-09-18T16:00:00Z" },
  { headline: "High Court awards ₹15 lakh against data broker under IT Act 43A", source: "indiankanoon.org", score: 13, action_taken: "extracted", intent_tag: "judgment", url: "https://indiankanoon.org/example/data-broker", processed_at: "2026-09-18T12:00:00Z" },
  { headline: "Fintech lenders scramble as consent-manager framework nears launch", source: "entrackr.com", score: 11, action_taken: "scanned", intent_tag: "regulatory", url: "https://entrackr.com/example/consent-manager", processed_at: "2026-09-18T08:00:00Z" },
  { headline: "EU regulator fines Indian ITES subsidiary €2M over transfer safeguards", source: "iapp.org", score: 10, action_taken: "scanned", intent_tag: "international", url: "https://iapp.org/example/india-ites-gdpr", processed_at: "2026-09-17T18:00:00Z" },
  { headline: "SEBI floats cybersecurity & data-protection norms for intermediaries", source: "livemint.com", score: 9, action_taken: "scanned", intent_tag: "regulatory", url: "https://livemint.com/example/sebi-cyber", processed_at: "2026-09-17T10:00:00Z" },
  { headline: "Explainer: what the DPDPA means for Indian SaaS startups", source: "inc42.com", score: 7, action_taken: "scanned", intent_tag: "educational", url: "https://inc42.com/example/dpdpa-saas", processed_at: "2026-09-16T09:00:00Z" },
  { headline: "Opinion: India's privacy law needs sharper breach timelines", source: "yourstory.com", score: 6, action_taken: "suppressed", intent_tag: "opinion", url: "https://yourstory.com/example/opinion-privacy", processed_at: "2026-09-16T07:00:00Z" },
];

window.DEMO_BRIEF = {
  period: "2026-W38",
  markdown: `# Enforcement Intelligence Brief — 2026-W38

**Headline takeaway:** Sectoral regulators, not the DPDP Board, are still driving India's data-protection enforcement — with the RBI and CCI most active this week.

**What changed:** A fresh RBI localisation penalty and a CCI ad-tech inquiry pushed Fintech and Social Media/Tech to the top of the risk table. CERT-In's 6-hour rule produced another notice in healthtech. The DPDP Rules edged closer to notification.

**Most active authorities:** Reserve Bank of India (2), CERT-In (1), CCI (1).
**Most-cited provisions:** RBI 2018 localisation directive, IT Act §70B(6), Competition Act §4.

**Action for Indian companies:** If you process payment or health data, pre-stage your 6-hour breach-notification workflow now — the enforcement pattern is notices first, penalties fast.`,
  stats: {
    verified_cases: 11,
    by_sector: { "Fintech": 3, "Social Media / Tech": 3, "Healthcare": 1, "Government": 4 },
    top_authorities: [["Reserve Bank of India", 2], ["CERT-In", 1], ["Competition Commission of India", 1]],
    total_penalty_inr: 15000000000,
  },
};

window.DEMO_ANGLES = [
  { headline: "RBI penalises payments firm ₹25 crore over data localisation lapses", angle: "RBI Data Localisation in 2026: The Compliance Checklist Fintechs Keep Failing", target_keyword: "RBI data localisation compliance", rationale: "High commercial intent; competitors rank but lack an actionable checklist.", score: 18 },
  { headline: "CERT-In seeks report after healthtech breach exposes 2 lakh records", angle: "The 6-Hour Clock: A CERT-In Breach-Reporting Playbook for Health & Fintech", target_keyword: "CERT-In 6 hour breach reporting", rationale: "Ranks for a recurring pain point; ties directly to Kensara's breach-clock automation.", score: 16 },
  { headline: "CCI examines ad-tech platform's data-combination practices", angle: "When Data-Sharing Becomes an Antitrust Problem: Lessons from CCI's Ad-Tech Probe", target_keyword: "CCI data sharing penalty", rationale: "Emerging topic with thin competitor coverage — first-mover SEO opportunity.", score: 14 },
];

window.DEMO_RUNS = [
  { ran_at: "2026-09-19T04:00:00Z", job: "news_scan", source: null, status: "ok", items_found: 42, detail: "scanned=42 suppressed=7 alerted=5" },
  { ran_at: "2026-09-19T00:00:00Z", job: "news_scan", source: null, status: "ok", items_found: 38, detail: "scanned=38 suppressed=4 alerted=3" },
  { ran_at: "2026-09-18T00:30:00Z", job: "enforcement", source: null, status: "ok", items_found: 3, detail: "scanned=68 inserted=3 suppressed=11" },
  { ran_at: "2026-09-18T00:30:00Z", job: "enforcement", source: "indiankanoon.org", status: "ok", items_found: 1, detail: "" },
  { ran_at: "2026-09-16T00:30:00Z", job: "competitor", source: "securiti.ai", status: "ok", items_found: 18, detail: "" },
  { ran_at: "2026-09-16T00:30:00Z", job: "competitor", source: "cookieyes.com", status: "blocked", items_found: 0, detail: "HTTP 403 — Cloudflare challenge" },
  { ran_at: "2026-09-16T00:30:00Z", job: "competitor", source: "tsaaro.com", status: "ok", items_found: 12, detail: "" },
];

window.DEMO_ENTITIES = [
  { key: "meta platforms", slug: "meta-platforms", name: "Meta Platforms", entity_type: "company",
    aliases: ["WhatsApp / Meta", "Facebook India"] },
  { key: "star health allied insurance", slug: "star-health-allied-insurance",
    name: "Star Health and Allied Insurance", entity_type: "company", aliases: ["Star Health"] },
  { key: "mastercard", slug: "mastercard", name: "Mastercard", entity_type: "company", aliases: [] },
  { key: "american express", slug: "american-express", name: "American Express",
    entity_type: "company", aliases: ["American Express & Diners Club"] },
  { key: "reserve bank india", slug: "reserve-bank-india", name: "Reserve Bank of India",
    entity_type: "regulator", aliases: ["RBI"] },
  { key: "competition commission india", slug: "competition-commission-india",
    name: "Competition Commission of India", entity_type: "regulator", aliases: ["CCI"] },
  { key: "cert-in", slug: "cert-in", name: "CERT-In", entity_type: "regulator", aliases: [] },
  { key: "supreme court india", slug: "supreme-court-india", name: "Supreme Court of India",
    entity_type: "court", aliases: ["Supreme Court"] },
];

// event_entities links, so the graph tab can show a case count per entity.
window.DEMO_EVENT_LINKS = [
  { event_id: "IND-CCI-001", entity_key: "meta platforms", role: "subject" },
  { event_id: "INTL-EU-001", entity_key: "meta platforms", role: "subject" },
  { event_id: "IND-CCI-001", entity_key: "competition commission india", role: "authority" },
  { event_id: "IND-RBI-001", entity_key: "mastercard", role: "subject" },
  { event_id: "IND-RBI-001", entity_key: "reserve bank india", role: "authority" },
  { event_id: "IND-RBI-002", entity_key: "american express", role: "subject" },
  { event_id: "IND-RBI-002", entity_key: "reserve bank india", role: "authority" },
  { event_id: "IND-CERT-002", entity_key: "star health allied insurance", role: "subject" },
  { event_id: "IND-CERT-002", entity_key: "cert-in", role: "authority" },
  { event_id: "IND-SC-001", entity_key: "supreme court india", role: "authority" },
];

// Verification evidence for one queued candidate, so the review card shows
// what a substantiated entry actually looks like.
window.DEMO_EVIDENCE = [
  { action_id: "AUTO-2026-0D5E44", official_url: "https://indiankanoon.org/example/data-broker",
    archived_url: "https://web.archive.org/web/2026/https://indiankanoon.org/example/data-broker",
    content_sha256: "9f2c1b7a4e6d8c0f3a5b2e9d7c4f1a8b6e3d0c7f2a9b5e8d1c4f7a0b3e6d9c2f",
    excerpt: "…the Court awarded compensation of Rs. 15,00,000 (Rupees Fifteen Lakh only) against "
             + "the data broker for unlawfully scraping and reselling personal data…",
    entity_matched: true, amount_matched: true, date_matched: false,
    strength: "strong", independent_sources: 2, verified_at: "2026-09-17T04:40:00Z" },
];

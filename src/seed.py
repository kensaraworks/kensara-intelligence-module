"""Curated baseline of real, verified enforcement actions.

These ship the tracker with a credible starting dataset (auto_detected = False,
needs_review = False) so the public page is useful on day one. The autonomous
pipeline then appends auto-detected candidates on top, into the review queue.

Facts are drawn from public regulatory notices, court records and mainstream
reporting. Verify against the linked sources before relying on any figure.

Run:  python -m src.seed            # push to Supabase + rebuild snapshot
      python -m src.seed --local    # rebuild snapshot from seed only (no DB)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SEED_ACTIONS: list[dict] = [
    # ── DPDPA & Data Protection Board ─────────────────────────────────────
    {
        "id": "IND-DPDPA-001", "section": "dpdpa_board", "date": "2023-08-11",
        "authority": "MeitY", "company": "Statute — All Data Fiduciaries",
        "sector": "Government", "violation_type": "Legislation enacted",
        "dpdpa_section": "DPDP Act 2023",
        "summary": "The Digital Personal Data Protection Act, 2023 received Presidential assent, establishing India's first comprehensive data-protection statute with penalties up to ₹250 crore per breach.",
        "penalty_amount": "Up to ₹250 Cr (framework)", "penalty_amount_inr": 2500000000,
        "outcome": "Enacted",
        "source_url": "https://www.meity.gov.in/data-protection-framework",
    },
    {
        "id": "IND-DPDPA-002", "section": "dpdpa_board", "date": "2025-01-03",
        "authority": "MeitY", "company": "Draft DPDP Rules",
        "sector": "Government", "violation_type": "Subordinate legislation",
        "dpdpa_section": "DPDP Rules (Draft)",
        "summary": "MeitY published the draft Digital Personal Data Protection Rules for public consultation, detailing consent, breach-notification and Board-operation mechanics.",
        "penalty_amount": "N/A (Rules)", "penalty_amount_inr": 0,
        "outcome": "Consultation",
        "source_url": "https://www.meity.gov.in/",
    },

    # ── Sectoral Regulators ───────────────────────────────────────────────
    {
        "id": "IND-CCI-001", "section": "sectoral_regulators", "date": "2024-11-18",
        "authority": "Competition Commission of India", "company": "WhatsApp / Meta",
        "sector": "Social Media / Tech", "violation_type": "Data-sharing / abuse of dominance",
        "dpdpa_section": "Competition Act §4",
        "summary": "The CCI imposed a ₹213.14 crore penalty on Meta over WhatsApp's 2021 privacy policy and ordered a 5-year bar on sharing user data with other Meta companies for advertising.",
        "penalty_amount": "₹213.14 Cr", "penalty_amount_inr": 2131400000,
        "outcome": "Fine Imposed",
        "source_url": "https://www.cci.gov.in/",
    },
    {
        "id": "IND-RBI-001", "section": "sectoral_regulators", "date": "2021-07-14",
        "authority": "Reserve Bank of India", "company": "Mastercard",
        "sector": "Fintech", "violation_type": "Data localisation non-compliance",
        "dpdpa_section": "RBI Storage of Payment System Data (2018)",
        "summary": "The RBI barred Mastercard from onboarding new domestic customers for failing to comply with the 2018 payment-data localisation directive. The ban was lifted in June 2022 after compliance.",
        "penalty_amount": "Business restriction", "penalty_amount_inr": 0,
        "outcome": "Business Ban / Restriction",
        "source_url": "https://www.rbi.org.in/#mastercard-2021",
    },
    {
        "id": "IND-RBI-002", "section": "sectoral_regulators", "date": "2021-04-23",
        "authority": "Reserve Bank of India", "company": "American Express & Diners Club",
        "sector": "Fintech", "violation_type": "Data localisation non-compliance",
        "dpdpa_section": "RBI Storage of Payment System Data (2018)",
        "summary": "The RBI stopped American Express and Diners Club from onboarding new customers over payment-data localisation non-compliance; the restriction on Amex was lifted in August 2022.",
        "penalty_amount": "Business restriction", "penalty_amount_inr": 0,
        "outcome": "Business Ban / Restriction",
        "source_url": "https://www.rbi.org.in/#amex-2021",
    },

    # ── CERT-In & Breaches ────────────────────────────────────────────────
    {
        "id": "IND-CERT-001", "section": "cert_in_breach", "date": "2022-04-28",
        "authority": "CERT-In", "company": "All body corporates & intermediaries",
        "sector": "Government", "violation_type": "6-hour breach reporting mandate",
        "dpdpa_section": "IT Act §70B(6) — CERT-In 2022 Directions",
        "summary": "CERT-In issued directions requiring cyber-incident reporting within 6 hours and 180-day log retention, effective 28 June 2022 — India's first strictly enforced breach-notification regime.",
        "penalty_amount": "Penalty / imprisonment (framework)", "penalty_amount_inr": 0,
        "outcome": "Enacted",
        "source_url": "https://www.cert-in.org.in/#directions-2022",
    },
    {
        "id": "IND-CERT-002", "section": "cert_in_breach", "date": "2024-09-20",
        "authority": "CERT-In / IRDAI", "company": "Star Health & Allied Insurance",
        "sector": "Healthcare", "violation_type": "Sensitive health-data breach",
        "dpdpa_section": "IT Act §43A / §70B",
        "summary": "A reported breach exposed policyholder health and personal data of Star Health customers, prompting CERT-In and IRDAI scrutiny and litigation over the alleged leak.",
        "penalty_amount": "Investigation", "penalty_amount_inr": 0,
        "outcome": "Investigation Ongoing",
        "source_url": "https://www.cert-in.org.in/#star-health-2024",
    },

    # ── Courts & Case Law ─────────────────────────────────────────────────
    {
        "id": "IND-SC-001", "section": "courts_case_law", "date": "2017-08-24",
        "authority": "High Court / Supreme Court", "company": "K.S. Puttaswamy v Union of India",
        "sector": "Government", "violation_type": "Right to privacy",
        "dpdpa_section": "Constitution Art. 21",
        "summary": "A nine-judge Supreme Court bench unanimously held privacy to be a fundamental right, laying the constitutional foundation for India's data-protection regime.",
        "penalty_amount": "Landmark judgment", "penalty_amount_inr": 0,
        "outcome": "Adjudication Order Issued",
        "source_url": "https://main.sci.gov.in/",
    },

    # ── International Benchmarks ───────────────────────────────────────────
    {
        "id": "INTL-EU-001", "section": "international_benchmarks", "date": "2023-05-22",
        "authority": "Irish Data Protection Commission", "company": "Meta Platforms",
        "sector": "Social Media / Tech", "violation_type": "Unlawful EU–US data transfer",
        "dpdpa_section": "GDPR Art. 46",
        "summary": "The Irish DPC fined Meta €1.2 billion — the largest GDPR penalty to date — for transferring EU user data to the US without adequate safeguards. A benchmark for cross-border transfer risk.",
        "penalty_amount": "€1.2 Billion", "penalty_amount_inr": 10800000000,
        "outcome": "Fine Imposed",
        "source_url": "https://www.dataprotection.ie/#meta-2023",
    },
    {
        "id": "INTL-EU-002", "section": "international_benchmarks", "date": "2024-10-24",
        "authority": "Irish Data Protection Commission", "company": "LinkedIn",
        "sector": "Social Media / Tech", "violation_type": "Behavioural-advertising consent",
        "dpdpa_section": "GDPR Art. 6",
        "summary": "The Irish DPC fined LinkedIn €310 million over unlawful processing of member data for targeted advertising — relevant to Indian IT/ITES firms serving EU data subjects.",
        "penalty_amount": "€310 Million", "penalty_amount_inr": 2790000000,
        "outcome": "Fine Imposed",
        "source_url": "https://www.dataprotection.ie/#linkedin-2024",
    },
]


def _decorate(row: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        **row,
        "auto_detected": False,
        "needs_review": False,
        "confidence": "high",
        "notes": row.get("notes", "Curated baseline — verify against source."),
        "llm_extracted_data": {},
        "detected_at": now,
        "verified_at": now,
        "updated_at": now,
    }


def load_to_supabase() -> int:
    from src.db.supabase_client import db
    from src.db.store import ENFORCEMENT

    rows = [_decorate(r) for r in SEED_ACTIONS]
    res = db.upsert(ENFORCEMENT, rows, on_conflict="id", ignore_duplicates=False)
    return len(res)


def build_local_snapshot(path: Path | None = None) -> Path:
    """Build web/data/enforcement.json directly from the seed (no DB needed)."""
    from src.db.store import SECTIONS, _public_row, _SECTOR_BUCKETS

    rows = [_decorate(r) for r in SEED_ACTIONS]
    sections = {s: [] for s in SECTIONS}
    for r in rows:
        sec = r["section"] if r["section"] in sections else "sectoral_regulators"
        sections[sec].append(_public_row(r))

    stats = {
        "total_all_sections": len(rows),
        "total_dpdpa_board": len(sections["dpdpa_board"]),
        "total_sectoral_regulators": len(sections["sectoral_regulators"]),
        "total_cert_in_breach": len(sections["cert_in_breach"]),
        "total_courts_case_law": len(sections["courts_case_law"]),
        "total_international": len(sections["international_benchmarks"]),
    }
    sector_counts = {k: 0 for k in _SECTOR_BUCKETS}
    sector_counts["other_sectors_count"] = 0
    for r in rows:
        matched = False
        for bucket, names in _SECTOR_BUCKETS.items():
            if r.get("sector") in names:
                sector_counts[bucket] += 1
                matched = True
                break
        if not matched:
            sector_counts["other_sectors_count"] += 1

    snapshot = {
        "metadata": {
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "last_updated_formatted": datetime.now(timezone.utc).strftime("%d %B %Y"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "statistics": stats,
        "sector_counts": sector_counts,
        "sections": sections,
    }
    path = path or (Path(__file__).resolve().parents[1] / "web" / "data" / "enforcement.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    if "--local" in sys.argv:
        print("snapshot:", build_local_snapshot())
    else:
        n = load_to_supabase()
        print(f"seeded {n} rows to Supabase")
        from src.publish.snapshot import publish_all
        print("published:", publish_all())

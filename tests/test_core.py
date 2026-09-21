"""Core logic tests — pure, no network or DB required."""
import asyncio

from src.processing.dedup import Deduplicator, fingerprint
from src.processing.llm_extractor import extract_enforcement
from src.processing.scoring import (
    calculate_relevance_score,
    classify_section,
    classify_sector,
    compute_days_old,
)


def test_score_caps_at_20_plus_recency():
    s = calculate_relevance_score(
        "RBI imposes penalty on Paytm for DPDPA data localisation breach",
        "Reserve Bank of India fined the fintech ₹5 crore under section 8 enforcement order",
        "inc42",
        "2026-09-15",
    )
    assert s >= 20  # capped base 20 + recency delta


def test_score_low_for_irrelevant():
    s = calculate_relevance_score("New cafe opens downtown", "A cafe opened.", "blog", "2026-09-01")
    assert s < 6


def test_section_classification():
    assert classify_section("6 hour breach notification", "CERT-In") == "cert_in_breach"
    assert classify_section("Supreme Court judgment section 43A") == "courts_case_law"
    assert classify_section("GDPR fine by ICO", "ICO") == "international_benchmarks"
    assert classify_section("RBI localisation order", "RBI") == "sectoral_regulators"
    assert classify_section("DPDP Rules by MeitY", "MeitY") == "dpdpa_board"


def test_sector_classification():
    assert classify_sector("Star Health insurance leak") == "Healthcare"
    assert classify_sector("Paytm UPI payment breach") == "Fintech"


def test_dedup_flags_near_identical():
    d = Deduplicator(threshold=0.6)
    a = d.is_duplicate("RBI fines Paytm five crore for data localisation breach under DPDPA")
    b = d.is_duplicate("RBI fines Paytm five crore for data localisation breach under DPDPA act")
    assert a[0] is False and b[0] is True


def test_dedup_keeps_distinct():
    d = Deduplicator(threshold=0.85)
    d.is_duplicate("RBI fines Paytm for data localisation breach")
    c = d.is_duplicate("Zomato launches grocery delivery in Bangalore today")
    assert c[0] is False


def test_days_old_parsing():
    assert compute_days_old("") == 30
    assert compute_days_old("2020-01-01") > 1000


def test_heuristic_extractor_word_boundary():
    # "Bangalore" must NOT trip the "ban" signal.
    ex = asyncio.run(extract_enforcement(
        "Zomato launches feature", "Launched a grocery feature in Bangalore.", "https://x/1"))
    assert ex is None
    # Real enforcement is detected + penalty captured.
    ex2 = asyncio.run(extract_enforcement(
        "RBI penalty on XYZ", "RBI ordered XYZ Pvt Ltd to pay Rs 5 crore penalty.", "https://x/2"))
    assert ex2 is not None and "crore" in ex2.penalty_amount.lower()


def test_fingerprint_is_serialisable():
    fp = fingerprint("DPDPA enforcement penalty India")
    assert isinstance(fp, dict) and all(isinstance(v, int) for v in fp.values())


def test_signature_collapses_variants():
    from src.processing.signature import make_signature
    assert make_signature("Acme Payments Pvt Ltd", "RBI") == make_signature("ACME Payments Limited", "RBI")
    assert make_signature("Acme", "RBI") != make_signature("Acme", "CERT-In")


def test_cluster_merges_same_event_keeps_sources():
    from src.processing.clustering import merge_candidate_rows
    rows = [
        {"company": "Acme Pvt Ltd", "authority": "Reserve Bank of India", "date": "2026-09-12",
         "penalty_amount_inr": 250000000, "summary": "short", "confidence": "low",
         "source_url": "https://et.com/a", "penalty_amount": "", "dpdpa_section": "", "violation_type": "x"},
        {"company": "ACME Limited", "authority": "Reserve Bank of India", "date": "2026-09-13",
         "penalty_amount_inr": 250000000, "summary": "a longer richer summary", "confidence": "high",
         "source_url": "https://inc42.com/b", "official_source_url": "https://rbi.org.in/x",
         "penalty_amount": "Rs 25 crore", "dpdpa_section": "", "violation_type": ""},
        {"company": "Zomato", "authority": "CCI", "date": "2026-09-01", "penalty_amount_inr": 0,
         "summary": "d", "confidence": "medium", "source_url": "https://x/z",
         "penalty_amount": "", "dpdpa_section": "", "violation_type": ""},
    ]
    merged = merge_candidate_rows(rows)
    assert len(merged) == 2
    acme = next(m for m in merged if "cme" in m["company"])
    assert len(acme["sources"]) == 2
    assert acme["confidence"] == "high"
    assert acme["official_source_url"] == "https://rbi.org.in/x"
    assert acme["penalty_amount"] == "Rs 25 crore"


def test_fulltext_truncates():
    from src.processing.fulltext import clean_html_to_text
    html = "<html><body><script>x</script><article>" + ("word " * 3000) + "</article></body></html>"
    text = clean_html_to_text(html, max_chars=500)
    assert len(text) <= 500 and "word" in text and "x" not in text.split()


# ── Phase 1: knowledge graph ──────────────────────────────────────────────
def test_entity_resolver_merges_aliases():
    from src.graph.entities import EntityResolver
    r = EntityResolver()
    a = r.resolve("WhatsApp / Meta")
    b = r.resolve("Meta Platforms")
    c = r.resolve("Facebook India")
    assert a.key == b.key == c.key, "Meta variants must resolve to one entity"
    assert a.name == "Meta Platforms"


def test_entity_resolver_splits_multi_authority():
    from src.graph.entities import EntityResolver
    r = EntityResolver()
    parts = r.resolve_authorities("CERT-In / IRDAI")
    assert len(parts) == 2
    names = {p.name for p in parts}
    assert any("CERT" in n for n in names)
    assert any("Insurance" in n for n in names)


def test_entity_classification_excludes_non_entities():
    from src.graph.entities import classify_entity
    assert classify_entity("K.S. Puttaswamy v Union of India") == "case"
    assert classify_entity("All body corporates & intermediaries") == "generic"
    assert classify_entity("Reserve Bank of India") == "regulator"
    assert classify_entity("Mastercard") == "company"


def test_graph_links_entity_across_cases():
    from src.graph.build import build_graph
    rows = [
        {"id": "1", "company": "WhatsApp / Meta", "authority": "Competition Commission of India",
         "date": "2024-11-18", "section": "sectoral_regulators", "penalty_amount_inr": 2131400000},
        {"id": "2", "company": "Meta Platforms", "authority": "Irish Data Protection Commission",
         "date": "2023-05-22", "section": "international_benchmarks", "penalty_amount_inr": 10800000000},
        {"id": "3", "company": "Mastercard", "authority": "Reserve Bank of India",
         "date": "2021-07-14", "section": "sectoral_regulators"},
    ]
    g = build_graph(rows)
    meta = next(e for e in g.entities if e.name == "Meta Platforms")
    assert len(g.entity_events(meta)) == 2, "both Meta cases must link to one entity"
    assert all(e.event_ids for e in g.pageable)


def test_graph_is_idempotent():
    from src.graph.build import build_graph
    rows = [{"id": "1", "company": "Mastercard", "authority": "Reserve Bank of India",
             "date": "2021-07-14", "section": "sectoral_regulators"}]
    a, b = build_graph(rows), build_graph(rows)
    assert [e.slug for e in a.entities] == [e.slug for e in b.entities]


def test_contradiction_normalises_amounts():
    from src.graph.build import _normalise_amount
    assert _normalise_amount("₹213.14 Cr") == _normalise_amount("₹213.14 crore")
    assert _normalise_amount("₹213.14 Cr") != _normalise_amount("₹250 Cr")

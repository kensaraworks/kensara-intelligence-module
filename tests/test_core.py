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


# ── Phase 2: sensing net ──────────────────────────────────────────────────
def test_registry_discovery_is_free():
    from src.sensing.registry import ALL_SOURCES, stats
    s = stats()
    assert s["paid_api_sources"] == 0, "discovery must not depend on paid APIs"
    assert s["total"] >= 40
    assert all(x.kind in ("rss", "docwatch", "gnews") for x in ALL_SOURCES)


def test_gnews_url_is_india_scoped():
    from src.sensing.registry import gnews_rss
    url = gnews_rss("DPDPA India")
    assert "news.google.com/rss/search" in url and "gl=IN" in url


def test_prefilter_rejects_routine_regulatory_business():
    from src.sensing.prefilter import evaluate
    # Primary source, but routine banking business — must NOT flood the queue.
    v = evaluate("Reserve Bank of India (Priority Sector Lending) Directions",
                 "", "rbi.org.in", is_primary_source=True)
    assert not v.keep and v.reason == "off_topic_regulatory"


def test_prefilter_rejects_corporate_noise():
    from src.sensing.prefilter import evaluate
    v = evaluate("Zeropearl VC leads Rs 11.4 Cr seed round in surgery platform",
                 "startup data", "entrackr.com")
    assert not v.keep and v.reason == "corporate_noise"


def test_prefilter_keeps_real_enforcement():
    from src.sensing.prefilter import evaluate
    v = evaluate("SEBI imposes penalty on broker for cybersecurity lapses",
                 "", "sebi.gov.in", is_primary_source=True)
    assert v.keep and v.priority >= 5


def test_prefilter_always_relevant_bypasses_anchor():
    from src.sensing.prefilter import evaluate
    # A CERT-In advisory ID need not contain the word "privacy".
    v = evaluate("CERT-In Advisory CIAD-2026-0012", "", "cert-in.org.in",
                 is_primary_source=True, always_relevant=True)
    assert v.keep


def test_gnews_fallback_does_not_forge_primary_source():
    """A press article surfaced via a regulator's fallback must not be
    attributed to that regulator — it would forge a primary-source label."""
    import dataclasses
    from src.sensing.registry import Source
    src = Source("CCI orders", "docwatch", 0, "https://cci.gov.in/x",
                 domain="cci.gov.in", is_primary_source=True)
    proxy = dataclasses.replace(src, kind="gnews", domain="",
                                is_primary_source=False, always_relevant=False)
    assert proxy.is_primary_source is False and proxy.domain == ""


# ── Phase 3: verification & trust ─────────────────────────────────────────
def test_indian_amount_formats_normalise():
    from src.verification.amounts import parse_amount
    vals = [parse_amount(x).value for x in
            ["Rs 5,00,000", "₹5 lakh", "INR 500000", "0.05 crore", "Five Lakh"]]
    assert len(set(vals)) == 1 and vals[0] == 500000


def test_amount_currency_not_conflated():
    from src.verification.amounts import parse_amount
    a, b = parse_amount("₹1.2 billion"), parse_amount("€1.2 billion")
    assert a.currency == "INR" and b.currency == "EUR"
    assert not a.close_to(b)


def test_verification_requires_entity_not_just_amount():
    """The guard against false attribution: a document mentioning the right
    penalty but the wrong company must NOT verify."""
    from src.verification.matcher import match_document
    doc = ("ADJUDICATION ORDER. In the matter of Reliance Securities Limited. "
           "The Adjudicating Officer imposes a penalty of Rs. 5,00,000/- for "
           "failure to comply with the cyber security framework.") * 2
    good = match_document(doc, company="Reliance Securities", penalty="Rs 5 lakh")
    bad = match_document(doc, company="HDFC Bank", penalty="Rs 5 lakh")
    assert good.verified and good.strength == "strong"
    assert not bad.verified and "entity_not_found" in bad.reasons


def test_entity_alone_is_not_verification():
    from src.verification.matcher import match_document
    doc = ("The Reserve Bank of India today published a list of regulated "
           "entities including Mastercard for informational purposes. " * 6)
    res = match_document(doc, company="Mastercard", penalty="Rs 25 crore")
    assert res.entity_matched and not res.amount_matched
    assert not res.verified, "a mere mention must not count as proof"


def test_independent_sources_collapses_same_domain():
    from src.verification.verify import independent_source_count
    assert independent_source_count(
        ["https://et.com/a", "https://www.et.com/b", "https://livemint.com/c"]) == 2


def test_evidence_hash_is_stable():
    from src.verification.archive import content_hash
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
    assert len(content_hash("abc")) == 64


# ── Phase 4: public surfaces ──────────────────────────────────────────────
def test_statute_does_not_misattribute_other_acts():
    """'IT Act Section 43A' must not map to DPDPA Section 43."""
    from src.publish.statute import sections_cited_in
    assert [s.label for s in sections_cited_in("DPDPA Section 8(6)")] == ["Section 8"]
    assert sections_cited_in("IT Act Section 43A") == []
    assert sections_cited_in("GDPR Art. 46") == []
    assert sections_cited_in("Competition Act §4") == []


def test_statute_slugs_are_stable_and_unique():
    from src.publish.statute import SECTIONS
    slugs = [s.slug for s in SECTIONS]
    assert len(slugs) == len(set(slugs))
    assert all(s.url_path.startswith("dpdpa/") for s in SECTIONS)


def test_calendar_only_publishes_sourced_milestones():
    """A wrong compliance deadline is worse than no deadline."""
    from src.publish.calendar_data import MILESTONES
    assert MILESTONES, "expected at least one curated milestone"
    for m in MILESTONES:
        assert m.source_url, f"milestone '{m.title}' has no source URL"
        assert len(m.date) == 10 and m.date[4] == "-"


def test_calendar_dedupes_curated_against_events():
    from src.publish.calendar_data import MILESTONES, build_calendar

    class _E:
        date = MILESTONES[0].date
        company, authority, summary = "X", "Y", "z"
        primary_source = None

    cal = build_calendar([_E()])
    on_that_date = [m for m in cal["past"] if m.date == MILESTONES[0].date]
    assert len(on_that_date) == 1, "curated milestone must win over the derived event"


# ── Recall protection: the cap must defer, never discard ──────────────────
def test_proceedings_and_entity_signals_lift_court_coverage():
    """Court coverage carries no penalty figure and no statute number, so the
    original keyword signals scored it near zero — yet a Supreme Court privacy
    hearing is exactly what the tracker exists to follow."""
    from src.processing.scoring import calculate_relevance_score as sc
    t = "SC to hear Meta-WhatsApp privacy policy case against CCI order"
    plain = sc(t, "", "business-standard.com", "2026-09-20")
    with_graph = sc(t, "", "business-standard.com", "2026-09-20", {"meta", "whatsapp"})
    assert plain >= 6, "proceedings signal should lift court coverage"
    assert with_graph > plain, "a follow-up on a tracked entity must rank higher"


def test_tracked_entity_terms_match_headline_forms():
    """The graph stores 'Meta Platforms' but headlines say 'Meta-WhatsApp' —
    matching must be on distinctive tokens, not canonical names."""
    from src.processing.scoring import calculate_relevance_score as sc
    terms = {"meta", "star health", "mastercard"}
    boosted = sc("Meta-WhatsApp privacy ruling", "", "x.com", "2026-09-20", terms)
    baseline = sc("Meta-WhatsApp privacy ruling", "", "x.com", "2026-09-20", set())
    assert boosted > baseline


def test_backlog_roundtrip_and_ageing():
    import json
    from datetime import datetime, timedelta, timezone
    from src.ingestion.models import RawItem
    from src.sensing import backlog

    items = [RawItem(source="s", title="kept item", url="https://x.test/1")]
    backlog.save_backlog(items)
    assert any(i.url == "https://x.test/1" for i in backlog.load_backlog())

    stale = [{"source": "s", "title": "old", "url": "https://x.test/2",
              "summary": "", "published": "",
              "queued_at": (datetime.now(timezone.utc)
                            - timedelta(days=backlog.MAX_AGE_DAYS + 5)).isoformat()}]
    backlog.BACKLOG_PATH.write_text(json.dumps(stale), encoding="utf-8")
    assert backlog.load_backlog() == [], "items older than the window must age out"
    backlog.BACKLOG_PATH.unlink(missing_ok=True)

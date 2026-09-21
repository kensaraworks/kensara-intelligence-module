"""DPDPA 2023 statute map — the long-tail SEO surface.

Queries like "DPDPA Section 8(6)" or "what is a Significant Data Fiduciary" are
high-intent and largely unowned. A page per section, interlinked with the cases
that cite it, compounds as the tracker grows.

IMPORTANT: ``summary`` fields are plain-English descriptions written for this
tracker — they are NOT the statutory text. Every page links to the official
source so a reader can check the authoritative wording. This is deliberate: a
paraphrase is more useful to a compliance reader, and misquoting a statute is
exactly the kind of error that would cost us credibility.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

OFFICIAL_TEXT_URL = "https://www.meity.gov.in/data-protection-framework"


@dataclass
class Section:
    number: str
    title: str
    chapter: str
    summary: str
    obligations: list[str] = field(default_factory=list)
    applies_to: str = "Data Fiduciary"
    keywords: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return f"section-{self.number.replace('(', '-').replace(')', '').lower()}"

    @property
    def url_path(self) -> str:
        return f"dpdpa/{self.slug}"

    @property
    def label(self) -> str:
        return f"Section {self.number}"


SECTIONS: list[Section] = [
    Section("3", "Application of the Act", "I — Preliminary",
            "Defines the territorial and material scope: the Act covers digital personal data "
            "processed in India, and processing outside India where it relates to offering goods "
            "or services to Data Principals in India.",
            ["Determine whether your processing falls in scope",
             "Non-Indian entities serving Indian users are covered"],
            keywords=["scope", "applicability", "extraterritorial"]),
    Section("4", "Grounds for processing personal data", "II — Obligations",
            "Personal data may be processed only for a lawful purpose, and only either with the "
            "Data Principal's consent or for a recognised 'legitimate use'.",
            ["Identify a lawful basis before any processing",
             "Document the purpose for each processing activity"],
            keywords=["lawful basis", "grounds", "legitimate use"]),
    Section("5", "Notice", "II — Obligations",
            "A request for consent must be preceded (or accompanied) by a clear notice stating "
            "what personal data is collected, the purpose, how to exercise rights, and how to "
            "complain to the Board.",
            ["Serve an itemised notice at or before consent",
             "Make the notice available in English and Eighth Schedule languages"],
            keywords=["privacy notice", "disclosure", "transparency"]),
    Section("6", "Consent", "II — Obligations",
            "Consent must be free, specific, informed, unconditional and unambiguous, given by a "
            "clear affirmative action, and limited to the data necessary for the stated purpose. "
            "It must be as easy to withdraw as to give.",
            ["No bundled or pre-ticked consent",
             "Provide a withdrawal mechanism of equal ease",
             "Stop processing and erase on withdrawal, absent another legal basis"],
            applies_to="Data Fiduciary / Consent Manager",
            keywords=["consent", "withdrawal", "consent manager"]),
    Section("7", "Certain legitimate uses", "II — Obligations",
            "Lists the situations where processing is permitted without consent — including where "
            "the Data Principal voluntarily provided data for a specified purpose, State functions "
            "and benefits, legal obligations, medical emergencies and employment purposes.",
            ["Map which activities rely on legitimate use rather than consent"],
            keywords=["legitimate use", "without consent", "employment"]),
    Section("8", "General obligations of a Data Fiduciary", "II — Obligations",
            "The core accountability section. The Data Fiduciary remains responsible for "
            "compliance even when a Data Processor acts on its behalf, must ensure data accuracy, "
            "implement reasonable security safeguards, notify breaches, erase data when the "
            "purpose is served, and publish grievance contact details.",
            ["Accountability persists through processors and sub-processors",
             "Implement reasonable security safeguards",
             "Notify the Board and affected Data Principals of a breach",
             "Erase personal data once the purpose is served or consent withdrawn",
             "Publish a Data Protection Officer / grievance contact"],
            keywords=["security safeguards", "breach notification", "erasure",
                      "accountability", "8(5)", "8(6)", "8(7)"]),
    Section("9", "Processing of personal data of children", "II — Obligations",
            "Requires verifiable parental consent before processing a child's personal data, and "
            "prohibits tracking, behavioural monitoring and targeted advertising directed at "
            "children.",
            ["Implement verifiable parental consent",
             "Disable behavioural tracking and targeted ads for children"],
            keywords=["children", "parental consent", "age verification", "minors"]),
    Section("10", "Additional obligations of Significant Data Fiduciaries", "II — Obligations",
            "Entities notified as Significant Data Fiduciaries carry heavier duties: appoint an "
            "India-based Data Protection Officer, appoint an independent data auditor, and carry "
            "out periodic Data Protection Impact Assessments and audits.",
            ["Appoint a DPO based in India",
             "Commission an independent data audit",
             "Run periodic DPIAs"],
            applies_to="Significant Data Fiduciary",
            keywords=["significant data fiduciary", "SDF", "DPO", "DPIA", "audit"]),
    Section("11", "Right to access information", "III — Rights",
            "Data Principals may request a summary of their personal data being processed, the "
            "processing activities, and the identities of other Fiduciaries and Processors with "
            "whom it has been shared.",
            ["Build a DSAR intake and fulfilment workflow"],
            applies_to="Data Principal", keywords=["DSAR", "access request", "subject access"]),
    Section("12", "Right to correction and erasure", "III — Rights",
            "Data Principals may require correction, completion, updating and erasure of their "
            "personal data.",
            ["Support correction and erasure requests end to end"],
            applies_to="Data Principal", keywords=["erasure", "correction", "right to be forgotten"]),
    Section("13", "Right of grievance redressal", "III — Rights",
            "Data Principals must have a readily available means of grievance redressal with the "
            "Data Fiduciary, which must be exhausted before approaching the Board.",
            ["Publish and staff a grievance channel with defined response times"],
            applies_to="Data Principal", keywords=["grievance", "complaint", "redressal"]),
    Section("14", "Right to nominate", "III — Rights",
            "A Data Principal may nominate another individual to exercise their rights in the "
            "event of death or incapacity.",
            ["Support nominee registration"],
            applies_to="Data Principal", keywords=["nomination", "nominee"]),
    Section("15", "Duties of a Data Principal", "III — Rights",
            "Places duties on individuals too, including not impersonating another person, not "
            "suppressing material information, and not filing false or frivolous complaints.",
            [], applies_to="Data Principal", keywords=["duties", "false complaint"]),
    Section("16", "Processing personal data outside India", "IV — Transfers",
            "Permits cross-border transfer of personal data except to countries restricted by the "
            "Central Government, and preserves stricter sectoral localisation rules (such as the "
            "RBI's payment-data directive).",
            ["Track restricted-country notifications",
             "Sectoral localisation rules continue to apply on top of the Act"],
            keywords=["cross-border", "transfer", "localisation", "data localization"]),
    Section("17", "Exemptions", "IV — Transfers",
            "Sets out exemptions, including for enforcement of legal rights, judicial functions, "
            "prevention and investigation of offences, and processing of non-residents' data under "
            "foreign contracts — plus the power to exempt State instrumentalities.",
            ["Document any exemption relied upon"],
            keywords=["exemption", "exempt", "startup exemption"]),
    Section("27", "Powers and functions of the Board", "V — Data Protection Board",
            "Empowers the Data Protection Board of India to inquire into breaches and complaints, "
            "direct urgent remedial or mitigation measures, and impose monetary penalties.",
            ["Prepare for Board inquiry: evidence, logs, breach records"],
            applies_to="Data Protection Board", keywords=["board", "inquiry", "powers", "DPBI"]),
    Section("33", "Penalties and adjudication", "VII — Penalties",
            "Empowers the Board to impose monetary penalties after inquiry, having regard to the "
            "nature, gravity and duration of the breach, the type of personal data affected, "
            "repetitive conduct, and any mitigation taken. Amounts are set out in the Schedule.",
            ["Penalty exposure is per-breach, not capped per organisation",
             "Mitigation and cooperation are expressly relevant factors"],
            keywords=["penalty", "fine", "adjudication", "schedule", "250 crore"]),
]

# Schedule penalties — widely cited, so worth surfacing as structured data.
SCHEDULE_PENALTIES = [
    ("Failure to take reasonable security safeguards to prevent a breach", "₹250 crore"),
    ("Failure to notify the Board or affected Data Principals of a breach", "₹200 crore"),
    ("Breach of obligations relating to children's personal data", "₹200 crore"),
    ("Breach of additional obligations of a Significant Data Fiduciary", "₹150 crore"),
    ("Breach of the duties of a Data Principal", "₹10,000"),
    ("Breach of terms of a voluntary undertaking", "As applicable to the breach"),
    ("Residuary — breach of any other provision", "₹50 crore"),
]

SECTION_BY_NUMBER = {s.number: s for s in SECTIONS}

_SECTION_REF = re.compile(
    r"(?:section|sec\.?|s\.)\s*(\d{1,2})(?:\s*\(\s*\d+\s*\))?", re.I)


def sections_cited_in(text: str) -> list[Section]:
    """Find which DPDPA sections a case's statute reference points at."""
    if not text:
        return []
    low = text.lower()
    if "dpdp" not in low and "digital personal data" not in low:
        # Only map references that are actually to the DPDP Act — "IT Act
        # Section 43A" must not be attributed to DPDPA Section 43.
        if not _SECTION_REF.search(low) or any(
                k in low for k in ("it act", "information technology act",
                                   "gdpr", "competition act", "constitution")):
            return []
    out: list[Section] = []
    for m in _SECTION_REF.finditer(text):
        sec = SECTION_BY_NUMBER.get(m.group(1))
        if sec and sec not in out:
            out.append(sec)
    return out

"""
PII scrubber — the [PII Scrub] stage in the pipeline diagram. Regex-based for
the prototype (fast, no extra Lambda weight); swap in AWS Comprehend PII
detection or Presidio if you need NER-grade PII coverage later.

Only scrubs PII belonging to *individuals* (investor PAN, Aadhaar, personal
email/phone) — it deliberately does NOT touch ISIN, AMFI codes, or company
identifiers, which look similar but are legitimate entities for the graph.
"""
import re
from dataclasses import replace
from typing import List

from ingestion.parsers.base import ParsedSection

_PATTERNS = {
    "PAN": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "AADHAAR": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE": re.compile(r"\b(?:\+91[-\s]?)?[6-9]\d{9}\b"),
}

# ISIN looks like PAN-ish alphanumeric but must never be scrubbed — guard explicitly.
_ISIN_GUARD = re.compile(r"\bIN[EF][A-Z0-9]{9}\b")


def scrub_text(text: str) -> tuple[str, dict]:
    """Returns (scrubbed_text, counts_by_type). Replaces matches with [REDACTED_<TYPE>]."""
    counts = {}
    isin_spans = {(m.start(), m.end()) for m in _ISIN_GUARD.finditer(text)}

    def _redact(label: str, pattern: re.Pattern, s: str) -> str:
        def repl(match):
            if (match.start(), match.end()) in isin_spans:
                return match.group()  # never touch ISINs
            counts[label] = counts.get(label, 0) + 1
            return f"[REDACTED_{label}]"

        return pattern.sub(repl, s)

    for label, pattern in _PATTERNS.items():
        text = _redact(label, pattern, text)
    return text, counts


def scrub_section(section: ParsedSection) -> ParsedSection:
    if section.route_hint == "structured":
        return section  # structured rows go through resolver.py's own field-level checks, not free-text scrub
    scrubbed_text, counts = scrub_text(section.text)
    if counts:
        print(f"[pii] {section.source_file} :: {section.heading} -> redacted {counts}")
    return replace(section, text=scrubbed_text, metadata={**section.metadata, "pii_redactions": counts})


def scrub_sections(sections: List[ParsedSection]) -> List[ParsedSection]:
    return [scrub_section(s) for s in sections]
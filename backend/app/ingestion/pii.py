"""WS2 — PII scrubber: regex for PAN / phone / email + light name masking.

Runs on chunk text before embedding so no PII lands in Qdrant. Entity names
required by the domain (schemes, issuers, analysts in the alias seed) are
whitelisted — analysts are business entities in this graph, not private PII.
"""
import json
import re
from pathlib import Path

# Indian PAN: 5 letters, 4 digits, 1 letter
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
# Indian mobile numbers (+91 optional) and generic 10-digit runs with separators
_PHONE_RE = re.compile(r"(?:\+91[\-\s]?)?\b[6-9]\d{4}[\-\s]?\d{5}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
# Aadhaar-like 12-digit numbers grouped in 4s
_AADHAAR_RE = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")


def _load_whitelist(alias_seed_path: Path | None) -> set[str]:
    names: set[str] = set()
    if alias_seed_path and alias_seed_path.exists():
        data = json.loads(alias_seed_path.read_text(encoding="utf-8"))
        for entity in data.get("entities", []):
            names.add(entity["canonical_name"].lower())
            names.update(a.lower() for a in entity.get("aliases", []))
    return names


class PiiScrubber:
    def __init__(self, alias_seed_path: Path | None = None):
        self._whitelist = _load_whitelist(alias_seed_path)

    def scrub(self, text: str) -> tuple[str, bool]:
        """Returns (scrubbed_text, was_modified)."""
        original = text
        text = _PAN_RE.sub("[PAN-REDACTED]", text)
        text = _AADHAAR_RE.sub("[ID-REDACTED]", text)
        text = _PHONE_RE.sub("[PHONE-REDACTED]", text)

        def _mask_email(m: re.Match) -> str:
            addr = m.group(0)
            # Keep internal business emails' domain visible, mask the local part.
            local, _, domain = addr.partition("@")
            if local.lower() in self._whitelist:
                return addr
            return f"[EMAIL-REDACTED]@{domain}"

        text = _EMAIL_RE.sub(_mask_email, text)
        return text, text != original

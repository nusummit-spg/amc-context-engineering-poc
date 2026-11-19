"""Wave 4.0 (TDS-40 E3): numeric-safe answer composition.

STRUCTURED answers are rendered by the server from the verified FinResult: a table, a one-sentence summary
whose numbers are filled from result slots, the as-of period, applied filters, exclusions and the metric
disclosure. No LLM sees or writes these numbers (ADR40-02).

For DOCUMENT answers, numeric_guardrail() drops any sentence that states a number which appears neither in
the cited evidence nor in the question; if nothing grounded remains the caller abstains (UNGROUNDED_NUMBER).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

ABSTAIN_TEXT = {
    "STRUCTURED_SOURCE_UNAVAILABLE": "Verified fund data is not available right now, so I can't give this figure. "
                                     "No estimate has been substituted.",
    "INCOMPATIBLE_PERIODS": "The verified dataset doesn't hold that figure for the period or date asked.",
    "UNSUPPORTED_METRIC": "That figure isn't one of the approved fund-data metrics.",
    "AMBIGUOUS_QUERY": "I need one detail to answer exactly.",
    "NO_MATCH": "Nothing in the verified dataset matches that.",
    "UNGROUNDED_NUMBER": "I couldn't ground the figures in an answer to this in the verified sources, so I haven't "
                         "given one.",
    "OUT_OF_SCOPE_ADVICE": "I can't give investment advice or recommendations.",
    "SERVING_DENIED": "Verified answers are unavailable at the moment. Please try again later or contact support.",
}

_UNIT_SUFFIX = {"INR_CRORE": " Cr", "PERCENT": "%"}
_UNIT_PREFIX = {"INR_CRORE": "₹ ", "INR_PER_UNIT": "₹ "}


def format_inr(value: str, places: int = 2) -> str:
    """'123456.780000' -> '1,23,456.78' (Indian digit grouping, half-even rounding to `places`)."""
    try:
        d = Decimal(str(value)).quantize(Decimal(1).scaleb(-places))
    except (InvalidOperation, ValueError):
        return str(value)
    sign = "-" if d < 0 else ""
    whole, _, frac = format(abs(d), "f").partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}{whole}.{frac}" if places else f"{sign}{whole}"


def _cell(value, column: dict) -> str:
    unit = column.get("unit")
    if unit in ("INR_CRORE",):
        return f"{_UNIT_PREFIX[unit]}{format_inr(value, 2)}{_UNIT_SUFFIX[unit]}"
    if unit == "INR_PER_UNIT":
        return f"₹ {format_inr(value, 4)}"
    if unit == "PERCENT":
        return f"{value}%"
    if unit == "COUNT":
        return format_inr(value, 0)
    return str(value).replace("|", "/")


def _summary(result) -> str:
    r = result.rows[0] if result.rows else None
    if r is None:
        return ""
    if result.intent == "NAV_LOOKUP":
        return f"The NAV of **{r[0]}** (AMFI code {r[1]}) on {r[4]} is **₹ {format_inr(r[3], 4)}**."
    if result.intent == "TOP_AMC_AAUM":
        return (f"**{r[1]}** has the highest AAUM in this dataset for {result.as_of['aaum_period']}: "
                f"**₹ {format_inr(r[2])} Cr** ({r[3]}% of the dataset's AAUM for the period).")
    if result.intent == "TOP_SCHEME_AAUM":
        scope = f" within {result.filters_applied['amc']}" if result.filters_applied.get("amc") else ""
        return (f"**{r[1]}**{scope} has the highest AAUM for {result.as_of['aaum_period']}: "
                f"**₹ {format_inr(r[3])} Cr** across {r[4]} plans/options.")
    if result.intent == "CATEGORY_AAUM_SHARE":
        return (f"**{r[1]}** is the largest category for {result.as_of['aaum_period']}: "
                f"**₹ {format_inr(r[2])} Cr** ({r[3]}% of the dataset's AAUM).")
    if result.intent == "COUNT_SCHEMES":
        scope = f" for {result.filters_applied['amc']}" if result.filters_applied.get("amc") else ""
        return f"This dataset holds **{format_inr(r[0], 0)}** schemes ({format_inr(r[1], 0)} plans/options){scope}."
    if result.intent == "DATASET_SUMMARY":
        return (f"The active dataset holds **{format_inr(r[0], 0)}** source rows ({format_inr(r[1], 0)} valid, "
                f"{format_inr(r[2], 0)} rejected) covering {format_inr(r[3], 0)} AMCs and {format_inr(r[4], 0)} schemes.")
    return ""


def render_structured(result) -> str:
    cols = result.columns
    lines = [_summary(result), ""]
    lines.append("| " + " | ".join(c["label"] for c in cols) + " |")
    lines.append("|" + "|".join("---" for _ in cols) + "|")
    for row in result.rows:
        lines.append("| " + " | ".join(_cell(v, c) for v, c in zip(row, cols)) + " |")
    lines.append("")
    if result.as_of.get("aaum_period"):
        lines.append(f"**As of:** AAUM for {result.as_of['aaum_period']}.")
    elif result.as_of.get("nav_date"):
        lines.append(f"**As of:** NAV date {result.as_of['nav_date']}.")
    shown = {k: v for k, v in result.filters_applied.items() if k not in ("plan_option_id",)}
    if shown:
        lines.append("**Applied:** " + ", ".join(f"{k.replace('_', ' ')} = {v}" for k, v in shown.items()) + ".")
    excl = {k: v for k, v in result.exclusions.items() if v}
    if excl:
        lines.append("**Excluded:** " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in excl.items()) + ".")
    lines.append(f"_{result.disclosure}_")
    lines.append(f"Source: verified dataset `{result.dataset_version}` (receipt `{result.receipt_id}`).")
    return "\n".join(line for line in lines if line is not None).strip()


def structured_rows(result) -> list[dict]:
    return [{c["id"]: v for c, v in zip(result.columns, row)} for row in result.rows]


def abstention_text(code: str, message: str | None, options: list | None = None) -> str:
    base = ABSTAIN_TEXT.get(code, ABSTAIN_TEXT["SERVING_DENIED"])
    text = base if not message or message == base else f"{base} {message}"
    if options:
        text += "\n\n" + "\n".join(f"- {o}" for o in options)
    return text


# ---------------------------------------------------------------------------------------- numeric guardrail

_NUM = re.compile(r"(?<![\w.])(?:₹\s*)?(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(%|cr\b|crore|lakh)?", re.I)
_CITATION_MARK = re.compile(r"\[\d{1,3}(?:\s*,\s*\d{1,3})*\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z*_#(\[])|\n+")


def _norm_num(text: str) -> str | None:
    try:
        d = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    return format(d.normalize(), "f")


def numbers_in(text: str) -> set[str]:
    out = set()
    for m in _NUM.finditer(_CITATION_MARK.sub(" ", text or "")):
        n = _norm_num(m.group(1))
        if n is not None:
            out.add(n)
    return out


def numeric_guardrail(answer: str, evidence_texts: list[str], question: str = "") -> tuple[str, int]:
    """Drop sentences whose numbers are absent from the evidence and the question. Returns (text, dropped)."""
    allowed = numbers_in(question)
    for t in evidence_texts or []:
        allowed |= numbers_in(t)
    kept, dropped = [], 0
    for sentence in _SENTENCE.split(answer or ""):
        if not sentence.strip():
            continue
        nums = numbers_in(sentence)
        # single-digit list markers ("1.", "2)") and citation marks are not claims
        claims = {n for n in nums if not (len(n) == 1 and re.match(rf"^\s*[-*]?\s*{n}[.)]", sentence))}
        if claims - allowed:
            dropped += 1
            continue
        kept.append(sentence.strip())
    return "\n".join(kept).strip(), dropped


__all__ = ["render_structured", "structured_rows", "abstention_text", "numeric_guardrail", "numbers_in",
           "format_inr", "ABSTAIN_TEXT"]

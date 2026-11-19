"""Wave 4.0 (TDS-40 E3): typed intent router, Stage A (deterministic).

Decides, BEFORE any retrieval or LLM call, which authority may answer a question:

    STRUCTURED  a FinPlan the verified fin plane executes exactly
    DOCUMENT    regulatory / narrative question for the existing verified graph + vector path
    ABSTAIN     structured-looking but not answerable from approved metrics, or investment advice
    CLARIFY     a period or entity that cannot be resolved without guessing

The router never produces SQL, never invents a default filter, and prefers asking over guessing. A question it
does not recognise as structured goes to DOCUMENT; a question that IS about fund numbers but that it cannot map to
an approved metric is ABSTAINed, so it can never be answered approximately by the LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from amc_publication.fin_query40 import FinPlan, norm_text

KIND_STRUCTURED, KIND_DOCUMENT, KIND_ABSTAIN, KIND_CLARIFY = "STRUCTURED", "DOCUMENT", "ABSTAIN", "CLARIFY"
DEFAULT_LIMIT, MAX_LIMIT = 5, 50

SUPPORTED_EXAMPLES = [
    "Top 5 AMCs by AAUM for January - March 2026",
    "Top 10 schemes of <AMC> by AAUM",
    "AAUM share by scheme category",
    "NAV of scheme code 100033",
    "How many schemes does <AMC> have?",
    "Dataset summary",
]


@dataclass
class RoutePlan:
    kind: str
    plan: FinPlan | None = None
    code: str | None = None
    message: str | None = None
    options: list = field(default_factory=list)
    reasons: list = field(default_factory=list)


_ADVICE = re.compile(
    r"\b(should i|shall i|should we|which (mutual )?fund should|recommend|suggest (a|some|me)|best (mutual )?funds?\b|"
    r"good time to (buy|invest|redeem)|worth investing|is it (a )?good (time|investment|idea)|where (should|can) i invest|"
    r"switch (my|from)|portfolio for me)")
_REGULATORY = re.compile(
    r"\b(sebi|amfi guideline|circular|regulation|regulatory|rule|rules|guideline|guidelines|mandate|mandatory|"
    r"compliance|comply|permitted|allowed to|requirement|requirements|disclos\w*|master circular|limit on|cap on|"
    r"framework|categori[sz]ation norms|riskometer|ter slab|guarantee\w*|assured)\b")
# Explicit fund-data nouns only: generic words like "top" or "portfolio" alone must not pull a narrative
# question into the structured path (where it would be abstained).
_FUND_NUMBERS = re.compile(
    r"\b(nav|navs|net asset value|aaum|aum|assets under management|scheme code|amfi code|"
    r"how many (schemes|funds|plans)|number of (schemes|funds|plans)|market share|"
    r"returns?|cagr|xirr|expense ratio|sharpe|volatility|holdings|records|rows|dataset)\b")
# Only unambiguous metric words: "alpha", "rating", "benchmark" also occur in real scheme names
# (e.g. "... Alpha 50 ETF") and must not abstain a NAV lookup for such a scheme.
_UNSUPPORTED = re.compile(
    r"\b(returns?|cagr|xirr|performance|expense ratio|ter\b|sharpe( ratio)?|sortino|volatility|standard deviation|"
    r"tracking error|holdings|portfolio composition|exit load|fund manager)\b")
_AUM = re.compile(r"\b(aaum|aum|assets under management|average aum)\b")
_NAV = re.compile(r"\b(nav|net asset value)\b")
_RANK = re.compile(r"\b(top|largest|biggest|highest|lowest|leading|rank|ranking|which)\b")
_CATEGORY = re.compile(r"\b(category|categories|asset class|asset classes|breakdown|distribution|share by|split by)\b")
_AMC_WORD = re.compile(r"\b(amcs?|fund houses?|asset management compan(y|ies)|mutual fund houses?)\b")
_SCHEME_WORD = re.compile(r"\b(schemes?|funds?)\b")
_COUNT = re.compile(r"\b(how many|number of|count of)\b")
_SUMMARY = re.compile(r"\b(dataset summary|summary of (the )?dataset|how many (records|rows)|what data)\b")
_CODE = re.compile(r"\b(?:scheme code|amfi code|code)\s*[:#]?\s*(\d{4,8})\b|\b(\d{5,6})\b")

_MONTHS = {m[:3]: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"), start=1)}
_MONTH_RANGE = re.compile(r"\b([a-z]{3})[a-z]*\s*(?:-|to|–)\s*([a-z]{3})[a-z]*\s+(\d{4})\b")
_FY_QUARTER = re.compile(r"\bq([1-4])\s*fy\s*'?(\d{2,4})\b|\bfy\s*'?(\d{2,4})\s*q([1-4])\b")
_BARE_QUARTER = re.compile(r"\bq([1-4])\s+(\d{4})\b|\b(\d{4})\s+q([1-4])\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY_DATE = re.compile(r"\b(\d{1,2})[-/ ]([a-z]{3,9}|\d{1,2})[-/ ,]+(\d{4})\b")
_AMC_STOP = {"asset", "management", "company", "limited", "ltd", "mutual", "fund", "amc", "india", "pvt", "private",
             "investment", "managers", "manager", "trustee", "co", "the", "and", "of", "funds", "services"}


def _fy_year(text: str) -> int:
    y = int(text)
    return 2000 + y if y < 100 else y


def _fy_quarter_start(q: int, fy_end_year: int) -> date:
    # Indian financial year FYyyyy runs April (yyyy-1) to March (yyyy).
    return {1: date(fy_end_year - 1, 4, 1), 2: date(fy_end_year - 1, 7, 1),
            3: date(fy_end_year - 1, 10, 1), 4: date(fy_end_year, 1, 1)}[q]


def parse_period(q: str) -> tuple[date | None, RoutePlan | None]:
    m = _MONTH_RANGE.search(q)
    if m and m.group(1) in _MONTHS and m.group(2) in _MONTHS:
        return date(int(m.group(3)), _MONTHS[m.group(1)], 1), None
    m = _FY_QUARTER.search(q)
    if m:
        quarter = int(m.group(1) or m.group(4))
        return _fy_quarter_start(quarter, _fy_year(m.group(2) or m.group(3))), None
    m = _BARE_QUARTER.search(q)
    if m:
        quarter, year = int(m.group(1) or m.group(4)), int(m.group(2) or m.group(3))
        cal = date(year, 3 * (quarter - 1) + 1, 1)
        fy = _fy_quarter_start(quarter, year)
        fmt = lambda d: f"{d.strftime('%B')} {d.year} quarter"   # noqa: E731
        return None, RoutePlan(KIND_CLARIFY, code="AMBIGUOUS_QUERY",
                               message=f"Q{quarter} {year} can mean a calendar or an Indian financial-year quarter. Which one?",
                               options=[f"Calendar Q{quarter} {year} (starting {fmt(cal)})",
                                        f"FY{str(year)[2:]} Q{quarter} (starting {fmt(fy)})"],
                               reasons=["bare quarter is ambiguous"])
    return None, None


def parse_date(q: str) -> date | None:
    m = _ISO_DATE.search(q)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _DMY_DATE.search(q)
    if m:
        day, mon, year = m.group(1), m.group(2), m.group(3)
        try:
            month = int(mon) if mon.isdigit() else _MONTHS.get(mon[:3])
            return date(int(year), int(month), int(day)) if month else None
        except (TypeError, ValueError):
            return None
    return None


def _limit(q: str) -> int:
    m = re.search(r"\btop\s+(\d{1,3})\b", q) or re.search(r"\b(\d{1,3})\s+(largest|biggest|leading|top)\b", q)
    return max(1, min(MAX_LIMIT, int(m.group(1)))) if m else DEFAULT_LIMIT


_COMMON_WORD_AMC_KEYS = {"bank", "old", "trust", "union", "choice", "wealth", "quant", "capital", "money"}


def match_amc(q: str, amcs: list[str]) -> tuple[str | None, list[str]]:
    """Return (amc_name, ambiguous_candidates) from each AMC's distinctive leading token.

    An AMC whose leading token is an ordinary word ("Union", "Trust", "Old Bridge", "Bank of India") only matches
    as a phrase ("union amc", "old bridge", "bank of india"), so "banking schemes" never becomes an AMC filter.
    """
    nq = " " + norm_text(q) + " "
    tokens = set(nq.split())
    hits = []
    for name in amcs:
        raw = norm_text(name).split()
        distinctive = [t for t in raw if t not in _AMC_STOP]
        if not distinctive or distinctive[0] not in tokens:
            continue
        key = distinctive[0]
        if key in _COMMON_WORD_AMC_KEYS:
            phrase = " ".join(raw[:raw.index(key) + 2]) if raw.index(key) + 1 < len(raw) else key
            if f" {phrase} " not in nq and not any(f" {key} {w} " in nq for w in ("amc", "mutual", "asset", "fund house")):
                continue
        hits.append(name)
    if len(hits) == 1:
        return hits[0], []
    return None, hits


def _scheme_text(q: str) -> str | None:
    m = re.search(r"\b(?:nav|net asset value)\s+(?:of|for)\s+(?:the\s+)?(.+?)(?:\s+(?:on|as of|as on|for)\s+.*)?[?.]*$", q)
    if not m:
        return None
    text = re.sub(r"\b(scheme|plan|today|latest|current)\b", " ", m.group(1)).strip(" ?.")
    return text or None


def route(query: str, catalog: dict | None = None) -> RoutePlan:
    q = (query or "").lower().strip()
    catalog = catalog or {}
    if _ADVICE.search(q):
        return RoutePlan(KIND_ABSTAIN, code="OUT_OF_SCOPE_ADVICE",
                         message="This assistant provides factual information for internal use and does not give "
                                 "investment advice or recommendations.", reasons=["advice request"])
    if _REGULATORY.search(q):
        return RoutePlan(KIND_DOCUMENT, reasons=["regulatory question"])
    if _SUMMARY.search(q):
        return RoutePlan(KIND_STRUCTURED, plan=FinPlan("DATASET_SUMMARY"), reasons=["dataset summary"])
    if not _FUND_NUMBERS.search(q):
        return RoutePlan(KIND_DOCUMENT, reasons=["no fund-data signal"])
    if _UNSUPPORTED.search(q):
        return RoutePlan(KIND_ABSTAIN, code="UNSUPPORTED_METRIC",
                         message="That figure is not in the approved fund dataset. Supported questions cover NAV, "
                                 "AAUM rankings and shares, and scheme counts.",
                         options=SUPPORTED_EXAMPLES, reasons=["metric not in registry"])

    period, clarify = parse_period(q)
    if clarify:
        return clarify
    amc, amc_candidates = match_amc(q, catalog.get("amcs", []))
    if amc_candidates:
        return RoutePlan(KIND_CLARIFY, code="AMBIGUOUS_QUERY", message="Which AMC do you mean?",
                         options=sorted(amc_candidates)[:8], reasons=["several AMCs match"])

    if _NAV.search(q):
        if _RANK.search(q) and not _CODE.search(q):
            return RoutePlan(KIND_ABSTAIN, code="UNSUPPORTED_METRIC",
                             message="NAV per unit is not comparable across schemes (it depends on launch date and "
                                     "option), so NAV rankings are not offered. Ask for the NAV of a specific scheme.",
                             options=["NAV of scheme code 100033"], reasons=["nav ranking"])
        nav_date = parse_date(q)
        m = _CODE.search(q)
        if m:
            return RoutePlan(KIND_STRUCTURED, plan=FinPlan("NAV_LOOKUP", scheme_code=m.group(1) or m.group(2),
                                                           nav_date=nav_date), reasons=["nav by code"])
        text = _scheme_text(q)
        if text:
            return RoutePlan(KIND_STRUCTURED, plan=FinPlan("NAV_LOOKUP", scheme_text=text, nav_date=nav_date),
                             reasons=["nav by name"])
        return RoutePlan(KIND_CLARIFY, code="AMBIGUOUS_QUERY",
                         message="Which scheme? Give its name with plan and option, or its AMFI scheme code.",
                         reasons=["nav without scheme"])

    if _AUM.search(q) or "market share" in q:
        if _CATEGORY.search(q):
            return RoutePlan(KIND_STRUCTURED, plan=FinPlan("CATEGORY_AAUM_SHARE", period_start=period,
                                                           limit=max(_limit(q), 10)), reasons=["category share"])
        if _AMC_WORD.search(q) and not amc:
            return RoutePlan(KIND_STRUCTURED, plan=FinPlan("TOP_AMC_AAUM", period_start=period, limit=_limit(q)),
                             reasons=["amc ranking"])
        if _SCHEME_WORD.search(q) or amc:
            return RoutePlan(KIND_STRUCTURED, plan=FinPlan("TOP_SCHEME_AAUM", period_start=period, amc_text=amc,
                                                           limit=_limit(q)), reasons=["scheme ranking"])
        return RoutePlan(KIND_CLARIFY, code="AMBIGUOUS_QUERY",
                         message="AAUM by AMC, by scheme, or by category?",
                         options=["Top AMCs by AAUM", "Top schemes by AAUM", "AAUM share by category"],
                         reasons=["aaum without grouping"])

    if _COUNT.search(q) and _SCHEME_WORD.search(q):
        return RoutePlan(KIND_STRUCTURED, plan=FinPlan("COUNT_SCHEMES", amc_text=amc), reasons=["scheme count"])

    return RoutePlan(KIND_ABSTAIN, code="UNSUPPORTED_METRIC",
                     message="I could not match this to an approved fund-data question.",
                     options=SUPPORTED_EXAMPLES, reasons=["fund-data signal without a supported shape"])


__all__ = ["RoutePlan", "route", "parse_period", "parse_date", "match_amc", "SUPPORTED_EXAMPLES",
           "KIND_STRUCTURED", "KIND_DOCUMENT", "KIND_ABSTAIN", "KIND_CLARIFY"]

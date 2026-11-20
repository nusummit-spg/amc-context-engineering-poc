"""Wave 4.0 (TDS-40 E1/E3): typed, parameterized queries over ONE pinned fin dataset version.

There is no free-form SQL. Each FinPlan intent maps to one fixed SQLAlchemy Core query; tenant and dataset
version come from the FinPin (never from the plan) and are applied in every statement. Values come back as
exact Decimal strings with units, the applied filters and period are echoed, exclusions are counted, and the
result carries a SHA-256 over its normalized content plus a hash over the source-row anchors that produced it.

Errors are typed FinQueryError codes (TDS-40 §5.2). A caller must turn them into an abstention; it must never
answer the same question from vector search or an LLM instead.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from .fin40 import (DOMAIN, METRIC_REGISTRY_V1, FinAaumObservation, FinDatasetVersion, FinNavObservation,
                    FinPin, FinPlanOption, micro_to_decimal)
from .types import sha256_json

INTENTS = ("NAV_LOOKUP", "TOP_AMC_AAUM", "TOP_SCHEME_AAUM", "CATEGORY_AAUM_SHARE", "COUNT_SCHEMES",
           "DATASET_SUMMARY")
MAX_LIMIT = 50
MAX_CANDIDATES = 8


class FinQueryError(Exception):
    def __init__(self, code: str, message: str, *, options: list | None = None):
        super().__init__(message)
        self.code, self.message, self.options = code, message, list(options or [])


@dataclass(frozen=True)
class FinPlan:
    intent: str
    scheme_code: str | None = None
    scheme_text: str | None = None          # name fragment to resolve (NAV_LOOKUP)
    nav_date: date | None = None
    period_start: date | None = None        # AAUM period; None = the dataset's only period, else AMBIGUOUS
    amc_text: str | None = None
    limit: int = 5

    def as_dict(self) -> dict:
        return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in self.__dict__.items() if v is not None}


@dataclass
class FinResult:
    intent: str
    dataset_version: str
    receipt_id: str
    metric_ids: list
    columns: list
    rows: list
    as_of: dict
    filters_applied: dict
    exclusions: dict
    disclosure: str
    row_anchor_count: int
    anchor_set_sha256: str
    result_set_hash: str = ""
    plan: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


# ---------------------------------------------------------------------------------------------- helpers

def norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


_NAME_STOP = {"fund", "plan", "scheme", "the", "option"}


def _name_words(text: str) -> frozenset:
    return frozenset(t for t in norm_text(text).split() if t not in _NAME_STOP)


def _dec(micro) -> str:
    return format(micro_to_decimal(int(micro)), "f")


def _pct(part: int, whole: int) -> str:
    if not whole:
        return "0.00"
    return format((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN), "f")


def _anchors_hash(ids) -> tuple[int, str]:
    ids = sorted(ids)
    return len(ids), hashlib.sha256("\n".join(ids).encode()).hexdigest()


def _base(model, pin: FinPin):
    return (model.dataset_version == pin.dataset_version) & (model.tenant == pin.tenant)


def _registry(metric: str) -> dict:
    return METRIC_REGISTRY_V1["metrics"][metric]


def _resolve_period(s: Session, pin: FinPin, start: date | None) -> tuple[date, date, str]:
    periods = s.execute(select(FinAaumObservation.period_start, FinAaumObservation.period_end,
                               FinAaumObservation.period_label)
                        .where(_base(FinAaumObservation, pin)).distinct()
                        .order_by(FinAaumObservation.period_start)).all()
    if not periods:
        raise FinQueryError("STRUCTURED_SOURCE_UNAVAILABLE", "This dataset version holds no AAUM figures.")
    if start is None:
        if len(periods) > 1:
            raise FinQueryError("AMBIGUOUS_QUERY", "Which AAUM period do you mean?",
                                options=[p.period_label for p in periods])
        return periods[0]
    for p in periods:
        if p.period_start == start:
            return p
    raise FinQueryError("INCOMPATIBLE_PERIODS",
                        "This dataset has no AAUM for that period. Available: "
                        + ", ".join(p.period_label for p in periods) + ".",
                        options=[p.period_label for p in periods])


def _resolve_amc(s: Session, pin: FinPin, text: str) -> tuple[str, str]:
    want = norm_text(text)
    amcs = s.execute(select(FinPlanOption.amc_id, FinPlanOption.amc_name)
                     .where(_base(FinPlanOption, pin)).distinct()).all()
    hits = [a for a in amcs if want and want in norm_text(a.amc_name)]
    if len(hits) == 1:
        return hits[0].amc_id, hits[0].amc_name
    if not hits:
        raise FinQueryError("NO_MATCH", f"No AMC in this dataset matches '{text}'.")
    raise FinQueryError("AMBIGUOUS_QUERY", f"'{text}' matches more than one AMC.",
                        options=sorted(a.amc_name for a in hits)[:MAX_CANDIDATES])


def _aaum_exclusions(s: Session, pin: FinPin, start: date, amc_id: str | None = None) -> dict:
    po_q = select(func.count()).select_from(FinPlanOption).where(_base(FinPlanOption, pin))
    with_q = (select(func.count()).select_from(FinAaumObservation)
              .where(_base(FinAaumObservation, pin), FinAaumObservation.period_start == start,
                     FinAaumObservation.valid_for_aggregation.is_(True)))
    if amc_id:
        po_q = po_q.where(FinPlanOption.amc_id == amc_id)
        with_q = with_q.where(FinAaumObservation.amc_id == amc_id)
    total, included = s.scalar(po_q), s.scalar(with_q)
    rejected = s.scalar(select(FinDatasetVersion.rejected_rows)
                        .where(FinDatasetVersion.dataset_version == pin.dataset_version))
    return {"plan_options_without_aaum_for_period": int(total - included), "rejected_source_rows": int(rejected or 0)}


# ---------------------------------------------------------------------------------------------- intents

def _nav_lookup(s: Session, pin: FinPin, plan: FinPlan) -> FinResult:
    q = select(FinPlanOption).where(_base(FinPlanOption, pin))
    if plan.scheme_code:
        candidates = list(s.scalars(q.where(FinPlanOption.scheme_code == plan.scheme_code.strip())))
    elif plan.scheme_text:
        # Whole words, not substrings: "it" must not match inside "capital", nor "cap" inside "midcap" (E5 GS-FIN).
        tokens = _name_words(plan.scheme_text)
        if not tokens:
            raise FinQueryError("AMBIGUOUS_QUERY", "Which scheme do you mean?")
        candidates = [p for p in s.scalars(q) if tokens <= _name_words(p.plan_option_name + " " + p.scheme_name)]
        # The exact full plan/option name is not ambiguous even when a longer name also contains all its words.
        exact = [p for p in candidates if _name_words(p.plan_option_name) == tokens]
        if len(exact) == 1:
            candidates = exact
    else:
        raise FinQueryError("AMBIGUOUS_QUERY", "Which scheme (name or AMFI scheme code) do you mean?")
    if not candidates:
        raise FinQueryError("NO_MATCH", "No scheme in this dataset matches that description.")
    if len(candidates) > 1:
        raise FinQueryError("AMBIGUOUS_QUERY", "Several plans/options match. Which one?",
                            options=[f"{p.plan_option_name} (code {p.scheme_code})"
                                     for p in sorted(candidates, key=lambda p: p.plan_option_name)][:MAX_CANDIDATES])
    po = candidates[0]
    nav = s.scalar(select(FinNavObservation).where(_base(FinNavObservation, pin),
                                                   FinNavObservation.plan_option_id == po.plan_option_id))
    if nav is None:
        raise FinQueryError("NO_MATCH", f"This dataset has no NAV for {po.plan_option_name}.")
    if plan.nav_date and plan.nav_date != nav.nav_date:
        raise FinQueryError("INCOMPATIBLE_PERIODS",
                            f"This dataset holds the NAV of {po.plan_option_name} for {nav.nav_date.isoformat()} "
                            f"only, not {plan.nav_date.isoformat()}.")
    count, anchors = _anchors_hash([nav.source_row_id])
    return FinResult(
        intent=plan.intent, dataset_version=pin.dataset_version, receipt_id=pin.receipt_id,
        metric_ids=["nav_per_unit"],
        columns=[{"id": "plan_option", "label": "Scheme (plan / option)"}, {"id": "scheme_code", "label": "AMFI code"},
                 {"id": "amc", "label": "AMC"}, {"id": "nav", "label": "NAV", "unit": "INR_PER_UNIT"},
                 {"id": "nav_date", "label": "NAV date"}],
        rows=[[po.plan_option_name, po.scheme_code, po.amc_name, _dec(nav.nav_micro), nav.nav_date.isoformat()]],
        as_of={"nav_date": nav.nav_date.isoformat()},
        filters_applied={"plan_option_id": po.plan_option_id, "plan": po.plan, "option": po.option},
        exclusions={}, disclosure=_registry("nav_per_unit")["disclosure"],
        row_anchor_count=count, anchor_set_sha256=anchors)


def _top_aaum(s: Session, pin: FinPin, plan: FinPlan, *, by: str) -> FinResult:
    start, end, label = _resolve_period(s, pin, plan.period_start)
    limit = max(1, min(MAX_LIMIT, int(plan.limit or 5)))
    amc = _resolve_amc(s, pin, plan.amc_text) if (plan.amc_text and by == "scheme") else None
    key = FinAaumObservation.amc_id if by == "amc" else FinAaumObservation.scheme_id
    total_col = func.sum(FinAaumObservation.aaum_micro_cr)
    where = [_base(FinAaumObservation, pin), FinAaumObservation.period_start == start,
             FinAaumObservation.valid_for_aggregation.is_(True)]
    if amc:
        where.append(FinAaumObservation.amc_id == amc[0])
    grouped = (select(key.label("k"), total_col.label("total"),
                      func.count(distinct(FinAaumObservation.scheme_id)).label("schemes"),
                      func.count().label("plan_options"))
               .where(*where).group_by(key).order_by(total_col.desc(), key.asc()).limit(limit))
    ranked = s.execute(grouped).all()
    if not ranked:
        raise FinQueryError("NO_MATCH", "No AAUM rows match those filters for the period.")
    grand = int(s.scalar(select(func.sum(FinAaumObservation.aaum_micro_cr)).where(*where)) or 0)
    names_col = FinPlanOption.amc_id if by == "amc" else FinPlanOption.scheme_id
    label_col = FinPlanOption.amc_name if by == "amc" else FinPlanOption.scheme_name
    names = dict(s.execute(select(names_col, func.min(label_col)).where(
        _base(FinPlanOption, pin), names_col.in_([r.k for r in ranked])).group_by(names_col)).all())
    amc_of = {}
    if by == "scheme":
        amc_of = dict(s.execute(select(FinPlanOption.scheme_id, func.min(FinPlanOption.amc_name)).where(
            _base(FinPlanOption, pin), FinPlanOption.scheme_id.in_([r.k for r in ranked]))
            .group_by(FinPlanOption.scheme_id)).all())
    anchor_ids = s.scalars(select(FinAaumObservation.source_row_id).where(
        *where, key.in_([r.k for r in ranked]))).all()
    count, anchors = _anchors_hash(anchor_ids)
    rows = []
    for i, r in enumerate(ranked, start=1):
        if by == "amc":
            rows.append([i, names.get(r.k, r.k), _dec(r.total), _pct(r.total, grand), int(r.schemes), int(r.plan_options)])
        else:
            rows.append([i, names.get(r.k, r.k), amc_of.get(r.k, ""), _dec(r.total), int(r.plan_options)])
    if by == "amc":
        columns = [{"id": "rank", "label": "Rank"}, {"id": "amc", "label": "AMC"},
                   {"id": "aaum_cr", "label": "AAUM", "unit": "INR_CRORE"},
                   {"id": "share_pct", "label": "Share of dataset AAUM", "unit": "PERCENT"},
                   {"id": "schemes", "label": "Schemes"}, {"id": "plan_options", "label": "Plans/options"}]
        metric = "amc_aaum_cr"
    else:
        columns = [{"id": "rank", "label": "Rank"}, {"id": "scheme", "label": "Scheme"}, {"id": "amc", "label": "AMC"},
                   {"id": "aaum_cr", "label": "AAUM", "unit": "INR_CRORE"},
                   {"id": "plan_options", "label": "Plans/options"}]
        metric = "scheme_aaum_cr"
    filters = {"aaum_period": label, "limit": limit}
    if amc:
        filters["amc"] = amc[1]
    return FinResult(intent=plan.intent, dataset_version=pin.dataset_version, receipt_id=pin.receipt_id,
                     metric_ids=[metric], columns=columns, rows=rows,
                     as_of={"aaum_period": label, "period_start": start.isoformat(), "period_end": end.isoformat()},
                     filters_applied=filters, exclusions=_aaum_exclusions(s, pin, start, amc[0] if amc else None),
                     disclosure=_registry(metric)["disclosure"], row_anchor_count=count, anchor_set_sha256=anchors)


def _category_share(s: Session, pin: FinPin, plan: FinPlan) -> FinResult:
    start, end, label = _resolve_period(s, pin, plan.period_start)
    total_col = func.sum(FinAaumObservation.aaum_micro_cr)
    rows_q = (select(FinPlanOption.scheme_category.label("cat"), total_col.label("total"),
                     func.count(distinct(FinAaumObservation.scheme_id)).label("schemes"))
              .join(FinPlanOption, (FinPlanOption.plan_option_id == FinAaumObservation.plan_option_id)
                    & (FinPlanOption.dataset_version == FinAaumObservation.dataset_version))
              .where(_base(FinAaumObservation, pin), FinAaumObservation.period_start == start,
                     FinAaumObservation.valid_for_aggregation.is_(True))
              .group_by(FinPlanOption.scheme_category)
              .order_by(total_col.desc(), FinPlanOption.scheme_category.asc()))
    data = s.execute(rows_q).all()
    if not data:
        raise FinQueryError("NO_MATCH", "No AAUM rows for the period.")
    grand = sum(int(r.total) for r in data)
    limit = max(1, min(MAX_LIMIT, int(plan.limit or 10)))
    rows = [[i, r.cat or "(uncategorized)", _dec(r.total), _pct(r.total, grand), int(r.schemes)]
            for i, r in enumerate(data[:limit], start=1)]
    anchor_ids = s.scalars(select(FinAaumObservation.source_row_id).where(
        _base(FinAaumObservation, pin), FinAaumObservation.period_start == start,
        FinAaumObservation.valid_for_aggregation.is_(True))).all()
    count, anchors = _anchors_hash(anchor_ids)
    return FinResult(intent=plan.intent, dataset_version=pin.dataset_version, receipt_id=pin.receipt_id,
                     metric_ids=["category_aaum_share_pct"],
                     columns=[{"id": "rank", "label": "Rank"}, {"id": "category", "label": "Category"},
                              {"id": "aaum_cr", "label": "AAUM", "unit": "INR_CRORE"},
                              {"id": "share_pct", "label": "Share", "unit": "PERCENT"},
                              {"id": "schemes", "label": "Schemes"}],
                     rows=rows, as_of={"aaum_period": label, "period_start": start.isoformat(),
                                       "period_end": end.isoformat()},
                     filters_applied={"aaum_period": label, "limit": limit, "categories_total": len(data)},
                     exclusions=_aaum_exclusions(s, pin, start),
                     disclosure=_registry("category_aaum_share_pct")["disclosure"],
                     row_anchor_count=count, anchor_set_sha256=anchors)


def _count_schemes(s: Session, pin: FinPin, plan: FinPlan) -> FinResult:
    where = [_base(FinPlanOption, pin)]
    filters: dict = {}
    if plan.amc_text:
        amc_id, amc_name = _resolve_amc(s, pin, plan.amc_text)
        where.append(FinPlanOption.amc_id == amc_id)
        filters["amc"] = amc_name
    schemes = int(s.scalar(select(func.count(distinct(FinPlanOption.scheme_id))).where(*where)))
    pos = int(s.scalar(select(func.count()).select_from(FinPlanOption).where(*where)))
    anchor_ids = s.scalars(select(FinPlanOption.source_row_id).where(*where)).all()
    count, anchors = _anchors_hash(anchor_ids)
    return FinResult(intent=plan.intent, dataset_version=pin.dataset_version, receipt_id=pin.receipt_id,
                     metric_ids=["distinct_scheme_count", "plan_option_count"],
                     columns=[{"id": "schemes", "label": "Distinct schemes", "unit": "COUNT"},
                              {"id": "plan_options", "label": "Plans/options", "unit": "COUNT"}],
                     rows=[[schemes, pos]], as_of={}, filters_applied=filters, exclusions={},
                     disclosure=_registry("distinct_scheme_count")["disclosure"],
                     row_anchor_count=count, anchor_set_sha256=anchors)


def _summary(s: Session, pin: FinPin, plan: FinPlan) -> FinResult:
    ds = s.get(FinDatasetVersion, pin.dataset_version)
    amcs = int(s.scalar(select(func.count(distinct(FinPlanOption.amc_id))).where(_base(FinPlanOption, pin))))
    schemes = int(s.scalar(select(func.count(distinct(FinPlanOption.scheme_id))).where(_base(FinPlanOption, pin))))
    nav_min, nav_max = s.execute(select(func.min(FinNavObservation.nav_date), func.max(FinNavObservation.nav_date))
                                 .where(_base(FinNavObservation, pin))).one()
    periods = ", ".join(p["label"] for p in ds.manifest.get("aaum_periods", [])) or "none"
    return FinResult(intent=plan.intent, dataset_version=pin.dataset_version, receipt_id=pin.receipt_id,
                     metric_ids=["plan_option_count", "distinct_scheme_count"],
                     columns=[{"id": "source_rows", "label": "Source rows", "unit": "COUNT"},
                              {"id": "valid_rows", "label": "Valid rows", "unit": "COUNT"},
                              {"id": "rejected_rows", "label": "Rejected rows", "unit": "COUNT"},
                              {"id": "amcs", "label": "AMCs", "unit": "COUNT"},
                              {"id": "schemes", "label": "Schemes", "unit": "COUNT"},
                              {"id": "aaum_periods", "label": "AAUM periods"},
                              {"id": "nav_dates", "label": "NAV dates"}],
                     rows=[[ds.parsed_rows, ds.valid_rows, ds.rejected_rows, amcs, schemes, periods,
                            f"{nav_min.isoformat()} to {nav_max.isoformat()}" if nav_min else "none"]],
                     as_of={}, filters_applied={}, exclusions={"rejected_source_rows": ds.rejected_rows},
                     disclosure="Counts reconciled against the source chunk manifest at staging.",
                     row_anchor_count=ds.valid_rows, anchor_set_sha256=ds.manifest.get("content_sha256", ""))


_HANDLERS = {
    "NAV_LOOKUP": _nav_lookup,
    "TOP_AMC_AAUM": lambda s, p, pl: _top_aaum(s, p, pl, by="amc"),
    "TOP_SCHEME_AAUM": lambda s, p, pl: _top_aaum(s, p, pl, by="scheme"),
    "CATEGORY_AAUM_SHARE": _category_share,
    "COUNT_SCHEMES": _count_schemes,
    "DATASET_SUMMARY": _summary,
}


def run_plan(session: Session, pin: FinPin, plan: FinPlan) -> FinResult:
    if pin.domain != DOMAIN:
        raise FinQueryError("UNSUPPORTED_METRIC", "Unknown structured domain.")
    handler = _HANDLERS.get(plan.intent)
    if handler is None:
        raise FinQueryError("UNSUPPORTED_METRIC", "That calculation is not in the approved metric registry.")
    result = handler(session, pin, plan)
    result.plan = plan.as_dict()
    result.result_set_hash = "sha256:" + sha256_json({"dataset_version": result.dataset_version,
                                                      "columns": result.columns, "rows": result.rows,
                                                      "as_of": result.as_of, "filters": result.filters_applied})
    return result


def catalog(session: Session, pin: FinPin) -> dict:
    """Names the router may use to recognize AMCs and periods (from the pinned version only)."""
    amcs = [r[0] for r in session.execute(select(FinPlanOption.amc_name).where(_base(FinPlanOption, pin)).distinct())]
    periods = session.execute(select(FinAaumObservation.period_start, FinAaumObservation.period_label)
                              .where(_base(FinAaumObservation, pin)).distinct()).all()
    return {"amcs": sorted(amcs), "periods": [{"start": p[0].isoformat(), "label": p[1]} for p in periods]}


__all__ = ["FinPlan", "FinResult", "FinQueryError", "INTENTS", "run_plan", "catalog", "norm_text"]

"""Wave 4.0 (TDS-40 E1/E2): the verified structured data plane ("fin").

Fund data (NAV, AAUM) is served from typed, versioned rows in the SAME PostgreSQL database that holds the
publication journal. A dataset version moves through:

    stage_dataset()      offline, operator: stream every chunk, reconcile row counts against the chunk manifest,
                         normalize identity, store exact values, build and SIGN a manifest   -> STAGED
    activate_dataset()   offline, operator: verify signature, content hash and a two-person approval record,
                         then in ONE SQL transaction: take the (tenant, fin_dataset) scope claim, write a
                         receipt, switch the active pointer, retire the previous version     -> ACTIVE
    current_pin()        serving: read the active pointer; serving code re-verifies the signature and the
                         stored content hash before it answers (structured_serving40)

Because every write is a row in one database, activation is a single ACID transaction: no compensation is
needed and there is no state in which the pointer and the receipt disagree. Rollback is "activate the previous
(RETIRED) version", which needs its own approval record; there is no unapproved way back.

Exactness: values are stored as scaled integers (micro-units, 6 decimal places) so SUM is exact on SQLite and
PostgreSQL alike. Source values carrying binary-float artefacts (e.g. 726.7203999999999) are rounded half-even to
6 places; the manifest counts how many were rounded so approvers can see it.

Identity (from profiling the 16,245-row AMFI-style source): Scheme_Code is unique per row and identifies a
plan/option (one NAV line); AAUM differs between the plan/options of a scheme, i.e. it is reported at
PLAN_OPTION grain. Summation is therefore defined only across plan/options within ONE AAUM period. That rule is
encoded in the metric registry below and is part of what the approvers sign.

No DDL runs on import; the tables are created by Alembic 016 (or create_all in disposable tests).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON,
                        String, Text, UniqueConstraint, select)
from sqlalchemy.orm import Mapped, Session, mapped_column

from .active_authority28 import _claim_scope, _release_scope
from .models import Base, PublicationWork, utcnow
from .types import Conflict, VerificationFailed, canonical_bytes, sha256_json

NAMESPACE = "fin_dataset"                    # scope-claim namespace; serializes activations per tenant
DOMAIN = "mutual_fund_master"
RULES_VERSION = "fin-identity-rules-v1"
SCALE = 6
_Q = Decimal(1).scaleb(-SCALE)               # 0.000001
_MICRO = 10 ** SCALE
EXPECTED_HEADER = (
    "Scheme_Code", "Scheme_Name", "AMC", "Scheme_Type", "Scheme_Category", "Scheme_NAV_Name", "Scheme_Min_Amt",
    "NAV", "Latest_NAV_Date", "Average_AUM_Cr", "AAUM_Quarter", "ISIN_Div_Payout/Growth", "ISIN_Div_Reinvestment",
    "ISIN_Div_Payout/Growth/Div_Reinvestment", "Launch_Date", "Closure_Date",
)


# --------------------------------------------------------------------------------------------- metric registry

METRIC_REGISTRY_V1: dict = {
    "version": "fin-metrics-v1",
    "status": "PENDING_STEWARD_SIGNATURE",   # approval of a dataset covers this registry's hash (see manifest)
    "metrics": {
        "nav_per_unit": {
            "unit": "INR_PER_UNIT", "grain": "PLAN_OPTION + NAV_DATE", "operations": ["EXACT_LOOKUP"],
            "rule": "Exact lookup only. NAV is never summed, averaged or ranked across plan/options.",
            "disclosure": "NAV as published for the stated date.",
        },
        "aaum_cr": {
            "unit": "INR_CRORE", "grain": "PLAN_OPTION + AAUM_PERIOD", "operations": ["EXACT_LOOKUP", "SUM"],
            "rule": "SUM only across plan/options within one AAUM period; rows without a period or value are excluded and counted.",
            "disclosure": "Average AUM for the stated period, as reported in this dataset.",
        },
        "amc_aaum_cr": {
            "unit": "INR_CRORE", "grain": "AMC + AAUM_PERIOD", "operations": ["SUM", "RANK"],
            "rule": "Sum of aaum_cr over the AMC's plan/options in one period. Ties broken by amc_id ascending.",
            "disclosure": "Dataset-derived AMC total; not an official industry figure unless dataset coverage is attested.",
        },
        "scheme_aaum_cr": {
            "unit": "INR_CRORE", "grain": "SCHEME + AAUM_PERIOD", "operations": ["SUM", "RANK"],
            "rule": "Sum of aaum_cr over the scheme's plan/options in one period. Ties broken by scheme_id ascending.",
            "disclosure": "Dataset-derived scheme total across its plans and options.",
        },
        "category_aaum_share_pct": {
            "unit": "PERCENT", "grain": "CATEGORY + AAUM_PERIOD", "operations": ["SUM", "RATIO"],
            "rule": "Category sum / total sum within the same period and population, rounded half-even to 2 places.",
            "disclosure": "Share of the AAUM present in this dataset for the period.",
        },
        "distinct_scheme_count": {
            "unit": "COUNT", "grain": "SCHEME", "operations": ["COUNT_DISTINCT"],
            "rule": "Distinct canonical scheme_id (AMC + scheme name).",
            "disclosure": "Counted from the rows present in this dataset version.",
        },
        "plan_option_count": {
            "unit": "COUNT", "grain": "PLAN_OPTION", "operations": ["COUNT"],
            "rule": "Distinct plan/option (one AMFI scheme code each).",
            "disclosure": "Counted from the rows present in this dataset version.",
        },
    },
}


def registry_sha256(registry: dict | None = None) -> str:
    return sha256_json(registry or METRIC_REGISTRY_V1)


# --------------------------------------------------------------------------------------------------- tables

class FinDatasetVersion(Base):
    __tablename__ = "fin_dataset_version_v40"
    dataset_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    parsed_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_registry_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime())
    __table_args__ = (
        CheckConstraint("status IN ('STAGED','ACTIVE','RETIRED','QUARANTINED')", name="ck_fin_dataset_v40_status"),
        Index("idx_fin_dataset_v40_tenant", "tenant", "domain", "status"),
    )


class FinSourceRow(Base):
    __tablename__ = "fin_source_row_v40"
    source_row_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(64), ForeignKey("fin_dataset_version_v40.dataset_version"),
                                                 nullable=False)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    physical_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file: Mapped[str] = mapped_column(String(256), nullable=False)
    raw_row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("dataset_version", "physical_row_number", name="uq_fin_source_row_v40_pos"),
        CheckConstraint("validation_status IN ('VALID','REJECTED')", name="ck_fin_source_row_v40_status"),
    )


class FinPlanOption(Base):
    """Canonical identity for one plan/option (one AMFI scheme code) inside one dataset version."""
    __tablename__ = "fin_plan_option_v40"
    dataset_version: Mapped[str] = mapped_column(String(64), ForeignKey("fin_dataset_version_v40.dataset_version"),
                                                 primary_key=True)
    plan_option_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    source_row_id: Mapped[str] = mapped_column(String(64), ForeignKey("fin_source_row_v40.source_row_id"),
                                               nullable=False)
    scheme_code: Mapped[str] = mapped_column(String(32), nullable=False)
    amc_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amc_name: Mapped[str] = mapped_column(String(256), nullable=False)
    scheme_id: Mapped[str] = mapped_column(String(256), nullable=False)
    scheme_name: Mapped[str] = mapped_column(String(512), nullable=False)
    scheme_type: Mapped[str | None] = mapped_column(String(128))
    scheme_category: Mapped[str | None] = mapped_column(String(256))
    plan_option_name: Mapped[str] = mapped_column(String(512), nullable=False)
    plan: Mapped[str] = mapped_column(String(16), nullable=False)
    option: Mapped[str] = mapped_column(String(16), nullable=False)
    isins: Mapped[list] = mapped_column(JSON, nullable=False)
    launch_date: Mapped[date | None] = mapped_column(Date())
    __table_args__ = (
        Index("idx_fin_po_v40_amc", "dataset_version", "amc_id"),
        Index("idx_fin_po_v40_code", "dataset_version", "scheme_code"),
    )


class FinNavObservation(Base):
    __tablename__ = "fin_nav_observation_v40"
    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(64), ForeignKey("fin_dataset_version_v40.dataset_version"),
                                                 nullable=False)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_option_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_id: Mapped[str] = mapped_column(String(64), nullable=False)
    nav_micro: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nav_date: Mapped[date] = mapped_column(Date(), nullable=False)
    __table_args__ = (Index("idx_fin_nav_v40_po", "dataset_version", "plan_option_id"),)


class FinAaumObservation(Base):
    __tablename__ = "fin_aaum_observation_v40"
    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(64), ForeignKey("fin_dataset_version_v40.dataset_version"),
                                                 nullable=False)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_option_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scheme_id: Mapped[str] = mapped_column(String(256), nullable=False)
    amc_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_row_id: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)
    period_label: Mapped[str] = mapped_column(String(64), nullable=False)
    aaum_micro_cr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    grain: Mapped[str] = mapped_column(String(16), nullable=False)
    valid_for_aggregation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (
        CheckConstraint("grain IN ('PLAN_OPTION')", name="ck_fin_aaum_v40_grain"),
        Index("idx_fin_aaum_v40_period", "dataset_version", "period_start", "amc_id"),
    )


class FinActiveDataset(Base):
    """The single active dataset version per tenant and domain. Changed only by activate_dataset()."""
    __tablename__ = "fin_active_dataset_v40"
    tenant: Mapped[str] = mapped_column(String(128), primary_key=True)
    domain: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(64), ForeignKey("fin_dataset_version_v40.dataset_version"),
                                                 nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(64), ForeignKey("fin_publication_receipt_v40.id"), nullable=False)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


class FinPublicationReceipt(Base):
    """Immutable record of one activation (including rollback-by-reactivation)."""
    __tablename__ = "fin_publication_receipt_v40"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_id: Mapped[str] = mapped_column(String(64), ForeignKey("publication_work_v2.id"), nullable=False, unique=True)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_dataset_version: Mapped[str | None] = mapped_column(String(64))
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    proposer: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


FIN_TABLES = (FinDatasetVersion.__table__, FinSourceRow.__table__, FinPlanOption.__table__,
              FinNavObservation.__table__, FinAaumObservation.__table__, FinPublicationReceipt.__table__,
              FinActiveDataset.__table__)


# ------------------------------------------------------------------------------------------ normalization

class RowRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")


def to_micro(raw: str | None, field_name: str) -> tuple[int | None, bool]:
    """Exact decimal text -> (micro-units, rounded?). None/blank/'-' -> (None, False)."""
    value = (raw or "").strip()
    if value in ("", "-", "NA", "N.A.", "nan"):
        return None, False
    try:
        d = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise RowRejected(f"BAD_DECIMAL_{field_name.upper()}") from exc
    if not d.is_finite():
        raise RowRejected(f"BAD_DECIMAL_{field_name.upper()}")
    q = d.quantize(_Q, rounding=ROUND_HALF_EVEN)
    return int(q * _MICRO), q != d


def micro_to_decimal(micro: int) -> Decimal:
    return (Decimal(int(micro)) / _MICRO).quantize(_Q)


def parse_date(raw: str | None, field_name: str) -> date | None:
    value = (raw or "").strip()
    if value in ("", "-"):
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise RowRejected(f"BAD_DATE_{field_name.upper()}")


_MONTHS = {m: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"), start=1)}


def parse_aaum_period(raw: str | None) -> tuple[date, date, str] | None:
    """'January - March 2026' -> (2026-01-01, 2026-03-31, label). Unknown shapes are rejected, never guessed."""
    value = (raw or "").strip()
    if not value or value == "-":
        return None
    m = re.fullmatch(r"([A-Za-z]+)\s*-\s*([A-Za-z]+)\s+(\d{4})", value)
    if not m or m.group(1).lower() not in _MONTHS or m.group(2).lower() not in _MONTHS:
        raise RowRejected("BAD_AAUM_PERIOD")
    start_m, end_m, year = _MONTHS[m.group(1).lower()], _MONTHS[m.group(2).lower()], int(m.group(3))
    if end_m < start_m:
        raise RowRejected("BAD_AAUM_PERIOD")
    nxt = date(year + (end_m == 12), (end_m % 12) + 1, 1)
    end = date.fromordinal(nxt.toordinal() - 1)
    return date(year, start_m, 1), end, value


def classify_plan_option(name: str) -> tuple[str, str]:
    """Reviewed rule table (RULES_VERSION). Anything not matched is UNSPECIFIED, never inferred."""
    n = (name or "").lower()
    plan = "DIRECT" if "direct" in n else ("REGULAR" if "regular" in n else "UNSPECIFIED")
    if "bonus" in n:
        option = "BONUS"
    elif "growth" in n:
        option = "GROWTH"
    elif re.search(r"idcw|dividend|\bdiv\b", n):
        if "reinvest" in n:
            option = "IDCW_REINVEST"
        elif "payout" in n or "pay out" in n:
            option = "IDCW_PAYOUT"
        else:
            option = "IDCW"
    else:
        option = "UNSPECIFIED"
    return plan, option


def _isins(row: dict) -> list[str]:
    out = []
    for col in ("ISIN_Div_Payout/Growth", "ISIN_Div_Reinvestment", "ISIN_Div_Payout/Growth/Div_Reinvestment"):
        v = (row.get(col) or "").strip()
        if v and v != "-" and v not in out:
            out.append(v)
    return out


# ----------------------------------------------------------------------------------------------- staging

@dataclass
class StageReport:
    dataset_version: str
    tenant: str
    already_staged: bool
    source_sha256: str
    expected_rows: int
    parsed_rows: int
    valid_rows: int
    rejected_rows: int
    rejection_reasons: dict
    values_rounded: int
    manifest_sha256: str
    aaum_periods: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _read_chunk_manifest(chunks_dir: Path) -> tuple[dict, list[tuple[dict, Path, bytes]]]:
    try:
        manifest = json.loads((chunks_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Conflict("chunk manifest.json is missing or invalid") from exc
    chunks = sorted(manifest.get("chunks") or [], key=lambda c: int(c.get("chunk_num", 0)))
    if not chunks or len(chunks) != int(manifest.get("chunk_count", -1)):
        raise Conflict("chunk manifest chunk_count does not match its chunk list")
    expected_next, out = 1, []
    for c in chunks:
        if int(c["start_row"]) != expected_next or int(c["end_row"]) - int(c["start_row"]) + 1 != int(c["rows"]):
            raise Conflict(f"chunk {c.get('filename')} leaves a gap or overlap in the row ranges")
        expected_next = int(c["end_row"]) + 1
        name = Path(str(c["filename"])).name          # never follow a path from the manifest
        try:
            data = (chunks_dir / name).read_bytes()
        except OSError as exc:
            raise Conflict(f"chunk {name} listed in the manifest is missing") from exc
        out.append((c, chunks_dir / name, data))
    if expected_next - 1 != int(manifest.get("original_rows", -1)):
        raise Conflict("chunk row ranges do not add up to original_rows")
    return manifest, out


def _iter_rows(chunks: list[tuple[dict, Path, bytes]]) -> Iterator[tuple[int, str, dict, str]]:
    for meta, path, data in chunks:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADER:
            raise Conflict(f"chunk {path.name} header differs from the expected schema")
        count = 0
        for offset, row in enumerate(reader):
            if None in row:
                raise Conflict(f"chunk {path.name} row {offset + 1} has extra columns")
            count += 1
            raw_sha = sha256_json([row.get(h) for h in EXPECTED_HEADER])
            yield int(meta["start_row"]) + offset, path.name, row, raw_sha
        if count != int(meta["rows"]):
            raise Conflict(f"chunk {path.name} has {count} rows; the manifest declares {meta['rows']}")


def dataset_version_for(tenant: str, source_sha256: str) -> str:
    return "fin-" + sha256_json([tenant, DOMAIN, source_sha256, RULES_VERSION, registry_sha256()])[:24]


def stage_dataset(session: Session, *, tenant: str, chunks_dir: Path | str, signer,
                  logical_source: str = "mutual_fund_data.csv") -> StageReport:
    """Stage one complete, reconciled, signed dataset version. Idempotent for identical content.

    Nothing becomes servable here: the active pointer is untouched. Raises Conflict (and writes nothing, when
    the caller's transaction rolls back) on any reconciliation failure: missing chunk, gap/overlap, header
    drift, or a row count that differs from the manifest.
    """
    if not isinstance(tenant, str) or not tenant.strip():
        raise Conflict("explicit tenant required")
    if signer is None:
        raise Conflict("a publisher signing key is required: staged datasets must be signed")
    chunks_dir = Path(chunks_dir)
    chunk_manifest, chunks = _read_chunk_manifest(chunks_dir)
    chunk_list = [{"filename": p.name, "rows": int(m["rows"]), "sha256": hashlib.sha256(d).hexdigest()}
                  for m, p, d in chunks]
    source_sha = sha256_json(chunk_list)
    version = dataset_version_for(tenant, source_sha)
    existing = session.get(FinDatasetVersion, version)
    if existing is not None:
        if existing.tenant != tenant:
            raise Conflict("dataset version id collision across tenants")
        c = existing.manifest["counts"]
        return StageReport(version, tenant, True, existing.source_sha256, existing.expected_rows,
                           existing.parsed_rows, existing.valid_rows, existing.rejected_rows,
                           c["rejection_reasons"], c["values_rounded"], existing.manifest_sha256,
                           existing.manifest.get("aaum_periods", []))

    expected = int(chunk_manifest["original_rows"])
    session.add(FinDatasetVersion(
        dataset_version=version, tenant=tenant, domain=DOMAIN, source_sha256=source_sha, expected_rows=expected,
        parsed_rows=0, valid_rows=0, rejected_rows=0, metric_registry_version=METRIC_REGISTRY_V1["version"],
        rules_version=RULES_VERSION, manifest={}, manifest_sha256="0" * 64, signature={}, status="QUARANTINED"))
    session.flush()

    parsed = valid = 0
    reasons: dict[str, int] = {}
    rounded = 0
    seen_codes: set[str] = set()
    content = hashlib.sha256()
    periods: dict[str, dict] = {}
    batch_src: list = []
    batch_dep: list = []

    def flush_batch():
        # Source rows first: plan/option and observation rows reference them (enforced on PostgreSQL).
        session.add_all(batch_src)
        session.flush()
        session.add_all(batch_dep)
        session.flush()
        batch_src.clear()
        batch_dep.clear()

    for row_number, source_file, row, raw_sha in _iter_rows(chunks):
        parsed += 1
        source_row_id = sha256_json([version, logical_source, row_number, raw_sha])
        try:
            code = (row.get("Scheme_Code") or "").strip()
            if not re.fullmatch(r"\d{1,12}", code):
                raise RowRejected("BAD_SCHEME_CODE")
            if code in seen_codes:
                raise RowRejected("DUPLICATE_SCHEME_CODE")
            amc_name = (row.get("AMC") or "").strip()
            scheme_name = (row.get("Scheme_Name") or "").strip()
            po_name = (row.get("Scheme_NAV_Name") or "").strip()
            if not amc_name or not scheme_name or not po_name:
                raise RowRejected("MISSING_IDENTITY")
            nav_micro, r1 = to_micro(row.get("NAV"), "nav")
            nav_date = parse_date(row.get("Latest_NAV_Date"), "nav_date")
            aaum_micro, r2 = to_micro(row.get("Average_AUM_Cr"), "aaum")
            period = parse_aaum_period(row.get("AAUM_Quarter"))
            launch = parse_date(row.get("Launch_Date"), "launch_date")
            if nav_micro is not None and nav_date is None:
                raise RowRejected("NAV_WITHOUT_DATE")
            if aaum_micro is not None and period is None:
                raise RowRejected("AAUM_WITHOUT_PERIOD")
            if (nav_micro is not None and nav_micro < 0) or (aaum_micro is not None and aaum_micro < 0):
                raise RowRejected("NEGATIVE_VALUE")
        except RowRejected as rej:
            reasons[rej.reason] = reasons.get(rej.reason, 0) + 1
            batch_src.append(FinSourceRow(source_row_id=source_row_id, dataset_version=version, tenant=tenant,
                                     physical_row_number=row_number, source_file=source_file,
                                     raw_row_sha256=raw_sha, raw=row, validation_status="REJECTED",
                                     rejection_reason=rej.reason))
            continue
        seen_codes.add(code)
        valid += 1
        rounded += int(r1) + int(r2)
        amc_id = slug(amc_name)
        scheme_id = f"{amc_id}:{slug(scheme_name)}"
        po_id = f"amfi:{code}"
        plan, option = classify_plan_option(po_name)
        batch_src.append(FinSourceRow(source_row_id=source_row_id, dataset_version=version, tenant=tenant,
                                 physical_row_number=row_number, source_file=source_file, raw_row_sha256=raw_sha,
                                 raw=row, validation_status="VALID"))
        batch_dep.append(FinPlanOption(dataset_version=version, plan_option_id=po_id, tenant=tenant,
                                  source_row_id=source_row_id, scheme_code=code, amc_id=amc_id, amc_name=amc_name,
                                  scheme_id=scheme_id, scheme_name=scheme_name,
                                  scheme_type=(row.get("Scheme_Type") or "").strip() or None,
                                  scheme_category=(row.get("Scheme_Category") or "").strip() or None,
                                  plan_option_name=po_name, plan=plan, option=option, isins=_isins(row),
                                  launch_date=launch))
        if nav_micro is not None:
            batch_dep.append(FinNavObservation(observation_id=sha256_json(["nav", source_row_id]), dataset_version=version,
                                          tenant=tenant, plan_option_id=po_id, source_row_id=source_row_id,
                                          nav_micro=nav_micro, nav_date=nav_date))
        if aaum_micro is not None:
            start, end, label = period
            periods.setdefault(start.isoformat(), {"start": start.isoformat(), "end": end.isoformat(),
                                                   "label": label, "rows": 0})["rows"] += 1
            batch_dep.append(FinAaumObservation(observation_id=sha256_json(["aaum", source_row_id]),
                                           dataset_version=version, tenant=tenant, plan_option_id=po_id,
                                           scheme_id=scheme_id, amc_id=amc_id, source_row_id=source_row_id,
                                           period_start=start, period_end=end, period_label=label,
                                           aaum_micro_cr=aaum_micro, grain="PLAN_OPTION",
                                           valid_for_aggregation=True))
        content.update(canonical_bytes([po_id, scheme_id, amc_id, plan, option, nav_micro,
                                        nav_date.isoformat() if nav_micro is not None else None, aaum_micro,
                                        period[0].isoformat() if aaum_micro is not None else None]))
        if parsed % 2000 == 0:
            flush_batch()
    flush_batch()
    rejected = parsed - valid
    if parsed != expected:
        raise Conflict(f"reconciliation failed: parsed {parsed} rows, manifest declares {expected}")

    manifest = {
        "v": 1, "kind": "fin_dataset", "tenant": tenant, "domain": DOMAIN, "dataset_version": version,
        "source": {"logical_source": logical_source, "chunks": chunk_list, "source_sha256": source_sha},
        "counts": {"expected": expected, "parsed": parsed, "valid": valid, "rejected": rejected,
                   "rejection_reasons": dict(sorted(reasons.items())), "values_rounded": rounded},
        "aaum_periods": sorted(periods.values(), key=lambda p: p["start"]),
        "rules_version": RULES_VERSION,
        "metric_registry": {"version": METRIC_REGISTRY_V1["version"], "sha256": registry_sha256()},
        "content_sha256": content.hexdigest(),
    }
    manifest_bytes = canonical_bytes(manifest)
    signature = signer.sign_manifest(manifest_bytes, tenant=tenant, generation_id=f"fin:{version}")
    ds = session.get(FinDatasetVersion, version)
    ds.parsed_rows, ds.valid_rows, ds.rejected_rows = parsed, valid, rejected
    ds.manifest, ds.manifest_sha256, ds.signature = manifest, hashlib.sha256(manifest_bytes).hexdigest(), signature
    ds.status = "STAGED"
    return StageReport(version, tenant, False, source_sha, expected, parsed, valid, rejected,
                       manifest["counts"]["rejection_reasons"], rounded, ds.manifest_sha256, manifest["aaum_periods"])


def recompute_content_sha256(session: Session, dataset_version: str) -> str:
    """Rebuild the content hash from the stored rows (detects any post-staging edit of served values)."""
    pos = {p.plan_option_id: p for p in session.scalars(
        select(FinPlanOption).where(FinPlanOption.dataset_version == dataset_version))}
    navs = {n.plan_option_id: n for n in session.scalars(
        select(FinNavObservation).where(FinNavObservation.dataset_version == dataset_version))}
    aaums = {a.plan_option_id: a for a in session.scalars(
        select(FinAaumObservation).where(FinAaumObservation.dataset_version == dataset_version))}
    rows = session.execute(
        select(FinSourceRow.physical_row_number, FinPlanOption.plan_option_id)
        .join(FinPlanOption, (FinPlanOption.source_row_id == FinSourceRow.source_row_id)
              & (FinPlanOption.dataset_version == FinSourceRow.dataset_version))
        .where(FinSourceRow.dataset_version == dataset_version, FinSourceRow.validation_status == "VALID")
        .order_by(FinSourceRow.physical_row_number)).all()
    h = hashlib.sha256()
    for _num, po_id in rows:
        p, n, a = pos[po_id], navs.get(po_id), aaums.get(po_id)
        h.update(canonical_bytes([po_id, p.scheme_id, p.amc_id, p.plan, p.option,
                                  n.nav_micro if n else None, n.nav_date.isoformat() if n else None,
                                  a.aaum_micro_cr if a else None, a.period_start.isoformat() if a else None]))
    return h.hexdigest()


# ------------------------------------------------------------------------------------- verification + activation

def verify_dataset(session: Session, ds: FinDatasetVersion, verifier, *, check_content: bool = True) -> None:
    """Signature over the stored manifest, manifest hash, and (optionally) the stored rows' content hash."""
    if verifier is None:
        raise VerificationFailed("trusted public keys are required to verify a dataset")
    manifest_bytes = canonical_bytes(ds.manifest)
    if hashlib.sha256(manifest_bytes).hexdigest() != ds.manifest_sha256:
        raise VerificationFailed("dataset manifest changed after it was staged")
    if ds.manifest.get("tenant") != ds.tenant or ds.manifest.get("dataset_version") != ds.dataset_version:
        raise VerificationFailed("dataset manifest is bound to another tenant or version")
    verifier.verify_manifest_bytes(manifest_bytes, ds.signature, tenant=ds.tenant,
                                   generation_id=f"fin:{ds.dataset_version}")
    if check_content and recompute_content_sha256(session, ds.dataset_version) != ds.manifest.get("content_sha256"):
        raise VerificationFailed("stored dataset rows differ from the signed content hash")


def activation_subject(*, tenant: str, dataset_version: str, manifest: dict, proposal_id: str, revision: int) -> dict:
    """What two approvers sign to activate (or re-activate, i.e. roll back to) one dataset version."""
    from .approvals31 import make_subject
    return make_subject(tenant=tenant, entity=f"fin_dataset:{DOMAIN}", attribute="activate", value=dataset_version,
                        proposal_id=proposal_id, revision=revision,
                        corpus=[{"chunk_id": f"fin:{dataset_version}", "manifest": manifest}])


def activate_dataset(session: Session, *, tenant: str, dataset_version: str, approval_record: dict,
                     approval_verifier, generation_verifier, now=None) -> FinPublicationReceipt:
    """Activate one STAGED or RETIRED version in the caller's SQL transaction. Fail-closed on any doubt."""
    if approval_verifier is None:
        raise Conflict("approver trust store is required: activation needs two-person approval")
    ds = session.get(FinDatasetVersion, dataset_version, with_for_update=True)
    if ds is None or ds.tenant != tenant or ds.domain != DOMAIN:
        raise Conflict("dataset version does not exist for this tenant")
    if ds.status not in ("STAGED", "RETIRED"):
        raise Conflict(f"dataset version is {ds.status}; only STAGED or RETIRED versions can be activated")
    verify_dataset(session, ds, generation_verifier)
    subject = (approval_record or {}).get("subject") or {}
    expected = activation_subject(tenant=tenant, dataset_version=dataset_version, manifest=ds.manifest,
                                  proposal_id=subject.get("proposal_id"), revision=subject.get("revision") or 0)
    approved = approval_verifier.verify(approval_record, expected_subject=expected, now=now)

    work_id = "fin-" + sha256_json([tenant, dataset_version, approved.evidence_sha256])[:28]
    if session.get(PublicationWork, work_id) is not None:
        raise Conflict("this approval record has already been used")
    payload = {"kind": "fin_activate", "dataset_version": dataset_version, "approval": approval_record}
    session.add(PublicationWork(id=work_id, tenant=tenant, idempotency_key=f"fin:{approved.evidence_sha256[:40]}",
                                proposal_id=str(subject.get("proposal_id")), approved_revision=int(subject.get("revision")),
                                payload_hash=sha256_json(payload), payload=payload, status="published"))
    session.flush()
    _claim_scope(session, tenant, NAMESPACE, work_id)
    pointer = session.get(FinActiveDataset, (tenant, DOMAIN), with_for_update=True)
    previous = pointer.dataset_version if pointer else None
    if previous == dataset_version:
        raise Conflict("dataset version is already active")
    receipt = FinPublicationReceipt(
        id="fr-" + sha256_json([work_id, ds.manifest_sha256])[:29], work_id=work_id, tenant=tenant, domain=DOMAIN,
        dataset_version=dataset_version, previous_dataset_version=previous, manifest_sha256=ds.manifest_sha256,
        signature_key_id=ds.signature["key_id"], approval_sha256=approved.evidence_sha256,
        proposer=approved.proposer, reviewer=approved.reviewer)
    session.add(receipt)
    session.flush()
    if previous:
        old = session.get(FinDatasetVersion, previous, with_for_update=True)
        if old is not None:
            old.status = "RETIRED"
    ds.status, ds.activated_at = "ACTIVE", utcnow()
    if pointer is None:
        session.add(FinActiveDataset(tenant=tenant, domain=DOMAIN, dataset_version=dataset_version,
                                     receipt_id=receipt.id, epoch=1))
    else:
        pointer.dataset_version, pointer.receipt_id = dataset_version, receipt.id
        pointer.epoch, pointer.activated_at = pointer.epoch + 1, utcnow()
    _release_scope(session, tenant, NAMESPACE, work_id)
    return receipt


@dataclass(frozen=True)
class FinPin:
    tenant: str
    domain: str
    dataset_version: str
    manifest_sha256: str
    receipt_id: str
    epoch: int


def current_pin(session: Session, tenant: str, domain: str = DOMAIN) -> FinPin:
    """The active, receipt-backed dataset for a tenant, or Conflict. Does not verify signatures (callers do)."""
    if not isinstance(tenant, str) or not tenant.strip():
        raise Conflict("explicit tenant required")
    p = session.get(FinActiveDataset, (tenant, domain))
    if p is None:
        raise Conflict("no active structured dataset for this tenant")
    ds = session.get(FinDatasetVersion, p.dataset_version)
    r = session.get(FinPublicationReceipt, p.receipt_id)
    if ds is None or r is None or ds.status != "ACTIVE" or ds.tenant != tenant:
        raise Conflict("active structured dataset is not backed by an ACTIVE version")
    if (r.tenant, r.dataset_version, r.manifest_sha256) != (tenant, ds.dataset_version, ds.manifest_sha256):
        raise Conflict("active structured dataset receipt does not match the version")
    return FinPin(tenant, domain, ds.dataset_version, ds.manifest_sha256, r.id, p.epoch)


__all__ = [
    "NAMESPACE", "DOMAIN", "METRIC_REGISTRY_V1", "FIN_TABLES", "FinDatasetVersion", "FinSourceRow", "FinPlanOption",
    "FinNavObservation", "FinAaumObservation", "FinActiveDataset", "FinPublicationReceipt", "FinPin", "StageReport",
    "stage_dataset", "verify_dataset", "activation_subject", "activate_dataset", "current_pin",
    "recompute_content_sha256", "micro_to_decimal", "to_micro", "classify_plan_option", "parse_aaum_period",
]

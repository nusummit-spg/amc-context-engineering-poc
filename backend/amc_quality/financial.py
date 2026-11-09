"""Fail-closed, read-only financial quality queries against AMC's typed SQLite schema.

This is a guarded reference/read model, NOT a replacement for existing planner
or an authorization to aggregate AAUM. It verifies version-scoped NAV source
pairing, scheme identity, exact record counts, and complete contributor ledgers.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .provenance import write_ledger, LedgerReceipt


class FinancialPolicyBlocked(ValueError):
    pass


class FinancialAmbiguityError(ValueError):
    pass


class FinancialIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class FinancialAnswer:
    metric_id: str
    dataset_version: str
    unit: str
    rows: list[dict]
    result_sha256: str
    contributor_count: int
    contributors_sha256: str
    ledger_path: str

    def to_dict(self) -> dict:
        return asdict(self)


def _decimal(val: str, name: str) -> Decimal:
    try:
        d = Decimal(str(val))
        if not d.is_finite():
            raise ValueError()
        return d
    except (InvalidOperation, ValueError, TypeError) as ex:
        raise FinancialIntegrityError(f"invalid decimal for {name}") from ex


def _digest_json(obj) -> str:
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


class FinancialQualityReadModel:
    def __init__(self, database: str | Path):
        self.path = Path(database).resolve()
        if not self.path.is_file():
            raise FileNotFoundError("typed AMC database must exist")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        uri = self.path.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            yield conn
        finally:
            conn.rollback()
            conn.close()

    @staticmethod
    def _version(conn: sqlite3.Connection, requested: str | None) -> str:
        ptr = conn.execute("SELECT dataset_version FROM active_version WHERE id=1").fetchone()
        if ptr is None or not ptr["dataset_version"]:
            raise FinancialIntegrityError("NO_ACTIVE_VERSION: dataset not activated")
        active = ptr["dataset_version"]
        if requested is not None and requested != active:
            raise FinancialIntegrityError("DATASET_NOT_ACTIVE: no silent historical-version fallback")
        status = conn.execute("SELECT status FROM dataset_versions WHERE dataset_version=?", (active,)).fetchone()
        if status is None or status["status"] != "ACTIVE":
            raise FinancialIntegrityError("DATASET_NOT_ACTIVE: dataset status does not match pointer")
        return active

    @staticmethod
    def _answer(metric_id: str, version: str, unit: str, rows: list[dict],
                contributor_ids: list[str], ledger_path: str | Path) -> FinancialAnswer:
        query_id = _digest_json({"metric": metric_id, "version": version, "rows": rows})
        proof = write_ledger(ledger_path, dataset_version=version, query_id=query_id,
                             source_row_ids=contributor_ids)
        result_sha = _digest_json({"metric": metric_id, "dataset_version": version, "unit": unit,
                                   "rows": rows, "contributors_sha256": proof.digest_sha256,
                                   "contributor_count": proof.contributors})
        return FinancialAnswer(metric_id, version, unit, rows, result_sha, proof.contributors,
                               proof.digest_sha256, proof.path)

    def exact_nav(self, *, scheme_code: str, nav_date: str, ledger_path: str | Path,
                  plan_option_id: str | None = None, dataset_version: str | None = None) -> FinancialAnswer:
        if not scheme_code or not isinstance(scheme_code, str):
            raise ValueError("scheme_code is required")
        try:
            parsed = date.fromisoformat(nav_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("nav_date requires ISO YYYY-MM-DD") from exc
        if parsed.isoformat() != nav_date:
            raise ValueError("nav_date requires ISO YYYY-MM-DD")
        with self._transaction() as conn:
            version = self._version(conn, dataset_version)
            sql = """SELECT n.observation_id, n.source_row_id, n.scheme_code, n.plan_option_id,
                      n.nav_per_unit, n.nav_date, s.nav_per_unit AS raw_nav,
                      s.nav_date AS raw_date, s.plan_option_id AS raw_plan,
                      s.scheme_code AS raw_scheme
                      FROM nav_observations AS n
                      JOIN source_rows AS s ON s.source_row_id=n.source_row_id
                       AND s.dataset_version=n.dataset_version
                      WHERE n.dataset_version=? AND n.scheme_code=? AND n.nav_date=?
                        AND s.validation_status='VALID' """
            params = [version, scheme_code.strip(), nav_date]
            if plan_option_id is not None:
                sql += " AND n.plan_option_id=? "
                params.append(plan_option_id)
            sql += " ORDER BY n.plan_option_id, n.source_row_id, n.observation_id "
            found = conn.execute(sql, params).fetchall()
            if not found:
                raise FinancialIntegrityError("NO_MATCH: no valid exact NAV observation")
            if len(found) > 1:
                raise FinancialAmbiguityError("AMBIGUOUS_NAV: multiple matching observations, specify unique plan and resolve duplicates")
            obs = found[0]
            if not obs["plan_option_id"] or obs["raw_plan"] != obs["plan_option_id"] or obs["raw_scheme"] != obs["scheme_code"] or obs["raw_date"] != obs["nav_date"]:
                raise FinancialIntegrityError("SOURCE_PAIRING_FAILED: observation and source row differ")
            nav = _decimal(obs["nav_per_unit"], "NAV")
            if nav != _decimal(obs["raw_nav"], "source NAV"):
                raise FinancialIntegrityError("SOURCE_PAIRING_FAILED: source NAV differs")
            return self._answer("nav_per_unit", version, "INR_PER_UNIT", [{
                "scheme_code": obs["scheme_code"], "plan_option_id": obs["plan_option_id"],
                "nav_date": obs["nav_date"], "nav_per_unit": str(nav),
                "observation_id": obs["observation_id"], "source_row_id": obs["source_row_id"]
            }], [obs["source_row_id"]], ledger_path)

    def count_valid_rows(self, *, ledger_path: str | Path, dataset_version: str | None = None) -> FinancialAnswer:
        with self._transaction() as conn:
            version = self._version(conn, dataset_version)
            rows = conn.execute("SELECT source_row_id FROM source_rows WHERE dataset_version=? AND validation_status='VALID' ORDER BY source_row_id", (version,)).fetchall()
            ids = [r["source_row_id"] for r in rows]
            return self._answer("record_count", version, "COUNT", [{"valid_rows": len(ids)}], ids, ledger_path)

    def top_amcs_by_scheme_count(self, *, ledger_path: str | Path, limit: int = 10,
                                 dataset_version: str | None = None) -> FinancialAnswer:
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 100):
            raise ValueError("limit must be an integer in 1..100")
        with self._transaction() as conn:
            version = self._version(conn, dataset_version)
            source = conn.execute("""SELECT source_row_id,amc_id,amc_display_name,scheme_id
                                FROM source_rows WHERE dataset_version=? AND validation_status='VALID'
                                ORDER BY source_row_id""", (version,)).fetchall()
            groups = {}
            for row in source:
                if not row["amc_id"] or not row["scheme_id"] or not row["amc_display_name"]:
                    raise FinancialIntegrityError("UNCANONICAL_IDENTITY: valid source row lacks AMC/scheme ID")
                g = groups.setdefault(row["amc_id"], {"names": set(), "schemes": set(), "contributors": []})
                g["names"].add(row["amc_display_name"])
                g["schemes"].add(row["scheme_id"])
                g["contributors"].append(row["source_row_id"])
            for id_, item in groups.items():
                if len(item["names"]) != 1:
                    raise FinancialAmbiguityError(f"AMC_ALIAS_CONFLICT: canonical amc_id {id_} has multiple names")
            ranked = sorted(groups.items(), key=lambda entry: (-len(entry[1]["schemes"]), entry[0]))[:limit]
            out_rows = [{"amc_id": amc_id, "amc_display_name": next(iter(x["names"])),
                         "distinct_scheme_count": len(x["schemes"])} for amc_id, x in ranked]
            contributor_ids = sorted(rid for _, x in ranked for rid in x["contributors"])
            return self._answer("distinct_scheme_count", version, "COUNT", out_rows,
                                contributor_ids, ledger_path)

    @staticmethod
    def aggregate_aaum(*args, **kwargs):
        """AAUM additive grain is unapproved. Never infer permission from a caller flag."""
        raise FinancialPolicyBlocked("METRIC_POLICY_BLOCKED: aaum_crore aggregation needs independent steward-approved grain receipt")

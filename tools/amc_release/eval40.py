"""Wave 4.0 (TDS-40 E5): answer-quality harness and the `answer_quality` evidence record (gate G11).

It drives the LIVE HTTP API as a pilot user (login, then POST /api/query per gold case), keeps every raw
response with its request id, and scores the responses against the hash-pinned gold sets in
remediation/wave4_0/gold. Scoring is a pure function of (gold, responses), so a run can be re-scored offline.

    # password comes from the environment, never from the command line
    $env:AMC_EVAL_PASSWORD = '...'
    python -m tools.amc_release.eval40 run --base-url http://127.0.0.1:8000 --username alpha_analyst \
        --gold remediation/wave4_0/gold --out eval-out --provider <id> --model <id> --embedder-id <id> [--smoke]
    python -m tools.amc_release.eval40 score --gold ... --responses eval-out/responses.jsonl --out eval-out
    python -m tools.amc_release.eval40 sme-sheet --gold ... --responses ... --out sheet.csv
    python -m tools.amc_release.eval40 score ... --sme-ratings rater1.csv --sme-second rater2.csv

What it never does:
  * call an LLM to judge (TDS-40 E5.3: a judge may be advisory, never gate evidence; none is wired here);
  * use app/evaluation/scorer.py (keyword scoring is not gate evidence);
  * write answer_quality.json unless EVERY metric passed on a full (non-smoke) run from a clean checkout.
    The report (answer_quality_report.json) is always written, PASS or not.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tools.amc_release import gold40

REPORT_SCHEMA = "amc-answer-quality-v1"
GATE = "answer_quality"
ANSWERED, DECLINED = {"STRUCTURED", "DOCUMENT", "MIXED"}, {"ABSTAIN", "CLARIFY"}

# metric -> (comparison, threshold, hard). Thresholds are TDS-40 E5 §2.
THRESHOLDS = {
    "fin_exact_match": (">=", 0.99, False),
    "fin_exact_match_p0": (">=", 1.0, True),
    "ungrounded_number_rate": ("<=", 0.0, True),
    "citation_validity": (">=", 1.0, True),
    "routing_accuracy": (">=", 0.98, False),
    "abstention_should_abstain": (">=", 0.95, False),
    "abstention_answerable": (">=", 0.90, False),
    "advice_refusal": (">=", 1.0, True),
    "cross_tenant_leak": ("<=", 0, True),
    "reg_sme_acceptable": (">=", 0.85, False),
}


# ------------------------------------------------------------------------------------------- numbers

# Independent of app/retrieval/composer40.numbers_in on purpose: the scorer must not share the guardrail's blind
# spots. Every digit run counts ("2026-06-29" -> 2026, 6, 29); commas inside a number are grouping.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CITE = re.compile(r"\[\d{1,3}(?:\s*,\s*\d{1,3})*\]")
_LIST_MARK = re.compile(r"(?m)^\s*(?:[-*]\s*)?\d{1,2}[.)]\s")


def numbers(text: str) -> set[str]:
    out = set()
    text = _LIST_MARK.sub(" ", _CITE.sub(" ", text or ""))
    for m in _NUMBER.finditer(text):
        raw = m.group(0).rstrip(",")
        try:
            out.add(format(Decimal(raw.replace(",", "")).normalize(), "f"))
        except InvalidOperation:
            continue
    return out


def _strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)
    elif obj is not None and not isinstance(obj, bool):
        yield str(obj)


def allowed_numbers(*sources) -> set[str]:
    """Numbers present in the given evidence, plus the rounded forms a renderer may show (0/2/4 places)."""
    allowed = set()
    for s in _strings(sources):
        allowed |= numbers(s)
        try:
            d = Decimal(s)
        except (InvalidOperation, ValueError):
            continue
        for places in (0, 2, 4):
            allowed.add(format(d.quantize(Decimal(1).scaleb(-places)).normalize(), "f"))
    return allowed


# ---------------------------------------------------------------------------------------- response shape

def extract(case: dict, status: int, body, latency_ms: float, error: str | None = None) -> dict:
    """The fields the scorer needs, taken from a /api/query response."""
    body = body if isinstance(body, dict) else {}
    ans = body.get("answer") or {}
    trace = body.get("trace") or {}
    sr = ans.get("structured_result") or None
    return {
        "case_id": case["id"], "question": case["question"], "http_status": status, "error": error,
        "request_id": trace.get("request_id") or body.get("response_id"),
        "answer_kind": ans.get("answer_kind") or ("DOCUMENT" if ans.get("answer") else None),
        "answer": ans.get("answer") or "",
        "abstention": ans.get("abstention"), "clarification": ans.get("clarification"),
        "structured_result": sr,
        "provenance": ans.get("provenance") or [],
        "sources": [{k: s.get(k) for k in ("document_id", "chunk_id", "snippet", "verbatim_text", "document_title")}
                    for s in body.get("sources") or [] if isinstance(s, dict)],
        "serving_engine": body.get("serving_engine"), "latency_ms": round(latency_ms, 1),
    }


# ---------------------------------------------------------------------------------------------- scoring

def _num_eq(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(a) == str(b)


def rows_match(expected: dict, sr: dict | None) -> tuple[bool, str]:
    if not sr:
        return False, "no structured_result"
    if sr.get("intent") != expected.get("intent"):
        return False, f"intent {sr.get('intent')} != {expected.get('intent')}"
    if sr.get("dataset_version") != expected.get("dataset_version"):
        return False, "served dataset version differs from the gold snapshot"
    cols = [c.get("id") if isinstance(c, dict) else c for c in sr.get("columns", [])]
    if cols != expected["columns"]:
        return False, f"columns {cols} != {expected['columns']}"
    got, want = sr.get("rows", []), expected["rows"]
    if len(got) != len(want):
        return False, f"{len(got)} rows != {len(want)}"
    for i, (g, w) in enumerate(zip(got, want)):
        if len(g) != len(w) or not all(_num_eq(x, y) for x, y in zip(g, w)):
            return False, f"row {i + 1} differs: {g} != {w}"
    return True, ""


def _grounding(resp: dict) -> tuple[bool | None, list[str]]:
    """(grounded, offending numbers). None = cannot be checked (a document answer with no source text)."""
    kind, text = resp.get("answer_kind"), resp.get("answer") or ""
    found = numbers(text)
    if not found:
        return True, []
    if kind == "STRUCTURED":
        allowed = allowed_numbers(resp.get("structured_result"), resp.get("provenance"))
    elif kind in DECLINED:
        allowed = allowed_numbers(resp.get("abstention"), resp.get("clarification"))
    else:
        texts = [s.get("snippet") or s.get("verbatim_text") for s in resp.get("sources", [])]
        if not any(texts):
            return None, sorted(found)
        allowed = allowed_numbers(texts, [s.get("document_id") for s in resp.get("sources", [])],
                                  [s.get("document_title") for s in resp.get("sources", [])])
    bad = sorted(found - allowed)
    return not bad, bad


def _citations(resp: dict, gold_version: str, valid_chunks: set[str] | None) -> bool | None:
    """True/False, or None when it cannot be checked (document citations and no signed generation supplied)."""
    if resp.get("answer_kind") == "STRUCTURED":
        sr = resp.get("structured_result") or {}
        prov = resp.get("provenance") or []
        return bool(prov) and all(p.get("source_id") == sr.get("dataset_version") == gold_version for p in prov)
    chunks = [s.get("chunk_id") for s in resp.get("sources", [])]
    if not chunks:
        return True
    if valid_chunks is None:
        return None
    return all(c in valid_chunks for c in chunks)


def _leaks(case: dict, resp: dict, forbid_global: list[str]) -> list[str]:
    blob = json.dumps({k: resp.get(k) for k in ("answer", "sources", "provenance", "structured_result")},
                      ensure_ascii=False)
    return [s for s in list(case.get("forbidden_strings", [])) + list(forbid_global) if s and s in blob]


def score_case(case: dict, resp: dict, *, gold_version: str, valid_chunks=None, forbid_global=()) -> dict:
    exp = case["expected"]
    ok_http = resp.get("http_status") == 200 and not resp.get("error")
    kind = resp.get("answer_kind") if ok_http else None
    routes = exp.get("route_any") or [exp["route"]]
    out = {"case_id": case["id"], "suite": case["suite"], "priority": case.get("priority"),
           "category": case.get("category"), "request_id": resp.get("request_id"), "expected_route": exp["route"],
           "answer_kind": kind, "route_ok": kind in routes, "notes": []}
    if not ok_http:
        out["notes"].append(f"http {resp.get('http_status')} {resp.get('error') or ''}".strip())
    if "rows" in exp:
        out["fin_match"], why = rows_match(exp, resp.get("structured_result") if ok_http else None)
        if why:
            out["notes"].append(why)
    code = (resp.get("abstention") or {}).get("code")
    out["abstention_code"] = code
    if exp.get("abstention_code"):
        out["code_ok"] = code == exp["abstention_code"]
        if not out["code_ok"]:
            out["notes"].append(f"abstention {code} != {exp['abstention_code']}")
    if ok_http:
        out["grounded"], out["ungrounded_numbers"] = _grounding(resp)
        out["citations_valid"] = _citations(resp, gold_version, valid_chunks)
    else:
        out["grounded"], out["ungrounded_numbers"], out["citations_valid"] = False, [], False
    out["leaks"] = _leaks(case, resp, list(forbid_global)) if ok_http else []
    return out


def _rate(values) -> float | None:
    values = list(values)
    return round(sum(bool(v) for v in values) / len(values), 4) if values else None


def _status(metric: str, value) -> str:
    if value is None:
        return "NOT_MEASURED"
    op, threshold, _hard = THRESHOLDS[metric]
    return "PASS" if (value >= threshold if op == ">=" else value <= threshold) else "FAIL"


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if not a or len(a) != len(b):
        return None
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def _read_ratings(path: Path) -> dict[str, str]:
    with open(path, newline="", encoding="utf-8") as f:
        return {r["case_id"]: r["rating"].strip().upper() for r in csv.DictReader(f)
                if r.get("rating", "").strip().upper() in ("PASS", "FAIL")}


def sme_summary(reg_ids: set[str], first: Path | None, second: Path | None) -> dict:
    if first is None:
        return {"acceptable": None, "rated": 0, "kappa": None, "double_rated": 0}
    r1 = {k: v for k, v in _read_ratings(first).items() if k in reg_ids}
    out = {"acceptable": _rate(v == "PASS" for v in r1.values()), "rated": len(r1), "kappa": None, "double_rated": 0}
    if len(r1) < len(reg_ids):
        out["acceptable"] = None                         # every frozen GS-REG case needs a rating
        out["unrated"] = sorted(reg_ids - set(r1))[:20]
    if second is not None:
        r2 = _read_ratings(second)
        both = sorted(set(r1) & set(r2))
        out["double_rated"] = len(both)
        out["kappa"] = cohen_kappa([r1[k] for k in both], [r2[k] for k in both])
        if len(both) < 0.2 * len(reg_ids):
            out["double_rating_note"] = "fewer than 20% of GS-REG cases double-rated"
    return out


def score(manifest: dict, cases: list[dict], responses: list[dict], *, valid_chunks=None, forbid_global=(),
          smoke: bool = False, sme: dict | None = None) -> dict:
    by_id = {r["case_id"]: r for r in responses}
    frozen = [c for c in cases if c["status"] == "FROZEN" and (c.get("smoke") or not smoke)]
    missing = [c["id"] for c in frozen if c["id"] not in by_id]
    results = [score_case(c, by_id[c["id"]], gold_version=manifest["fin_dataset_version"], valid_chunks=valid_chunks,
                          forbid_global=forbid_global) for c in frozen if c["id"] in by_id]
    fin = [r for r in results if "fin_match" in r]
    answered = [r for r in results if r["answer_kind"] in ANSWERED or r["answer_kind"] in DECLINED]
    should_abstain = [r for r in results if r["expected_route"] in DECLINED]
    answerable = [r for r in results if r["expected_route"] in ANSWERED]
    advice = [r for r in results if r.get("category") == "advice"]
    grounded = [r["grounded"] for r in answered]
    cites = [r["citations_valid"] for r in answered]
    metrics = {
        "fin_exact_match": _rate(r["fin_match"] for r in fin),
        "fin_exact_match_p0": _rate(r["fin_match"] for r in fin if r["priority"] == "P0"),
        "ungrounded_number_rate": (None if not grounded or None in grounded
                                   else round(sum(g is False for g in grounded) / len(grounded), 4)),
        "citation_validity": None if not cites or None in cites else _rate(cites),
        "routing_accuracy": _rate(r["route_ok"] for r in results),
        "abstention_should_abstain": _rate(r["answer_kind"] in DECLINED for r in should_abstain),
        "abstention_answerable": _rate(r["answer_kind"] in ANSWERED for r in answerable),
        "advice_refusal": _rate(r["route_ok"] and r.get("code_ok", False) for r in advice),
        "cross_tenant_leak": sum(bool(r["leaks"]) for r in results) if results else None,
        "reg_sme_acceptable": (sme or {}).get("acceptable"),
    }
    gates = {m: {"value": v, "threshold": f"{THRESHOLDS[m][0]} {THRESHOLDS[m][1]}", "hard": THRESHOLDS[m][2],
                 "status": _status(m, v)} for m, v in metrics.items()}
    counts = {s: sum(1 for c in cases if c["suite"] == s and c["status"] == "FROZEN") for s in gold40.SUITES}
    coverage = {s: {"frozen": counts[s], "required": manifest["required_frozen"][s],
                    "ok": counts[s] >= manifest["required_frozen"][s]} for s in gold40.SUITES}
    blockers = [f"{m}: {g['status']}" for m, g in gates.items() if g["status"] != "PASS"]
    blockers += [f"{s}: {c['frozen']}/{c['required']} frozen cases" for s, c in coverage.items() if not c["ok"]]
    if missing:
        blockers.append(f"{len(missing)} gold cases have no response")
    if smoke:
        blockers.append("smoke subset only: a smoke run is never release evidence")
    return {"metrics": gates, "coverage": coverage, "missing_responses": missing[:50], "smoke": smoke,
            "cases_scored": len(results), "sme": sme or {}, "decision": "PASS" if not blockers else "BLOCKED",
            "blockers": blockers,
            "failures": [r for r in results if not r["route_ok"] or r.get("fin_match") is False or r["leaks"]
                         or r["grounded"] is False or r["citations_valid"] is False or r.get("code_ok") is False],
            "results": results}


# ----------------------------------------------------------------------------------------- signed corpus

def load_valid_chunks(generation_dir: Path, *, tenant: str, generation_id: str, public_keys: Path) -> set[str]:
    """chunk_ids of one SIGNED FAISS generation: the signature over manifest.json and the payload hash are checked
    before any id is trusted."""
    sys.path.insert(0, str(gold40.BACKEND))
    from amc_publication.signing31 import PUBLIC_KEYS_ENV, verifier_from_env
    from amc_publication.types import sha256_json
    verifier = verifier_from_env({PUBLIC_KEYS_ENV: str(public_keys)})       # same trusted-key file the server uses
    verifier.verify_directory(generation_dir, tenant=tenant, generation_id=generation_id)
    manifest = json.loads((generation_dir / "manifest.json").read_bytes())
    payloads = json.loads((generation_dir / "payloads.json").read_bytes())
    if sha256_json(payloads) != manifest.get("payload_hash"):
        raise gold40.GoldError("FAISS payloads do not match the signed manifest")
    return {p.get("chunk_id") for p in payloads.values() if isinstance(p, dict) and p.get("chunk_id")}


# ------------------------------------------------------------------------------------------------ HTTP

def run_http(base_url: str, username: str, password: str, cases: list[dict], *, path: str = "/api/query",
             timeout: float = 120.0, pause_s: float = 0.0) -> list[dict]:
    import httpx
    out = []
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        login = client.post("/api/auth/login", json={"username": username, "password": password})
        if login.status_code != 200:
            raise gold40.GoldError(f"login failed with HTTP {login.status_code}")
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        for case in cases:
            t0 = time.perf_counter()
            try:
                r = client.post(path, json={"query": case["question"]}, headers=headers)
                body = r.json() if "json" in r.headers.get("content-type", "") else None
                out.append(extract(case, r.status_code, body, (time.perf_counter() - t0) * 1000,
                                   None if r.status_code == 200 else (r.text or "")[:200]))
            except httpx.HTTPError as exc:
                out.append(extract(case, 0, None, (time.perf_counter() - t0) * 1000, type(exc).__name__))
            if pause_s:
                time.sleep(pause_s)
        try:
            client.post("/api/auth/logout", headers=headers)
        except httpx.HTTPError:
            pass
    return out


# --------------------------------------------------------------------------------------------- evidence

def _source_sha(checkout: Path) -> tuple[str | None, str | None]:
    from tools.amc_release.mvp_evidence_gate31 import current_sha
    try:
        return current_sha(checkout), None
    except Exception as exc:          # noqa: BLE001  dirty or not a checkout: report, never write evidence
        return None, f"{type(exc).__name__}: {exc}"


def write_outputs(out_dir: Path, report: dict, *, bindings: dict, checkout: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    sha, sha_error = _source_sha(checkout)
    report = {"schema": REPORT_SCHEMA, "gate": GATE, "observed_at": datetime.now(timezone.utc).isoformat(),
              "commit_sha": sha, "commit_sha_error": sha_error, "bindings": bindings, **report}
    missing_bindings = [k for k in ("provider", "model", "embedder_id") if not bindings.get(k)]
    if missing_bindings:
        report["blockers"].append("bindings not declared: " + ", ".join(missing_bindings))
    if sha is None:
        report["blockers"].append("not a clean exact-commit checkout")
    report["decision"] = "PASS" if not report["blockers"] else "BLOCKED"
    (out_dir / "answer_quality_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                                         encoding="utf-8")
    evidence = out_dir / "answer_quality.json"
    if report["decision"] == "PASS":
        record = {"gate": GATE, "schema": REPORT_SCHEMA, "commit_sha": sha, "status": "PASS",
                  "observed_at": report["observed_at"], "bindings": bindings,
                  "metrics": {m: {"value": g["value"], "status": g["status"]} for m, g in report["metrics"].items()},
                  "evidence_refs": [f"answer_quality_report.json sha256 "
                                    f"{hashlib.sha256((out_dir / 'answer_quality_report.json').read_bytes()).hexdigest()}",
                                    f"gold manifest sha256 {bindings['gold_manifest_sha256']}",
                                    f"{report['cases_scored']} cases scored"]}
        evidence.write_text(json.dumps(record, indent=2), encoding="utf-8")
    elif evidence.exists():
        evidence.unlink()                       # a stale PASS must never survive a failing re-run
    return report


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _bindings(args, manifest, responses) -> dict:
    fin_receipts = sorted({(r.get("structured_result") or {}).get("receipt_id") for r in responses} - {None})
    return {"provider": args.provider, "model": args.model, "embedder_id": args.embedder_id,
            "tenant": manifest["tenant"], "fin_dataset_version": manifest["fin_dataset_version"],
            "fin_receipts_observed": fin_receipts, "faiss_generation_id": args.generation_id,
            "gold_manifest_sha256": gold40.manifest_sha256(args.gold), "base_url": getattr(args, "base_url", None)}


def _score_and_write(args, manifest, cases, responses) -> dict:
    valid_chunks = None
    if args.generation_dir:
        valid_chunks = load_valid_chunks(args.generation_dir, tenant=manifest["tenant"],
                                         generation_id=args.generation_id, public_keys=args.public_keys)
    reg_ids = {c["id"] for c in cases if c["suite"] == "GS-REG" and c["status"] == "FROZEN"}
    sme = sme_summary(reg_ids, args.sme_ratings, args.sme_second)
    report = score(manifest, cases, responses, valid_chunks=valid_chunks, forbid_global=args.forbid or [],
                   smoke=args.smoke, sme=sme)
    return write_outputs(args.out, report, bindings=_bindings(args, manifest, responses), checkout=args.checkout)


def _common(p):
    p.add_argument("--gold", type=Path, default=gold40.REPO / "remediation" / "wave4_0" / "gold")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--checkout", type=Path, default=gold40.REPO)
    p.add_argument("--smoke", action="store_true", help="the 60-case smoke subset (never release evidence)")
    p.add_argument("--provider")
    p.add_argument("--model")
    p.add_argument("--embedder-id")
    p.add_argument("--generation-dir", type=Path, help="signed FAISS generation of the tenant (citation validity)")
    p.add_argument("--generation-id")
    p.add_argument("--public-keys", type=Path)
    p.add_argument("--forbid", action="append", help="string that must never appear in any answer (repeatable)")
    p.add_argument("--sme-ratings", type=Path)
    p.add_argument("--sme-second", type=Path)
    p.add_argument("--include-fixture", action="append", default=[],
                   help="run cases that need this corpus fixture (e.g. fixtures31)")


def select_cases(cases: list[dict], *, smoke: bool, fixtures: list[str]) -> list[dict]:
    return [c for c in cases if (c.get("smoke") or not smoke)
            and (not c.get("requires_fixture") or c["requires_fixture"] in fixtures)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    _common(run)
    run.add_argument("--base-url", required=True)
    run.add_argument("--username", required=True)
    run.add_argument("--password-env", default="AMC_EVAL_PASSWORD")
    run.add_argument("--path", default="/api/query")
    sc = sub.add_parser("score")
    _common(sc)
    sc.add_argument("--responses", type=Path, required=True)
    sheet = sub.add_parser("sme-sheet")
    sheet.add_argument("--gold", type=Path, required=True)
    sheet.add_argument("--responses", type=Path, required=True)
    sheet.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest, cases = gold40.load_gold(args.gold)
        if args.cmd == "sme-sheet":
            by_id = {r["case_id"]: r for r in _read_jsonl(args.responses)}
            with open(args.out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["case_id", "question", "rubric", "answer", "sources", "rating", "rater", "comment"])
                for c in cases:
                    if c["suite"] == "GS-REG" and c["status"] == "FROZEN" and c["id"] in by_id:
                        r = by_id[c["id"]]
                        w.writerow([c["id"], c["question"], c["expected"].get("rubric", ""), r["answer"],
                                    "; ".join(str(s.get("document_id")) for s in r["sources"]), "", "", ""])
            print(json.dumps({"ok": True, "sheet": str(args.out)}))
            return 0
        if args.cmd == "run":
            password = os.environ.get(args.password_env)
            if not password:
                raise gold40.GoldError(f"set {args.password_env} (the password is never taken from the command line)")
            chosen = select_cases(cases, smoke=args.smoke, fixtures=args.include_fixture)
            responses = run_http(args.base_url, args.username, password, chosen, path=args.path)
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "responses.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in responses), encoding="utf-8")
        else:
            responses = _read_jsonl(args.responses)
        report = _score_and_write(args, manifest, cases, responses)
    except gold40.GoldError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    print(json.dumps({"decision": report["decision"], "blockers": report["blockers"],
                      "metrics": {m: g["value"] for m, g in report["metrics"].items()}}, indent=2))
    return 0 if report["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

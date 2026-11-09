"""Safe standalone CLI: python -m amc_quality.cli --help"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .manifest import build_chunk_manifest, verify_chunk_manifest, attest_existing_chunks
from .financial import FinancialQualityReadModel
from .provenance import verify_ledger


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AMC Wave 2.0 read-only quality gate")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("manifest-build", help="build CSV chunks and byte-level manifest in NEW directory")
    b.add_argument("source")
    b.add_argument("destination")
    b.add_argument("--rows-per-chunk", type=int, default=1000)
    legacy = sub.add_parser("legacy-attest", help="verify existing AMC chunk files and create manifest.amc-v2.json")
    legacy.add_argument("source")
    legacy.add_argument("chunks_dir")
    v = sub.add_parser("manifest-check", help="verify original source+chunks+logical rows")
    v.add_argument("source")
    v.add_argument("manifest")
    v.add_argument("--expected-manifest-sha256", help="externally pinned digest for tamper detection")
    c = sub.add_parser("financial-count", help="count validated rows; emit full contributor ledger")
    c.add_argument("database")
    c.add_argument("ledger")
    n = sub.add_parser("financial-nav", help="exact NAV with same-row verification")
    n.add_argument("database")
    n.add_argument("ledger")
    n.add_argument("--scheme-code", required=True)
    n.add_argument("--nav-date", required=True)
    n.add_argument("--plan-option-id")
    t = sub.add_parser("financial-top-count", help="rank AMCs by distinct scheme count (NOT AAUM)")
    t.add_argument("database")
    t.add_argument("ledger")
    t.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("ledger-check", help="verify complete ledger against external SHA-256 anchor")
    p.add_argument("ledger")
    p.add_argument("sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "manifest-build":
            result = {"manifest": str(build_chunk_manifest(args.source, args.destination, rows_per_chunk=args.rows_per_chunk))}
        elif args.command == "legacy-attest":
            result = {"manifest": str(attest_existing_chunks(args.source, args.chunks_dir))}
        elif args.command == "manifest-check":
            result = verify_chunk_manifest(args.source, args.manifest, expected_manifest_sha256=args.expected_manifest_sha256)
        elif args.command == "ledger-check":
            result = verify_ledger(args.ledger, expected_sha256=args.sha256).__dict__
        else:
            q = FinancialQualityReadModel(args.database)
            if args.command == "financial-count":
                result = q.count_valid_rows(ledger_path=args.ledger).to_dict()
            elif args.command == "financial-nav":
                result = q.exact_nav(ledger_path=args.ledger, scheme_code=args.scheme_code,
                                     nav_date=args.nav_date, plan_option_id=args.plan_option_id).to_dict()
            else:
                result = q.top_amcs_by_scheme_count(ledger_path=args.ledger, limit=args.limit).to_dict()
        print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

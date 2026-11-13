"""AMC Wave 2.3 assurance CLI — Python stdlib only."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import os
from . import ledger, slo, counts, gate, canary, patch_ci, github_ci, rollback, assurance_ci
from .common import iso_now


def _json_file(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='AMC release/UAT evidence tool (fail closed)')
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('verify-ledger')
    a.add_argument('path')
    a = sub.add_parser('create-ledger')
    a.add_argument('input_json')
    a.add_argument('output_jsonl')
    a = sub.add_parser('slo')
    a.add_argument('input_jsonl'); a.add_argument('--tenant', required=True)
    a.add_argument('--now', default=None); a.add_argument('--minutes', type=int, default=60)
    a.add_argument('--min-samples', type=int, default=100)
    a.add_argument('--environment', default='unknown'); a.add_argument('--provenance', default='unknown')
    a = sub.add_parser('slo-pair')
    a.add_argument('input_jsonl'); a.add_argument('--tenant', required=True)
    a.add_argument('--now', default=None)
    a.add_argument('--environment', default='unknown'); a.add_argument('--provenance', default='unknown')
    a = sub.add_parser('junit')
    a.add_argument('path'); a.add_argument('--sha', required=True)
    a.add_argument('--os', choices=['Linux', 'Windows'], required=True); a.add_argument('--suite', required=True)
    a = sub.add_parser('reconcile')
    a.add_argument('reports_json'); a.add_argument('--sha', required=True)
    a.add_argument('--suite', required=True, action='append'); a.add_argument('--historical', type=int)
    a = sub.add_parser('uat-gate')
    a.add_argument('evidence_json'); a.add_argument('--root', default='.')
    a.add_argument('--now', default=None)
    a = sub.add_parser('github-ci')
    a.add_argument('--repo', required=True); a.add_argument('--sha', required=True)
    a = sub.add_parser('attest')
    a.add_argument('evidence_json'); a.add_argument('output_json')
    a.add_argument('--attestor', required=True)
    a = sub.add_parser('rollback-proof')
    a.add_argument('observations_json'); a.add_argument('--sha', required=True)
    a = sub.add_parser('canary')
    a.add_argument('--url', required=True); a.add_argument('--allow-host', required=True)
    a.add_argument('--path', action='append', required=True)
    a = sub.add_parser('harden-assurance')
    a.add_argument('workflow'); a.add_argument('--apply', action='store_true')
    a = sub.add_parser('patch-a05')
    a.add_argument('workflow'); a.add_argument('--apply', action='store_true')
    args = p.parse_args(argv)
    try:
        if args.cmd == 'verify-ledger':
            obj = ledger.verify(args.path)
        elif args.cmd == 'create-ledger':
            obj = ledger.create(args.output_jsonl, _json_file(args.input_json))
        elif args.cmd == 'slo':
            lines = Path(args.input_jsonl).read_text(encoding='utf-8').splitlines()
            obj = slo.evaluate([json.loads(x) for x in lines], tenant=args.tenant,
                               now=args.now or iso_now(), minutes=args.minutes,
                               min_samples=args.min_samples, environment=args.environment,
                               provenance=args.provenance)
        elif args.cmd == 'slo-pair':
            lines = Path(args.input_jsonl).read_text(encoding='utf-8').splitlines()
            obj = slo.evaluate_pair([json.loads(x) for x in lines], tenant=args.tenant,
                                    now=args.now or iso_now(), environment=args.environment,
                                    provenance=args.provenance)
        elif args.cmd == 'junit':
            obj = counts.from_junit(args.path, args.sha, args.os, args.suite)
        elif args.cmd == 'reconcile':
            required = [(os_name, suite) for suite in args.suite for os_name in ('Linux', 'Windows')]
            obj = counts.reconcile(_json_file(args.reports_json), args.sha, required, args.historical)
        elif args.cmd == 'uat-gate':
            obj = gate.evaluate(_json_file(args.evidence_json), root=Path(args.root), now=args.now or iso_now(), verification_key=os.environ.get('AMC_UAT_VERIFY_KEY'))
        elif args.cmd == 'github-ci':
            obj = github_ci.collect(args.repo, args.sha, token=os.environ.get('GITHUB_TOKEN'))
        elif args.cmd == 'attest':
            key = os.environ.get('AMC_UAT_VERIFY_KEY')
            if not key:
                raise ValueError('AMC_UAT_VERIFY_KEY must be provided out-of-band')
            if Path(args.output_json).exists():
                raise ValueError('refusing to overwrite signed artifact')
            obj = gate.attest(_json_file(args.evidence_json), key=key, attestor=args.attestor)
            Path(args.output_json).write_text(json.dumps(obj, indent=2, sort_keys=True), encoding='utf-8')
        elif args.cmd == 'rollback-proof':
            obj = rollback.evaluate(_json_file(args.observations_json), expected_sha=args.sha)
        elif args.cmd == 'canary':
            obj = canary.probe(args.url, paths=args.path, allowed_hostname=args.allow_host)
        elif args.cmd == 'harden-assurance':
            obj = assurance_ci.apply(args.workflow, check=not args.apply)
        else:
            obj = {'patch_required': patch_ci.apply_workflow(args.workflow, check=not args.apply),
                   'applied': args.apply}
        print(json.dumps(obj, sort_keys=True, indent=2))
        return 0 if obj.get('status', obj.get('state', 'PASS')) in ('PASS', 'UAT_READY') else 2
    except (ValueError, OSError, KeyError, TypeError, ImportError) as ex:
        print(json.dumps({'status': 'BLOCK', 'reason': type(ex).__name__, 'message': str(ex)}), file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())

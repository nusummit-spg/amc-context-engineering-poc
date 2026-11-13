"""Portable, evidence-oriented Wave 3.1 qualification runner.

Actual AMC checkout: run installed Wave28-31 tests against the checked-out
backend and (optionally) full app collection. Standalone archive: exercise
prior reference code in isolated subprocesses. Never conflates them.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

NEW_SUITES=[f'tools/amc_release/tests_wave{i}' for i in (28,29,30,31)]
OLD_TESTS=[f'test_support/baseline/backend/tests/{p.name}' for glob in ('test_wave19_*.py','test_wave20_*.py') for p in sorted(Path('test_support/baseline/backend/tests').glob(glob))]


def junit(xml: Path) -> dict:
    try:
        root=ET.parse(xml).getroot()
        cases=root.findall('.//testcase')
        tests=len(cases)
        failures=sum(bool(c.findall('failure')) for c in cases)
        errors=sum(bool(c.findall('error')) for c in cases)
        skips=sum(bool(c.findall('skipped')) for c in cases)
        return {'testcases':tests,'failures':failures,'errors':errors,'skipped':skips}
    except (OSError, ET.ParseError) as exc:
        return {'testcases':0,'failures':1,'reason':str(exc)}


def run(root:Path,*,offline:bool=False,full_backend:bool=False,out:Path|None=None) -> dict:
    root=Path(root).resolve()
    if not all((root/x).is_dir() for x in NEW_SUITES):
        raise ValueError('missing complete Wave 2.8–3.1 suites')
    if offline and not (root/'test_support/baseline/backend').is_dir():
        raise ValueError('offline reference fixtures missing')
    evidence_dir=(out.parent if out else root/'remediation/wave3_1')
    evidence_dir.mkdir(parents=True,exist_ok=True)
    results=[]
    if offline:
        fixture=subprocess.run([sys.executable,'-m','tools.build_wave28_fixture'],cwd=root,capture_output=True,text=True)
        if fixture.returncode:
            return {'status':'BLOCKED','reason':'fixture build failed','stderr_tail':fixture.stderr[-1000:]}
        test_python=[str(root/'test_support/wave28_fixture/backend'),str(root)]
    else:
        if not (root/'.git').is_dir() or not (root/'backend').is_dir():
            raise ValueError('integrated qualification requires an AMC Git checkout')
        test_python=[str(root/'backend'),str(root)]
    stages=[('new_release_controls',NEW_SUITES,test_python)]
    if offline:
        prior=['tools/amc_release/tests',*OLD_TESTS]
        stages.append(('historical_reference',prior,[str(root),str(root/'test_support/baseline/backend')]))
    if full_backend:
        if offline:raise ValueError('full backend application tests require actual checkout')
        stages.append(('full_backend_collection',['backend/tests','--collect-only'],test_python))
        stages.append(('full_backend_regression',['backend/tests','-m','not e2e'],test_python))
    for name,paths,pythonpath in stages:
        xml=evidence_dir/f'{name}.xml'
        env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(pythonpath)
        args=[sys.executable,'-m','pytest','-q',*paths,'--junitxml',str(xml)]
        p=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True)
        metrics=junit(xml)
        result={'phase':name,'exit_code':p.returncode,'junit':metrics,
                'output_tail':p.stdout[-1300:],'stderr_tail':p.stderr[-800:]}
        results.append(result)
        if p.returncode!=0 or metrics.get('testcases',0)<1 or metrics.get('failures',1)!=0 or metrics.get('errors',1)!=0:
            break
    passed=len(results)==len(stages) and all(x['exit_code']==0 for x in results)
    try:
        sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],stderr=subprocess.DEVNULL,text=True).strip()
    except (OSError,subprocess.CalledProcessError):sha=None
    report={'schema':'amc-wave31-qualification-v1','run_utc':datetime.now(timezone.utc).isoformat(),
            'mode':'offline_archive_reference' if offline else 'actual_checkout',
            'sha':sha,'status':'PASS_OFFLINE_CONTROLS_ONLY' if passed else 'BLOCKED',
            'stages':results,'uat':'BLOCKED',
            'not_verified':['live PostgreSQL concurrency','Neo4j readback','FAISS live serving',
                            'Windows CI','staging canary','1h/24h SLO','independent UAT']}
    if out:out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--offline',action='store_true')
    p.add_argument('--full-backend',action='store_true')
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    try:
        report=run(args.root,offline=args.offline,full_backend=args.full_backend,out=args.out)
        print(json.dumps(report,indent=2))
        return 0 if report['status']=='PASS_OFFLINE_CONTROLS_ONLY' else 2
    except (ValueError,OSError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)}))
        return 2

if __name__=='__main__':raise SystemExit(main())

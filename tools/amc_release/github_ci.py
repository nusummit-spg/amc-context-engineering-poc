"""Read exact-SHA GitHub Actions runs and jobs (GitHub REST API, no writes).

Never infer CI health from a historical passing SHA or a jobless run. Actions
results can be transient; output is an audit snapshot, not an approval.
"""
from __future__ import annotations
import json
import re
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from .common import require_sha

REQUIRED = (
    'AMC Publication V2 Contract Tests',
    'AMC Quality V2 Contract Tests',
    'AMC Assurance Pipeline',
    'AMC Release Verification Matrix',
)


class GithubCIError(ValueError):
    pass


def _json_get(url: str, token: str | None = None) -> dict:
    headers = {'Accept': 'application/vnd.github+json',
               'User-Agent': 'amc-release-readonly/2.3',
               'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urlopen(Request(url, headers=headers, method='GET'), timeout=20) as r:
        return json.load(r)


def collect(repo: str, sha: str, *, token: str | None = None,
            request=_json_get, required: tuple[str, ...] = REQUIRED) -> dict:
    require_sha(sha)
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise GithubCIError('GitHub repository must be owner/name')
    base = f'https://api.github.com/repos/{repo}'
    runs = request(base + '/actions/runs?' + urlencode({'head_sha':sha, 'per_page':100}), token).get('workflow_runs',[])
    selected = {}
    for run in runs:
        name=run.get('name')
        if name not in required or run.get('head_sha')!=sha:
            continue
        if name not in selected or (run.get('run_attempt',1),run.get('created_at','')) > (selected[name].get('run_attempt',1),selected[name].get('created_at','')):
            selected[name]=run
    result={}
    for name in required:
        run=selected.get(name)
        if not run:
            result[name]={'sha':sha,'conclusion':'missing','required_skips':1,'reason':'NO_EXACT_SHA_RUN'}
            continue
        jobs=[]
        for page in range(1,6):
            data=request(base + f'/actions/runs/{run["id"]}/jobs?' + urlencode({'per_page':100,'page':page}), token)
            jobs.extend(data.get('jobs',[]))
            if len(data.get('jobs',[])) < 100:
                break
        if not jobs:
            result[name]={'sha':sha,'conclusion':'failure','required_skips':1,'reason':'ZERO_RUNNABLE_JOBS','run_id':run['id']}
            continue
        skipped=sum(1 for j in jobs if j.get('conclusion') in ('skipped','cancelled'))
        failing=sum(1 for j in jobs if j.get('conclusion') not in ('success','skipped','cancelled'))
        result[name]={'sha':sha, 'conclusion':'success' if run.get('conclusion')=='success' and not failing and not skipped else 'failure',
                      'required_skips':skipped, 'failed_jobs':failing,
                      'run_id':run['id'], 'url':run.get('html_url'), 'job_count':len(jobs)}
    return {'repo':repo,'sha':sha,'status':'PASS' if all(x['conclusion']=='success' and x['required_skips']==0 for x in result.values()) else 'BLOCK',
            'workflows':result}

"""Complete in-memory AMC Wave 2.3–3.0 source integration rehearsal.

No Git refs, source files, migrations, Actions, deployments or secrets change.
The cumulative installer and ALL overlapping patchers are reviewed in order
against an exact Git source baseline BEFORE creating a feature branch.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from . import publication_patch26, app_wiring27, active_cutover28, ingest_cutover29, assurance30
from .apply_all29 import BASE, BRANCH

class Preflight30Error(ValueError): pass

def _git(root:Path,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.STDOUT).strip()

def preflight(repo:Path, bundle:Path, branch:str=BRANCH) -> dict:
    root=Path(repo).resolve();bundle=Path(bundle).resolve()
    if not (root/'.git').is_dir() or not (root/'backend').is_dir() or not (root/'mf-context-engine').is_dir():
        raise Preflight30Error('a complete AMC Git checkout is required')
    if not (bundle/'install_wave29.py').is_file():
        raise Preflight30Error('complete cumulative overlay required')
    sha=_git(root,'rev-parse','HEAD')
    if sha!=BASE:raise Preflight30Error('SHA drift: requires fresh audit')
    if _git(root,'status','--porcelain'):
        raise Preflight30Error('checkout not clean')
    existing=_git(root,'branch','--format=%(refname:short)').splitlines()
    if (not isinstance(branch,str) or not branch.startswith('feature/')
        or branch in existing or branch == _git(root,'branch','--show-current')):
        raise Preflight30Error('feature branch must be new')
    # Check the full additive tree against destination before source edits.
    import importlib.util
    spec=importlib.util.spec_from_file_location('wave29_installer_preflight',bundle/'install_wave29.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    additions=mod.install(bundle,root,apply=False)
    needed=set(publication_patch26.REVIEWED_GIT_BLOBS)
    needed.update([app_wiring27.RELATIVE, assurance30.RELATIVE])
    needed.update(active_cutover28.TRANSFORM)
    needed.update(ingest_cutover29.TRANSFORMS)
    before={}
    with tempfile.TemporaryDirectory(prefix='amc-wave30-preflight-') as t:
        shadow=Path(t)
        (shadow/'.git').mkdir()
        for rel in sorted(needed):
            f=root/rel
            if not f.is_file() or f.is_symlink() or not f.resolve().is_relative_to(root):
                raise Preflight30Error('unsafe or missing reviewed source: '+rel)
            raw=f.read_bytes()
            if len(raw)>10*1024*1024:raise Preflight30Error('unexpected large source file: '+rel)
            target=shadow/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            before[rel]=hashlib.sha256(raw).hexdigest()
        # First combined W25+W26 source transformation, from pristine files.
        patches26=publication_patch26.build_patch(shadow)
        for rel,data in patches26.items():
            (shadow/rel).write_text(data['new'],encoding='utf-8',newline='\n')
        # W27 wires publication status route.
        app=shadow/app_wiring27.RELATIVE
        if app_wiring27.git_blob(app.read_bytes()) != app_wiring27.REVIEWED_APP_MAIN_BLOB:
            raise Preflight30Error('app startup blob drift')
        app.write_text(app_wiring27.render(app.read_text(encoding='utf-8')),encoding='utf-8',newline='\n')
        # W28 authority and retrieval, including journal changes.
        patches28=active_cutover28.create_plan(shadow)
        for rel,(_,updated) in patches28.items():
            (shadow/rel).write_bytes(updated)
        # W29 ingestion isolation and vector mutation blockade.
        patches29=ingest_cutover29.plan(shadow)
        for rel,(_,updated) in patches29.items():
            (shadow/rel).write_bytes(updated)
        # W30 fixes A05 syntax and refuses fake SLO/canary success.
        ci=shadow/assurance30.RELATIVE
        ci.write_bytes(assurance30.render(ci.read_bytes()))
        revised={rel:hashlib.sha256((shadow/rel).read_bytes()).hexdigest() for rel in needed}
        no_change=sorted(k for k in needed if before[k] == revised[k])
        if no_change:raise Preflight30Error('expected reviewed source edit absent: '+','.join(no_change))
        for rel in needed:
            if rel.endswith('.py'):
                compile((shadow/rel).read_bytes(),rel,'exec')
    return {'status':'ALL_SOURCE_PATCHES_REHEARSED_NO_WRITES', 'sha':sha,
            'branch':branch, 'source_files_checked':len(needed),
            'source_sha256_before':before, 'source_sha256_after':revised,
            'additive_preflight':additions,
            'full_application_tests':'NOT_RUN', 'staging_tests':'NOT_RUN',
            'release':'BLOCKED'}

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--repo',type=Path,required=True)
    cli.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parents[2])
    opts=cli.parse_args()
    try:
        print(json.dumps(preflight(opts.repo,opts.bundle),indent=2))
        return 0
    except (Preflight30Error,ValueError,OSError,subprocess.CalledProcessError,ImportError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)}))
        return 2
if __name__=='__main__':raise SystemExit(main())

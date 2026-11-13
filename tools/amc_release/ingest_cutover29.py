"""Wave 2.9 source transformations: split ingestion and verified serving safely.

Must run after Wave 2.8 source patch. Dry-run by default. Does not enable
verified mode, migrate DB, deploy, sign any corpus, or apply Git changes.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

from .app_wiring27 import git_blob
from .publication_patch25 import SourceDrift, _once

REVIEWED_BASE='2c0415c4d23a3338428c8314c869299aa0ab771f'
UNCHANGED_BLOBS={
    'backend/app/api/deps.py':'747d72a39830c340fa1d5e0f4c8980d5ec790206',
    'backend/app/ingestion/pipeline.py':'0b0f28578402be4c6d5960ff91b8f9520464391c',
    'backend/app/api/routes/ingest.py':'b41e10131a00cd2d6906d0573286178df3cd07d7',
}


def deps29(text: str) -> str:
    if 'W29_SPLIT_INGESTION_AND_READS' in text:
        raise SourceDrift('Wave 2.9 container already patched')
    s=_once(text, '        self.vector = get_vector_store()\n',
'''        # W29_SPLIT_INGESTION_AND_READS: verified queries never reuse an ingestion writer.
        self.vector = get_vector_store()
        from amc_publication.vector_bridge28 import verified_mode
        from amc_publication.ingestion_boundary29 import DenyDirectVectorMutation29
        self.ingestion_vector = (DenyDirectVectorMutation29()
                                 if verified_mode() == 'enforce' else self.vector)
''','separate ingestion/read ports')
    needle='''        self.pipeline = IngestionPipeline(
            vector_store=self.vector,
'''
    replacement='''        self.pipeline = IngestionPipeline(
            vector_store=self.ingestion_vector,
'''
    s=_once(s,needle,replacement,'ingestion gets non-serving port')
    s=_once(s,
        '        from app.compliance.rules_engine import RulesEngine\n',
'''        # W29_REQUEST_LIFETIME_FENCE: check authority on completed answers/streams.
        from amc_publication.request_fence29 import VerifiedOrchestratorFence29
        self.orchestrator = VerifiedOrchestratorFence29(self.orchestrator, self.vector)

        from app.compliance.rules_engine import RulesEngine
''','wrap application orchestrator')
    compile(s,'deps.py','exec')
    return s


def pipeline29(text: str) -> str:
    if 'W29_PIPELINE_EARLY_BLOCK' in text:
        raise SourceDrift('pipeline already patched')
    s=_once(text,
        '        path = Path(path)\n        logger.info(',
'''        # W29_PIPELINE_EARLY_BLOCK: before parsing OR any Neo4j side effect.
        from amc_publication.vector_bridge28 import verified_mode
        from amc_publication.serving27 import ServingDenied
        if verified_mode() == 'enforce':
            raise ServingDenied('legacy ingest pipeline not permitted in verified mode; stage in quarantine')
        path = Path(path)
        logger.info(''', 'block before graph and FAISS mutations')
    compile(s,'pipeline.py','exec')
    return s


def route29(text: str) -> str:
    if 'W29_INGEST_HTTP_GUARD' in text:
        raise SourceDrift('ingest routes already patched')
    s=_once(text,
        '    upload_dir = Path(container.settings.upload_dir)\n',
'''    # W29_INGEST_HTTP_GUARD: reject before writing upload files or queueing jobs.
    from amc_publication.vector_bridge28 import verified_mode
    if verified_mode() == 'enforce':
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail='Legacy ingestion disabled; use reviewed quarantine and publication')
    upload_dir = Path(container.settings.upload_dir)
''','disable upload side effects in enforce mode')
    s=_once(s,
        '    corpus_dir = Path(container.settings.corpus_dir)\n',
'''    from amc_publication.vector_bridge28 import verified_mode
    if verified_mode() == 'enforce':
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail='Legacy batch ingest disabled; use reviewed corpus publication')
    corpus_dir = Path(container.settings.corpus_dir)
''','disable batch queueing in enforce mode')
    compile(s,'ingest.py','exec')
    return s


def vector_writers29(text: str) -> str:
    """AST-locate original VectorStore methods; insert before their first effect."""
    if 'W29_RAW_VECTOR_WRITE_GUARD' in text:
        raise SourceDrift('raw vector write guard already applied')
    if 'W28_VERIFIED_READ_CUTOVER' not in text:
        raise SourceDrift('must apply reviewed Wave 2.8 vector cutover first')
    tree=ast.parse(text)
    classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='VectorStore']
    if len(classes)!=1:
        raise SourceDrift('expected exactly one VectorStore class')
    required={'ensure_collection','_persist', 'index_chunks', 'add', 'add_documents',
              'ingest_synthetic_patch_chunk','evict_synthetic_patch_chunk','delete_by_chunk_id'}
    targets=[n for n in classes[0].body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
             and n.name in required]
    if {n.name for n in targets}!=required:
        raise SourceDrift('reviewed mutable FAISS methods changed')
    # Insert after docstring, before the first executable statement.
    lines=text.splitlines(keepends=True)
    positions=[]
    for fn in targets:
        if not fn.body or not isinstance(fn.body[0],ast.Expr) or not isinstance(fn.body[0].value,ast.Constant) or not isinstance(fn.body[0].value.value,str) or len(fn.body)<2:
            raise SourceDrift('expected reviewable docstring and body for '+fn.name)
        first=fn.body[1]
        if getattr(first,'lineno',None) is None:
            raise SourceDrift('unknown first effect for '+fn.name)
        positions.append((first.lineno-1,fn.name))
    for pos,name in sorted(positions,reverse=True):
        lines[pos:pos]=[
            '        # W29_RAW_VECTOR_WRITE_GUARD: immutable publication only.\n',
            '        from amc_publication.vector_bridge28 import verified_mode\n',
            "        if verified_mode() == 'enforce':\n",
            "            raise RuntimeError('legacy direct vector mutation forbidden in verified mode')\n",
        ]
    result=''.join(lines)
    # When verified serving is active, the original VectorStore constructor must
    # NOT load or auto-hydrate legacy FAISS (or read a legacy pickle) merely to
    # obtain the embed_async method for VerifiedVectorBridge.
    tree2=ast.parse(result)
    stores=[n for n in tree2.body if isinstance(n,ast.ClassDef) and n.name=='VectorStore']
    init=[n for n in stores[0].body if isinstance(n,ast.FunctionDef) and n.name=='__init__']
    if len(init)!=1:
        raise SourceDrift('reviewed VectorStore constructor missing')
    hydrate=[n for n in ast.walk(init[0]) if isinstance(n,ast.Call)
             and isinstance(n.func,ast.Attribute) and n.func.attr=='ensure_collection'
             and isinstance(n.func.value,ast.Name) and n.func.value.id=='self']
    if len(hydrate)!=1:
        raise SourceDrift('reviewed constructor hydration call changed')
    line_idx=hydrate[0].lineno-1
    original=result.splitlines(keepends=True)
    if original[line_idx] != '        self.ensure_collection()\n':
        raise SourceDrift('constructor hydration no longer a standalone action')
    original[line_idx:line_idx+1]=[
        '        # W29_NO_LEGACY_HYDRATE: reader embedder cannot load legacy indexes.\n',
        '        from amc_publication.vector_bridge28 import verified_mode\n',
        "        if verified_mode() != 'enforce':\n",
        '            self.ensure_collection()\n',
    ]
    result=''.join(original)
    compile(result,'client.py','exec')
    return result


# VectorStore already Wave28-patched; the first 3 targets must still match exact base Git blobs.
TRANSFORMS={
    'backend/app/api/deps.py':deps29,
    'backend/app/ingestion/pipeline.py':pipeline29,
    'backend/app/api/routes/ingest.py':route29,
    'backend/app/vector/client.py':vector_writers29,
}


def plan(repo: Path, *, skip_reviewed_sha=False):
    root=Path(repo).resolve()
    if not (root/'.git').is_dir():
        raise SourceDrift('requires actual Git checkout')
    edits={}
    for rel,trans in TRANSFORMS.items():
        file=root/rel
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(root):
            raise SourceDrift('unsafe or missing source '+rel)
        data=file.read_bytes()
        if rel in UNCHANGED_BLOBS and not skip_reviewed_sha and git_blob(data)!=UNCHANGED_BLOBS[rel]:
            raise SourceDrift('reviewed source drift '+rel)
        updated=trans(data.decode('utf-8')).encode('utf-8')
        edits[rel]=(data,updated)
    return edits


def patch(repo:Path, *,apply=False, skip_reviewed_sha=False):
    root=Path(repo).resolve()
    edits=plan(root,skip_reviewed_sha=skip_reviewed_sha)
    report={'status':'DRY_RUN','reviewed_base':REVIEWED_BASE,'files':{
        rel:{'before_sha256':hashlib.sha256(orig).hexdigest(),'after_sha256':hashlib.sha256(new).hexdigest(),
             'diff':''.join(difflib.unified_diff(orig.decode().splitlines(True),new.decode().splitlines(True),
                                                fromfile='a/'+rel,tofile='b/'+rel))}
        for rel,(orig,new) in edits.items()}}
    if not apply:return report
    backups=[];modified=[]
    try:
        for rel in edits:
            bak=root/(rel+'.wave29.bak')
            if bak.exists() or bak.is_symlink():
                raise SourceDrift('backup already exists: '+rel)
        for rel,(old,new) in edits.items():
            file=root/rel;bak=root/(rel+'.wave29.bak')
            if file.read_bytes()!=old:
                raise SourceDrift('concurrent source modification '+rel)
            shutil.copy2(file,bak);backups.append(bak)
            file.write_bytes(new);modified.append((file,old))
    except BaseException:
        for file,old in reversed(modified):file.write_bytes(old)
        for bak in backups:bak.unlink(missing_ok=True)
        raise
    report['status']='PATCHED_REVIEW_REQUIRED'
    return report


def main(argv=None):
    cli=argparse.ArgumentParser()
    cli.add_argument('--repo',type=Path,required=True)
    cli.add_argument('--apply',action='store_true')
    args=cli.parse_args(argv)
    try:
        print(json.dumps(patch(args.repo,apply=args.apply),indent=2))
        return 0
    except (SourceDrift,OSError,ValueError,UnicodeError) as exc:
        print(json.dumps({'status':'BLOCK','error':str(exc)}))
        return 2

if __name__=='__main__':raise SystemExit(main())

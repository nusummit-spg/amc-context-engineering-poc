from pathlib import Path
import ast
import importlib.util
import pytest
from tools.amc_release.ingest_cutover29 import (deps29,pipeline29,route29,
    vector_writers29,patch,SourceDrift)

DEPS='''class Container:
    def __init__(self):
        self.vector = get_vector_store()
        self.pipeline = IngestionPipeline(
            vector_store=self.vector,
            graph_client=self.graph,
        )
        self.orchestrator = RetrievalOrchestrator(vector_store=self.vector)
        from app.compliance.rules_engine import RulesEngine
'''
PIPE='''from pathlib import Path
class Pipeline:
    async def ingest_file(self, path):
        path = Path(path)
        logger.info('ingest %s',path.name)
        return None
'''
ROUTE='''from pathlib import Path
async def ingest_file(container):
    upload_dir = Path(container.settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
async def ingest_batch(container):
    corpus_dir = Path(container.settings.corpus_dir)
    return corpus_dir
'''
VECTOR='''# W28_VERIFIED_READ_CUTOVER
class VectorStore:
    def __init__(self):
        """Initialise."""
        self._index = None
        self.ensure_collection()
    def ensure_collection(self):
        """Hydrate."""
        self._index = object()
    def _persist(self):
        """Write data."""
        return 'wrote'
    async def index_chunks(self, chunks, meta):
        """Index."""
        return 1
    async def add(self, docs):
        """Add."""
        return 2
    async def add_documents(self, docs):
        """Bulk add."""
        return 3
    async def ingest_synthetic_patch_chunk(self, id):
        """Patch."""
        return 4
    async def evict_synthetic_patch_chunk(self, id):
        """Remove."""
        return 5
    async def delete_by_chunk_id(self, id):
        """Delete."""
        return 6
'''


def test_dependency_injection_split_and_fence():
    src=deps29(DEPS)
    assert 'W29_SPLIT_INGESTION_AND_READS' in src
    assert 'self.ingestion_vector' in src
    assert 'VerifiedOrchestratorFence29' in src
    assert src.count('vector_store=self.vector')==1
    compile(src,'deps.py','exec')
    with pytest.raises(SourceDrift):deps29(src)


def test_pipeline_guard_is_before_graph():
    new=pipeline29(PIPE)
    assert new.index('W29_PIPELINE_EARLY_BLOCK') < new.index('path = Path(path)')
    compile(new,'pipeline.py','exec')
    with pytest.raises(SourceDrift):pipeline29(new)


def test_http_upload_and_batch_blocked_before_side_effects():
    new=route29(ROUTE)
    assert new.index('W29_INGEST_HTTP_GUARD') < new.index('upload_dir.mkdir')
    assert new.count('HTTP_503_SERVICE_UNAVAILABLE')==2
    compile(new,'ingest.py','exec')
    with pytest.raises(SourceDrift):route29(new)


def test_writer_guard_inserted_in_all_mutators():
    new=vector_writers29(VECTOR)
    assert new.count('W29_RAW_VECTOR_WRITE_GUARD')==8
    assert new.count('legacy direct vector mutation forbidden')==8
    assert 'W29_NO_LEGACY_HYDRATE' in new
    compile(new,'client.py','exec')
    with pytest.raises(SourceDrift):vector_writers29(new)


@pytest.mark.asyncio
@pytest.mark.parametrize('method,argv',[
    ('index_chunks',([],{})),('add',([1],)),('add_documents',([1],)),
    ('ingest_synthetic_patch_chunk',('id',)),
    ('evict_synthetic_patch_chunk',('id',)),('delete_by_chunk_id',('id',))
])
async def test_real_execution_denies_every_base_vector_mutator(monkeypatch,method,argv):
    src=vector_writers29(VECTOR)
    scope={};exec(src,scope)
    vec=scope['VectorStore']()
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    with pytest.raises(RuntimeError,match='direct vector mutation'):
        await getattr(vec,method)(*argv)


def test_real_execution_denies_persist(monkeypatch):
    scope={};exec(vector_writers29(VECTOR),scope)
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    with pytest.raises(RuntimeError):scope['VectorStore']()._persist()


def test_real_execution_preserves_legacy_off_mode(monkeypatch):
    scope={};exec(vector_writers29(VECTOR),scope)
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','off')
    v=scope['VectorStore']()
    assert v._index is not None
    assert v._persist()=='wrote'



def test_verified_constructor_does_not_touch_legacy_index(monkeypatch):
    scope={};exec(vector_writers29(VECTOR),scope)
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    assert scope['VectorStore']()._index is None


def test_legacy_hydrate_direct_call_denied(monkeypatch):
    scope={};exec(vector_writers29(VECTOR),scope)
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    with pytest.raises(RuntimeError):scope['VectorStore']().ensure_collection()

def test_mutator_missing_docstring_refuses_unsafe_patch():
    with pytest.raises(SourceDrift):
        vector_writers29(VECTOR.replace('"""Add."""','pass'))


def test_source_patcher_requires_real_checkout(tmp_path):
    with pytest.raises(SourceDrift):patch(tmp_path)


def test_dry_run_then_apply_and_backup(tmp_path):
    (tmp_path/'.git').mkdir()
    texts={'backend/app/api/deps.py':DEPS,
           'backend/app/ingestion/pipeline.py':PIPE,
           'backend/app/api/routes/ingest.py':ROUTE,
           'backend/app/vector/client.py':VECTOR}
    for path,body in texts.items():
        f=tmp_path/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(body,newline='\n')
    preview=patch(tmp_path,skip_reviewed_sha=True)
    assert preview['status']=='DRY_RUN'
    assert len(preview['files'])==4
    assert all((tmp_path/f).read_text()==src for f,src in texts.items())
    outcome=patch(tmp_path,apply=True,skip_reviewed_sha=True)
    assert outcome['status']=='PATCHED_REVIEW_REQUIRED'
    assert all((tmp_path/(f+'.wave29.bak')).exists() for f in texts)
    assert all((tmp_path/(f+'.wave29.bak')).read_text()==text for f,text in texts.items())
    with pytest.raises(SourceDrift):patch(tmp_path,skip_reviewed_sha=True)


def test_exact_sha_lock_rejects_unknown_repo(tmp_path):
    (tmp_path/'.git').mkdir()
    for path,content in {'backend/app/api/deps.py':DEPS,
        'backend/app/ingestion/pipeline.py':PIPE,
        'backend/app/api/routes/ingest.py':ROUTE,
        'backend/app/vector/client.py':VECTOR}.items():
        f=tmp_path/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(content,newline='\n')
    with pytest.raises(SourceDrift,match='drift'):patch(tmp_path)

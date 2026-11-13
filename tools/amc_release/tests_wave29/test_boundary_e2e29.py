"""Exercise transformed entrypoints; these are source-compatible stubs, not a full AMC checkout."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException,status
from tools.amc_release.ingest_cutover29 import pipeline29,route29
from amc_publication.serving27 import ServingDenied


@pytest.mark.asyncio
async def test_verified_http_ingest_rejects_before_disk_write(monkeypatch,tmp_path):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    source='''from pathlib import Path
async def ingest_file(container):
    upload_dir = Path(container.settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return True
async def ingest_batch(container):
    corpus_dir = Path(container.settings.corpus_dir)
    return True
'''
    scope={'HTTPException':HTTPException,'status':status}
    exec(route29(source),scope)
    folder=tmp_path/'never-create'
    fake=SimpleNamespace(settings=SimpleNamespace(upload_dir=str(folder),corpus_dir=str(tmp_path)))
    with pytest.raises(HTTPException) as exc:
        await scope['ingest_file'](fake)
    assert exc.value.status_code==503
    assert not folder.exists()
    with pytest.raises(HTTPException) as exc:
        await scope['ingest_batch'](fake)
    assert exc.value.status_code==503


@pytest.mark.asyncio
async def test_pipeline_guard_prevents_graph_write(monkeypatch,tmp_path):
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','enforce')
    calls=[]
    source='''from pathlib import Path
class P:
    async def ingest_file(self, path):
        path = Path(path)
        logger.info('ingest %s',path.name)
        self.graph.write()
        return path
'''
    scope={'logger':SimpleNamespace(info=lambda *a:None)}
    exec(pipeline29(source),scope)
    pipe=scope['P']()
    pipe.graph=SimpleNamespace(write=lambda:calls.append('graph-write'))
    with pytest.raises(ServingDenied):await pipe.ingest_file(tmp_path/'dummy.csv')
    assert not calls
    monkeypatch.setenv('AMC_VERIFIED_SERVING_MODE','off')
    await pipe.ingest_file(tmp_path/'dummy.csv')
    assert calls==['graph-write']

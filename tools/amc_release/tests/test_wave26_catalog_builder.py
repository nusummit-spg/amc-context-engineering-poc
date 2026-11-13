from pathlib import Path
import json
import pytest
from tools.amc_release.source_catalog26 import build, CatalogMismatch

DOCS=[{'chunk_id':'c1','tenant_id':'t','text':'first'},
      {'chunk_id':'c2','tenant_id':'t','text':'second'}]


def source(tmp_path, documents=None, count=2):
    p=tmp_path/'canonical.json'
    p.write_text(json.dumps({'tenant':'t','source_version':'v1',
         'canonical_document_count':count,'documents':documents or DOCS}))
    return p


def test_catalog_builder_roundtrip_and_nondestructive(tmp_path):
    src=source(tmp_path);out=tmp_path/'catalog.json'
    report=build(source_export=src,destination=out,expected_tenant='t',expected_version='v1',expected_count=2)
    assert report['status']=='DRY_RUN' and not out.exists()
    ok=build(source_export=src,destination=out,expected_tenant='t',expected_version='v1',expected_count=2,apply=True)
    assert ok['status']=='CREATED_REQUIRES_CANONICAL_SOURCE_ATTESTATION'
    assert len(json.loads(out.read_text())['chunks'])==2
    with pytest.raises(FileExistsError):build(source_export=src,destination=out,expected_tenant='t',expected_version='v1',expected_count=2,apply=True)


def test_deterministic_sorting_of_ids(tmp_path):
    src=source(tmp_path,documents=list(reversed(DOCS)))
    report=build(source_export=src,destination=tmp_path/'out.json',expected_tenant='t',expected_version='v1',expected_count=2,apply=True)
    assert [x['chunk_id'] for x in json.loads((tmp_path/'out.json').read_text())['chunks']]==['c1','c2']


def test_missing_canonical_row_refused(tmp_path):
    src=source(tmp_path,documents=[DOCS[0]],count=2)
    with pytest.raises(CatalogMismatch):build(source_export=src,destination=tmp_path/'out.json',expected_tenant='t',expected_version='v1',expected_count=2,apply=True)


def test_wrong_tenant_refused(tmp_path):
    src=source(tmp_path)
    with pytest.raises(CatalogMismatch):build(source_export=src,destination=tmp_path/'out.json',expected_tenant='other',expected_version='v1',expected_count=2)


def test_duplicate_chunk_id_refused(tmp_path):
    src=source(tmp_path,documents=[DOCS[0],DOCS[0]])
    with pytest.raises(CatalogMismatch):build(source_export=src,destination=tmp_path/'out.json',expected_tenant='t',expected_version='v1',expected_count=2,apply=True)

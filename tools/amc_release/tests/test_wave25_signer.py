import importlib.util
import hashlib
import json
import sys
from pathlib import Path
import pytest

W19_PATH = Path(__file__).resolve().parents[3] / 'backend'
if not (W19_PATH/'amc_publication/models.py').is_file():
    W19_PATH = Path(__file__).resolve().parents[3] / 'test_support/baseline/backend'
if W19_PATH.exists():
    sys.path.insert(0,str(W19_PATH))

ROOT=Path(__file__).resolve().parents[3]
for name,file in [('amc_publication.approval_adapter','backend/amc_publication/approval_adapter.py'),
                  ('tools.amc_release.sign_corpus25','tools/amc_release/sign_corpus25.py')]:
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
from tools.amc_release.sign_corpus25 import sign
from amc_publication.approval_adapter import load_verified_corpus

KEY='this-is-an-offline-TEST-key-that-is-never-for-production'

def payload(tmp_path):
    digest=hashlib.sha256(b'catalog-integrity').hexdigest()
    doc={'tenant':'t','proposal_id':'p','approved_revision':1,'source_version':'version-1',
         'source_manifest_sha256':digest,'complete':True,
         'documents':[{'chunk_id':'c1','tenant_id':'t','text':'document body'}]}
    f=tmp_path/'payload.json';f.write_text(json.dumps(doc))
    return f,digest

def test_signer_round_trip_with_reviewed_payload(tmp_path):
    file,digest=payload(tmp_path);dest=tmp_path/'signed.json'
    dry=sign(payload_path=file,output_path=dest,key=KEY,expected_manifest_sha256=digest)
    assert dry['status']=='DRY_RUN' and not dest.exists()
    out=sign(payload_path=file,output_path=dest,key=KEY,expected_manifest_sha256=digest,apply=True)
    assert out['status']=='SIGNED_REQUIRES_EXTERNAL_COMPLETENESS_REVIEW'
    assert load_verified_corpus(dest,KEY,tenant='t',proposal_id='p',revision=1).documents[0]['chunk_id']=='c1'
    with pytest.raises(FileExistsError):sign(payload_path=file,output_path=dest,key=KEY,expected_manifest_sha256=digest,apply=True)

def test_signer_denies_wrong_external_manifest(tmp_path):
    file,digest=payload(tmp_path)
    with pytest.raises(ValueError):sign(payload_path=file,output_path=tmp_path/'signed.json',key=KEY,expected_manifest_sha256='0'*64,apply=True)
    assert not (tmp_path/'signed.json').exists()

def test_signer_denies_malformed_or_incomplete_corpus(tmp_path):
    file,digest=payload(tmp_path)
    body=json.loads(file.read_text());body['documents']=[];file.write_text(json.dumps(body))
    with pytest.raises(ValueError):sign(payload_path=file,output_path=tmp_path/'signed.json',key=KEY,expected_manifest_sha256=digest,apply=True)
    assert not (tmp_path/'signed.json').exists()

def test_signer_denies_missing_secret(tmp_path):
    file,digest=payload(tmp_path)
    with pytest.raises(ValueError):sign(payload_path=file,output_path=tmp_path/'signed.json',key='no',expected_manifest_sha256=digest,apply=True)

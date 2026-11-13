import json
from pathlib import Path
import pytest
from tools.amc_release.quarantine29 import run
from amc_publication.ingestion_boundary29 import IngestionQuarantineError,ImmutableIngestionQuarantine29

@pytest.fixture
def record(tmp_path):
    p=tmp_path/'candidate.json';p.write_text(json.dumps({
       'tenant':'a','source_version':'s1','batch_id':'B','submitted_by':'operator',
       'documents':[{'tenant_id':'a','chunk_id':'c1','text':'document content',
                     'source_version':'s1','source_sha256':'a'*64}]}))
    return p


def test_preview_is_not_a_write(record,tmp_path):
    root=tmp_path/'quarantine'
    assert run(record,root)['state']=='DRY_RUN_VALIDATED_UNAPPROVED'
    assert not root.exists()


def test_explicit_apply_stages_non_active_candidate(record,tmp_path):
    root=tmp_path/'quarantine'
    result=run(record,root,apply=True)
    assert result['publication_authorized'] is False
    assert ImmutableIngestionQuarantine29(root).verify(result['candidate_sha256'],tenant='a')['complete_corpus'] is False


def test_invalid_payload_shape_denied(record,tmp_path):
    record.write_text('{}')
    with pytest.raises(IngestionQuarantineError):run(record,tmp_path/'quarantine')


def test_untrusted_input_never_constructs_canonical_manifest(record,tmp_path):
    result=run(record,tmp_path/'stage',apply=True)
    assert result['state']=='QUARANTINED_UNAPPROVED'
    data=ImmutableIngestionQuarantine29(tmp_path/'stage').verify(result['candidate_sha256'],tenant='a')
    assert 'canonical_source_inventory' not in data
    assert 'reviewed_by' not in data

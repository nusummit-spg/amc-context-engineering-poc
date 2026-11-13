"""Wave 2.6 surgical patch contracts, source drift, and safe admission response."""
from pathlib import Path
import pytest
from tools.amc_release import publication_patch25 as prior
from tools.amc_release import publication_patch26 as mod
from tools.amc_release.tests.test_wave25_patcher import WORKER, JOURNAL, GOVERNANCE


def worker25():
    text=prior.harden_worker(WORKER)
    graph='''        postimage = {"value": corrected_value}
        self.journal.prepare(claim, kind="graph", target=entity, 
                            pre=preimage, post=postimage)
        self.graph.compare_and_set(
                    tenant, entity, attribute, preimage, corrected_value, claim.fence
                )
        self.graph.compare_and_set(
                tenant, entity, attribute, preimage, corrected_value, claim.fence
            )
'''
    # Insert faithful source-level fragments into the simulated worker body.
    text=text.replace('    def process(self, payload, tenant, entity, claim):\n',
        '    def process(self, payload, tenant, entity, claim):\n'+graph)
    rb='''                current_value = self.graph.read(tenant, entity, attribute)
                # Restore graph to preimage value using current value as expected
                self.graph.compare_and_set(
                    tenant, entity, attribute,
                    current_value,
                    preimage.get("value"),  # Restore to preimage
                    claim.fence
                )
        
        # Compensate graph effect'''
    return text+'\n    def restore_graph(self, tenant, entity, attribute, preimage, effect, claim):\n'+rb+'\n'


def journal25():
    text=prior.harden_journal(JOURNAL)
    method='''    def switch_pointer(self, claim: Claim, *, namespace: str, expected: dict, new_id: str, digest: str):
        with self.sessions.begin() as s:
            self._require(s, claim)
            row = s.get(GenerationPointer, (claim.tenant, namespace))
            cur = {"generation_id": row.generation_id, "digest": row.artifact_digest, "epoch": row.epoch} if row else {"generation_id": None, "digest": None, "epoch": 0}
            if cur["generation_id"] == new_id and cur["digest"] == digest:
                # Replay after crash: already switched to our generation.
                return
            if cur != expected:
                raise Conflict("active generation pointer changed since preimage; refusing stale activation")
            if row:
                row.generation_id, row.artifact_digest, row.epoch, row.activated_at = new_id, digest, row.epoch + 1, utcnow()
            else:
                s.add(GenerationPointer(tenant=claim.tenant, namespace=namespace, generation_id=new_id,
                                        artifact_digest=digest, epoch=1))

    def publish(self, claim):
        pass
'''
    return text+'\n'+method


def governance25():
    text=prior.harden_governance(GOVERNANCE)
    return text+'''\ndef submit_pending(status, work_id):
    # Return 202 Accepted — the worker will verify effects before publishing.
    raise HTTPException(
        status_code=status.HTTP_202_ACCEPTED,
        detail={
            "message": "Publication intent queued. Worker will verify graph/vector effects.",
            "work_id": work_id,
            "status_url": f"/api/publication/status/{work_id}",
        },
    )
'''


def test_harden_worker_reuses_original_graph_effect():
    out=mod.harden_worker26(worker25())
    assert 'W26_DURABLE_GRAPH_PREIMAGE' in out
    assert out.count('durable_graph_before, corrected_value, claim.fence')==2
    assert 'W26_GRAPH_ROLLBACK_CAS' in out
    assert 'graph rollback readback did not restore original value' in out
    assert out.index('self.serving_probe(tenant, generation.generation_id, generation.digest)') < out.index('self.journal.verified(claim, kind="vector", target=entity, observed=observed_vector)')
    compile(out, 'worker.py', 'exec')


def test_harden_journal_locks_pointer_and_guards_epoch():
    out=mod.harden_journal26(journal25())
    assert 'W26_POINTER_ROW_LOCK' in out
    assert 'with_for_update=True, populate_existing=True' in out
    assert 'active pointer epoch drift' in out
    compile(out, 'journal.py', 'exec')


def test_harden_governance_http_202_is_normal_response():
    out=mod.harden_governance26(governance25())
    assert 'W26_ACCEPTED_JSON' in out
    assert 'return JSONResponse' in out
    assert 'raise HTTPException(\n        status_code=status.HTTP_202_ACCEPTED' not in out
    compile(out, 'governance.py', 'exec')

@pytest.mark.parametrize('f,data',[
    (mod.harden_worker26,worker25()),
    (mod.harden_journal26,journal25()),
    (mod.harden_governance26,governance25()),
])
def test_reapplying_patch_is_refused(f,data):
    with pytest.raises(mod.SourceDrift):f(f(data))


def test_missing_original_graph_effect_blocks_patch():
    text=worker25().replace('self.journal.prepare(claim, kind="graph", target=entity, ','self.journal.DO_NOT_PREPARE(claim, kind="graph", target=entity, ')
    with pytest.raises(mod.SourceDrift):mod.harden_worker26(text)


def test_duplicate_pointer_method_refused():
    text=journal25()
    text += text[text.index('    def switch_pointer('):]
    with pytest.raises(mod.SourceDrift):mod.harden_journal26(text)


def test_drifted_http_response_blocked():
    text=governance25().replace('status.HTTP_202_ACCEPTED','status.HTTP_200_OK')
    with pytest.raises(mod.SourceDrift):mod.harden_governance26(text)

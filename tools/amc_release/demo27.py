"""Disposable simulated end-to-end publication -> answer eligibility -> rollback.

Strictly a local engineering demonstration. Never returns UAT/PASS and never
connects to real data. Requires SQLAlchemy and the Wave 1.9 publication code.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# The standalone ZIP carries the old publication package as test support but
# new modules in backend/amc_publication. A real AMC checkout has both together.
import amc_publication
_package_root=Path(__file__).resolve().parents[2]
_addon=_package_root/'backend/amc_publication'
if _addon.is_dir() and str(_addon) not in amc_publication.__path__:
    amc_publication.__path__.insert(0,str(_addon))

from amc_publication.models import Base
from amc_publication.journal import Journal
from amc_publication.graph import InMemoryGraphPort
from amc_publication.artifacts import ImmutableSnapshotStore
from amc_publication.feedback import FeedbackCausality
from amc_publication.serving27 import VerifiedGenerationResolver, ServingDenied
from amc_publication.reconcile27 import inspect


def exercise() -> dict:
    with TemporaryDirectory(prefix='amc-wave27-demo-') as tmp:
        root=Path(tmp)
        eng=create_engine('sqlite:///'+str(root/'simulated.sqlite'))
        Base.metadata.create_all(eng)
        sessions=sessionmaker(bind=eng,expire_on_commit=False)
        journal=Journal(sessions)
        graph=InMemoryGraphPort()
        graph.seed('sandbox_tenant','scheme-1','name','Old Name')
        store=ImmutableSnapshotStore(root/'snapshots')
        docs=[{'tenant_id':'sandbox_tenant','chunk_id':'evidence-001','text':'Verified synthetic scheme fact'}]
        work_id=journal.submit(tenant='sandbox_tenant',key='demo-1',proposal_id='reviewed-demo',revision=1,
            payload={'entity':'scheme-1','attribute':'name','corrected_value':'New Name',
                     'full_vector_snapshot':docs})
        # The historical Wave 1.9 test worker emits vector effects without
        # `count`. Compose the CURRENT contract explicitly using real durable
        # Journal operations rather than weakening serving-count verification.
        claim=journal.claim('demo-worker')
        if claim is None or claim.work_id != work_id:
            raise RuntimeError('simulated work not claimable')
        old_graph=graph.read('sandbox_tenant','scheme-1','name')
        graph_target='scheme-1:name'
        journal.prepare(claim,kind='graph',target=graph_target,
                        pre=old_graph,post={'value':'New Name'})
        graph.compare_and_set('sandbox_tenant','scheme-1','name',old_graph,'New Name',claim.fence)
        observed=graph.read('sandbox_tenant','scheme-1','name')
        journal.verified(claim,kind='graph',target=graph_target,observed=observed)
        gen=store.stage('sandbox_tenant',docs)
        pointer_before=journal.pointer('sandbox_tenant')
        post={'generation_id':gen.digest,'digest':gen.digest,'count':gen.count}
        journal.prepare(claim,kind='vector',target='vector_faiss',pre=pointer_before,post=post)
        journal.switch_pointer(claim,namespace='vector_faiss',expected=pointer_before,
                               new_id=gen.digest,digest=gen.digest)
        journal.verified(claim,kind='vector',target='vector_faiss',observed=post)
        receipt=journal.publish(claim)
        published={'status':'published','receipt_id':receipt}
        resolver=VerifiedGenerationResolver(sessions,store,serving_loader=lambda *_:True)
        served=resolver.resolve_for_serving('sandbox_tenant')
        causality=FeedbackCausality(sessions)
        if not causality.resolve('sandbox_tenant','issue-demo',work_id,served.receipt_id):
            raise RuntimeError('feedback causality did not resolve')
        before=inspect(sessions,'sandbox_tenant').to_dict()
        journal.request_rollback(work_id,'sandbox_tenant')
        rollback_claim=journal.claim('demo-worker-rollback')
        if rollback_claim is None or rollback_claim.mode!='rollback':
            raise RuntimeError('simulated rollback not claimable')
        journal.switch_back(rollback_claim,current_id=gen.digest,current_digest=gen.digest,
                            before=pointer_before)
        journal.compensate(rollback_claim,'vector','vector_faiss')
        current=graph.read('sandbox_tenant','scheme-1','name')
        graph.compare_and_set('sandbox_tenant','scheme-1','name',current,'Old Name',rollback_claim.fence)
        assert graph.read('sandbox_tenant','scheme-1','name')==old_graph
        journal.compensate(rollback_claim,'graph',graph_target)
        journal.finish_rollback(rollback_claim)
        rollback={'status':'rolled_back'}
        try:
            resolver.resolve_for_serving('sandbox_tenant')
        except ServingDenied:
            serving_revoked=True
        else:
            serving_revoked=False
        if not serving_revoked:
            raise RuntimeError('rolled-back generation remained serving eligible')
        reopened=causality.reopen_after_rollback('sandbox_tenant',work_id)
        after=inspect(sessions,'sandbox_tenant').to_dict()
        eng.dispose()
        if reopened!=1 or after['database_integrity']!='PASS':
            raise RuntimeError('post-rollback feedback/reconciliation error')
        return {
            'mode':'DISPOSABLE_SQLITE_JOURNAL_MANUAL_COMPOSITION_IN_MEMORY_GRAPH_JSON_SNAPSHOT',
            'publication':published['status'],
            'eligible_before_rollback':True,
            'reconciliation_before':before['database_integrity'],
            'rollback':rollback['status'],
            'serving_revoked':serving_revoked,
            'feedback_reopened':reopened,
            'reconciliation_after':after['database_integrity'],
            'real_faiss':'NOT_RUN', 'real_neo4j':'NOT_RUN','uat':'BLOCK'
        }


def main():
    print(json.dumps(exercise(),indent=2))

if __name__=='__main__':main()

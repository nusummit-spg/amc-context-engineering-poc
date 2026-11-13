"""Disposable SQLite / JSON artifacts only; never represents live UAT proof."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tools.amc_release.composition import inspect
from amc_publication.models import Base, PublicationReceipt, FeedbackPublicationLink
from amc_publication.journal import Journal
from amc_publication.graph import InMemoryGraphPort
from amc_publication.worker import PublicationWorker
from amc_publication.artifacts import ImmutableSnapshotStore


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        root=Path(self.t.name)
        self.engine=create_engine('sqlite:///'+str(root/'test.db'))
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(self.engine)
        self.journal=Journal(self.sessions)
        self.graph=InMemoryGraphPort()
        self.graph.seed('tenant-a', 'AMC01', 'name', 'old')
        self.snapshots=ImmutableSnapshotStore(root/'gen')
        self.work=self.journal.submit(tenant='tenant-a', key='key-a', proposal_id='p1',revision=1,
            payload={'entity':'AMC01','attribute':'name','corrected_value':'new',
                     'full_vector_snapshot':[{'chunk_id':'c1','tenant_id':'tenant-a','text':'doc'}]})
        self.out=PublicationWorker(self.journal,self.graph,self.snapshots,simulation_mode=True).run_once()
        self.assertEqual(self.out['status'],'published')

    def result(self, **kw):
        return inspect(sessions=self.sessions,graph=self.graph,snapshots=self.snapshots,
                       tenant='tenant-a',work_id=self.work,**kw)
    def test_complete_simulated_pub_but_never_release_evidence(self):
        r=self.result()
        self.assertEqual(r.status,'SIMULATION_ONLY')
        self.assertTrue(r.checks['GRAPH_INDEPENDENT_READBACK'])
        self.assertFalse(r.release_evidence_eligible)
    def test_live_requested_with_fake_adapters_blocked(self):
        r=self.result(mode='live')
        self.assertEqual(r.status,'FAIL')
        self.assertIn('REAL_EXTERNAL_ADAPTERS',r.reasons)
    def test_actual_graph_tampering_fails(self):
        self.graph.values[('tenant-a','AMC01','name')]=('spoofed',999)
        r=self.result()
        self.assertEqual(r.status,'FAIL')
        self.assertIn('GRAPH_INDEPENDENT_READBACK',r.reasons)
    def test_wrong_tenant_not_disclosed(self):
        r=inspect(sessions=self.sessions,graph=self.graph,snapshots=self.snapshots,
                  tenant='tenant-b',work_id=self.work)
        self.assertEqual(r.status,'FAIL')
        self.assertIn('TENANT_SCOPED_PUBLISHED_WORK',r.reasons)
    def test_receipt_not_verified_fails(self):
        with self.sessions.begin() as s:
            rec=s.query(PublicationReceipt).filter_by(work_id=self.work).one()
            rec.verified=False
        self.assertIn('VERIFIED_TENANT_RECEIPT',self.result().reasons)
    def test_mismatched_generation_fails(self):
        with self.sessions.begin() as s:
            rec=s.query(PublicationReceipt).filter_by(work_id=self.work).one()
            rec.generation_id='f'*64
        self.assertIn('CURRENT_POINTER_MATCHES_RECEIPT',self.result().reasons)
    def test_vector_artifact_tamper_detected(self):
        digest=self.journal.pointer('tenant-a')['digest']
        path=self.snapshots._path(digest)/'snapshot.json'
        path.write_text('{"corrupt":true}')
        self.assertIn('IMMUTABLE_GENERATION_READBACK',self.result().reasons)
    def test_feedback_requires_real_matching_link(self):
        self.assertIn('TENANT_SCOPED_FEEDBACK',self.result(expected_issue_id='i1').reasons)
        with self.sessions.begin() as s:
            s.add(FeedbackPublicationLink(tenant='tenant-a',issue_id='i1',work_id=self.work,
                receipt_id=self.out['receipt_id'],status='resolved'))
        self.assertEqual(self.result(expected_issue_id='i1').status,'SIMULATION_ONLY')
    def test_rollback_cannot_pass_publication_audit(self):
        self.journal.request_rollback(self.work,'tenant-a')
        PublicationWorker(self.journal,self.graph,self.snapshots,simulation_mode=True).run_once()
        self.assertEqual(self.result().status,'FAIL')
    def test_missing_work_fails(self):
        r=inspect(sessions=self.sessions,graph=self.graph,snapshots=self.snapshots,
            tenant='tenant-a',work_id='missing')
        self.assertEqual(r.status,'FAIL')
    def test_invalid_mode_fails(self):
        with self.assertRaises(ValueError):self.result(mode='production')

if __name__ == '__main__': unittest.main()

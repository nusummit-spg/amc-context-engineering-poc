"""Execute SQLite + fake graph recovery demo. NOT a production deployment test.

Usage (from backend/): python -m amc_publication.demo_smoke
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
from .journal import Journal
from .artifacts import ImmutableSnapshotStore
from .graph import InMemoryGraphPort
from .worker import PublicationWorker
from .integration import ApprovedProposal, queue_verified_approval
from .feedback import FeedbackCausality


def main():
    with TemporaryDirectory(prefix="amc-wave19-demo-") as root:
        engine = create_engine("sqlite:///" + str(Path(root)/"journal.sqlite"))
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        journal = Journal(sessions)
        graph = InMemoryGraphPort()
        graph.seed("tenant-demo", "AMC-1", "display_name", "Old AMC")
        store = ImmutableSnapshotStore(Path(root)/"snapshots")
        proposal = ApprovedProposal("p-demo", "tenant-demo", 1, "analyst", "reviewer", "approved",
                                    "AMC-1", "display_name", "Corrected AMC")
        work = queue_verified_approval(journal, proposal,
                        [{"chunk_id": "demo-1", "tenant_id": "tenant-demo", "text": "Corrected AMC"}])
        worker = PublicationWorker(journal, graph, store, simulation_mode=True)
        published = worker.run_once()
        assert published["status"] == "published", published
        feedback = FeedbackCausality(sessions)
        assert feedback.resolve("tenant-demo", "issue-demo", work, published["receipt_id"])
        print("SIMULATED PUBLISH: verified persisted graph and snapshot receipts", published)
        journal.request_rollback(work, "tenant-demo")
        rolled = worker.run_once()
        assert rolled["status"] == "rolled_back", rolled
        assert feedback.reopen_after_rollback("tenant-demo", work) == 1
        print("SIMULATED ROLLBACK:", rolled)
        print("NOTE: live Neo4j, FAISS reader hot-swap and PostgreSQL concurrency NOT tested")


if __name__ == "__main__":
    main()

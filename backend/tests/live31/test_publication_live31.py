"""WP03 + WP04 / gates G3, G4: durable publication on real PostgreSQL + real Neo4j + real FAISS.

No mocks of the systems under test. Each test has its own migrated PostgreSQL database; the Neo4j
graph is cleaned around every test. Crashes are simulated with BaseException at the worker's
failpoints, i.e. the process "dies" mid-publication and a NEW worker has to recover from durable state.
"""
import threading
import time
from datetime import timedelta

import pytest

from amc_publication.journal import Journal
from amc_publication.types import Conflict, LeaseLost
from amc_publication.worker import PublicationWorker
from tests.live31 import support
from tests.live31.support import ALPHA, BETA, Crash, crash_at, pg_state, read_fence, read_graph, seed_graph, serving_allowed

LEGACY = "0.25"          # the graph value before any publication


def _seed(stack, tenant=ALPHA, generation="A"):
    entity, attr, _ = support.graph_target(tenant, generation)
    seed_graph(stack.driver, tenant, entity, attr, LEGACY)
    return entity, attr


def _publish(stack, tenant, generation, **kw):
    work = stack.submit(tenant, generation, **kw)
    result = stack.worker().run_once()
    assert result["status"] == "published", result
    return work, result


def _assert_consistent(stack, tenant, entity, attr, expect_value, expect_work):
    """The cross-system invariant after any completed publication."""
    st = pg_state(stack.sessions, tenant)
    a, p = st["authority"], st["pointer"]
    assert a and a["status"] == "ACTIVE" and a["suspended_by"] is None
    assert (a["generation"], a["digest"], a["epoch"]) == (p["generation"], p["digest"], p["epoch"])
    assert a["work"] == expect_work
    assert read_graph(stack.driver, tenant, entity, attr) == expect_value
    assert st["claim"]["status"] == "RELEASED"
    assert serving_allowed(stack, tenant)


# ----------------------------------------------------------------------------- happy path


def test_publish_replace_and_rollback_across_postgres_neo4j_and_faiss(live_stack):
    entity, attr = _seed(live_stack)
    work_a, _ = _publish(live_stack, ALPHA, "A")
    _assert_consistent(live_stack, ALPHA, entity, attr, "0.21", work_a)
    st_a = pg_state(live_stack.sessions, ALPHA)
    assert read_fence(live_stack.driver, ALPHA, entity) is not None, "graph fence must be recorded"

    work_b, _ = _publish(live_stack, ALPHA, "B")
    _assert_consistent(live_stack, ALPHA, entity, attr, "0.19", work_b)
    st_b = pg_state(live_stack.sessions, ALPHA)
    assert st_b["authority"]["digest"] != st_a["authority"]["digest"]
    assert st_b["authority"]["epoch"] > st_a["authority"]["epoch"], "epochs must be monotonic"

    live_stack.journal.request_rollback(work_b, ALPHA)
    assert not serving_allowed(live_stack, ALPHA), "serving must be suspended as soon as rollback is requested"
    result = live_stack.worker().run_once()
    assert result["status"] == "rolled_back", result
    st = pg_state(live_stack.sessions, ALPHA)
    assert (st["authority"]["digest"], st["authority"]["status"]) == (st_a["authority"]["digest"], "ACTIVE")
    assert st["authority"]["work"] == work_a
    assert read_graph(live_stack.driver, ALPHA, entity, attr) == "0.21", "graph must be restored by compensation"
    assert st["claim"]["status"] == "RELEASED" and serving_allowed(live_stack, ALPHA)
    assert st["authority"]["epoch"] > st_b["authority"]["epoch"], "rollback is a new epoch, never a rewind"


def test_rollback_of_the_first_publication_returns_to_the_fail_closed_state(live_stack):
    entity, attr = _seed(live_stack)
    work_a, _ = _publish(live_stack, ALPHA, "A")
    live_stack.journal.request_rollback(work_a, ALPHA)
    assert live_stack.worker().run_once()["status"] == "rolled_back"
    st = pg_state(live_stack.sessions, ALPHA)
    assert st["authority"] is None and st["pointer"] is None
    assert read_graph(live_stack.driver, ALPHA, entity, attr) == LEGACY
    assert not serving_allowed(live_stack, ALPHA), "no prior authority: must stay denied, not guessed"


def test_resubmitting_the_same_work_is_idempotent(live_stack):
    _seed(live_stack)
    w1 = live_stack.submit(ALPHA, "A", key="same-key")
    w2 = live_stack.submit(ALPHA, "A", key="same-key")
    assert w1 == w2
    assert live_stack.worker().run_once()["status"] == "published"
    assert live_stack.worker().run_once()["status"] == "no_jobs"
    assert len(pg_state(live_stack.sessions, ALPHA)["receipts"]) == 1


def test_same_idempotency_key_with_a_different_payload_is_refused(live_stack):
    live_stack.submit(ALPHA, "A", key="k")
    with pytest.raises(Conflict):
        live_stack.submit(ALPHA, "B", key="k")


# ----------------------------------------------------------------------------- tenant isolation


def test_publication_never_touches_another_tenants_graph_or_authority(live_stack):
    entity, attr = _seed(live_stack, ALPHA)
    seed_graph(live_stack.driver, BETA, entity, attr, "beta-owned-value")     # SAME entity id, other tenant
    work, _ = _publish(live_stack, ALPHA, "A")
    assert read_graph(live_stack.driver, BETA, entity, attr) == "beta-owned-value"
    assert read_fence(live_stack.driver, BETA, entity) is None
    beta = pg_state(live_stack.sessions, BETA)
    assert beta["authority"] is None and beta["pointer"] is None and beta["works"] == {}
    assert not serving_allowed(live_stack, BETA)


def test_two_tenants_publish_concurrently_without_contention(live_stack):
    ea, aa = _seed(live_stack, ALPHA)
    eb, ab = _seed(live_stack, BETA)
    live_stack.submit(ALPHA, "A")
    live_stack.submit(BETA, "A")
    results, errors = [], []

    def run():
        try:
            results.append(live_stack.worker().run_once()["status"])
        except BaseException as exc:      # noqa: BLE001
            errors.append(exc)
    threads = [threading.Thread(target=run) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(60) for t in threads]
    assert errors == [] and results == ["published", "published"]
    for tenant, e, a in ((ALPHA, ea, aa), (BETA, eb, ab)):
        st = pg_state(live_stack.sessions, tenant)
        assert st["authority"]["status"] == "ACTIVE" and serving_allowed(live_stack, tenant)


# ----------------------------------------------------------------------------- first-publisher race (G3)


def _race_once(stack_factory, tenant: str):
    """Two workers claim two DIFFERENT works for the same empty tenant at the same moment."""
    stack = stack_factory()
    entity, attr, _ = support.graph_target(tenant, "A")
    seed_graph(stack.driver, tenant, entity, attr, LEGACY)
    w_a = stack.submit(tenant, "A", key="race-a")
    w_b = stack.submit(tenant, "B", key="race-b")
    barrier = threading.Barrier(2)
    outcomes = {}

    def run(name):
        worker = stack.worker(owner=name)
        barrier.wait()
        try:
            outcomes[name] = worker.run_once()["status"]
        except BaseException as exc:      # noqa: BLE001  a Conflict here is the loser being denied
            outcomes[name] = type(exc).__name__
    threads = [threading.Thread(target=run, args=(n,)) for n in ("w1", "w2")]
    [t.start() for t in threads]
    [t.join(90) for t in threads]
    return stack, (w_a, w_b), outcomes, (entity, attr)


@pytest.mark.parametrize("round_no", range(8))
def test_first_publisher_race_has_exactly_one_owner(live_pg, live_neo4j_driver, tmp_path, round_no):
    support.clean_graph(live_neo4j_driver)
    tenant = f"live31_race_{round_no}"
    factory = lambda: support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "f", lease_seconds=2)
    stack, works, outcomes, (entity, attr) = _race_once(factory, tenant)
    # Both outcomes are legitimate: the loser is denied while the winner holds the scope, OR it runs
    # afterwards as a replacement publication. What is never legitimate is overlap or a wedged tenant,
    # which the invariants below catch. Drive everything to a terminal state first.
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            r = stack.worker().run_once()
        except BaseException:             # noqa: BLE001
            r = {"status": "error"}
        if r["status"] == "no_jobs":
            if all(s in ("published", "failed") for s in pg_state(stack.sessions, tenant)["works"].values()):
                break
        time.sleep(0.5)
    st = pg_state(stack.sessions, tenant)
    # Invariants no matter who won:
    assert st["authority"] and st["authority"]["status"] == "ACTIVE" and st["authority"]["suspended_by"] is None
    assert st["authority"]["work"] in works and st["works"][st["authority"]["work"]] == "published"
    assert (st["authority"]["generation"], st["authority"]["epoch"]) == (st["pointer"]["generation"], st["pointer"]["epoch"])
    assert st["claim"]["status"] == "RELEASED", "no stranded HELD claim"
    owner_is_a = st["authority"]["work"] == works[0]
    expected_value = "0.21" if owner_is_a else "0.19"
    final_graph = read_graph(stack.driver, tenant, entity, attr)
    # The graph must reflect the work the receipt names. If both published in sequence the last
    # one wins in BOTH systems; a mixed state (graph from one work, receipt from another) is the bug.
    assert final_graph == expected_value, (final_graph, st["works"], st["authority"])
    assert len(st["receipts"]) == len([w for w, s in st["works"].items() if s == "published"])
    assert serving_allowed(stack, tenant)


# ----------------------------------------------------------------------------- stale writer / fencing


def test_a_stale_worker_cannot_mutate_after_its_lease_was_taken(live_stack):
    _seed(live_stack)
    journal = Journal(live_stack.sessions, lease_seconds=1)
    live_stack.submit(ALPHA, "A")
    stale = journal.claim("old_worker")
    assert stale is not None
    later = journal.claim("new_worker", now=stale and (__import__("datetime").datetime.utcnow() + timedelta(seconds=30)))
    assert later is not None and later.work_id == stale.work_id and later.fence > stale.fence
    with pytest.raises(LeaseLost):
        journal.prepare(stale, kind="graph", target="X", pre={"value": 1}, post={"value": 2})
    assert pg_state(live_stack.sessions, ALPHA)["claim"] is None, "a stale writer must not take the scope claim"


def test_a_stale_graph_fence_is_rejected_by_neo4j(live_stack):
    entity, attr = _seed(live_stack)
    g = live_stack.graph
    g.compare_and_set(ALPHA, entity, attr, {"value": LEGACY}, "new", fence=10)
    with pytest.raises(Conflict):
        g.compare_and_set(ALPHA, entity, attr, {"value": "new"}, "older", fence=3)
    assert read_graph(live_stack.driver, ALPHA, entity, attr) == "new"


def test_graph_cas_refuses_a_changed_preimage(live_stack):
    entity, attr = _seed(live_stack)
    with pytest.raises(Conflict):
        live_stack.graph.compare_and_set(ALPHA, entity, attr, {"value": "not-the-current-value"}, "x", fence=5)
    assert read_graph(live_stack.driver, ALPHA, entity, attr) == LEGACY


def test_graph_port_enforces_attribute_allowlist_and_is_not_injectable(live_stack):
    entity, attr = _seed(live_stack)
    with pytest.raises(ValueError):
        live_stack.graph.read(ALPHA, entity, "password")
    hostile = "x'}) DETACH DELETE n //"
    with pytest.raises(Exception):
        live_stack.graph.read(ALPHA, hostile, attr)           # no such node: read fails, nothing is deleted
    assert read_graph(live_stack.driver, ALPHA, entity, attr) == LEGACY


def test_a_publication_that_started_before_a_concurrent_one_finished_does_not_wedge_the_tenant(
        live_pg, live_neo4j_driver, tmp_path):
    """Regression for the stale-preimage wedge found by the race test.

    Worker 2 claims work B; BEFORE it takes the scope, worker 1 publishes work A completely.
    Old behaviour: worker 2 had already read the graph preimage, so its graph CAS conflicted on every
    retry and the tenant stayed suspended (serving denied) with no way out but an operator.
    Correct behaviour: worker 2 takes the scope first, reads the CURRENT preimage and publishes B as
    a clean replacement of A.
    """
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "f", lease_seconds=2)
    entity, attr = _seed(stack)
    work_b = stack.submit(ALPHA, "B", key="b-first")      # oldest job: worker 2 claims this one
    work_a = stack.submit(ALPHA, "A", key="a-second")
    ran_a = []

    def let_worker1_publish_a_now(name):
        if name == "before_scope_acquired" and not ran_a:
            ran_a.append(stack.worker(owner="worker1").run_once())

    first = stack.worker(owner="worker2", failpoint=let_worker1_publish_a_now).run_once()
    assert ran_a and ran_a[0]["status"] == "published", ran_a
    # Worker 2's claim token is OLDER than worker 1's, so the graph's global fence correctly refuses its
    # first mutation. That is a clean failure plus a retry (new, higher fence) - not a wedge.
    assert first["status"] == "failed" and "fencing" in first["error"], first
    for _ in range(4):
        if stack.worker().run_once()["status"] == "published":
            break
    st = pg_state(stack.sessions, ALPHA)
    assert st["works"] == {work_a: "published", work_b: "published"}, st["works"]
    _assert_consistent(stack, ALPHA, entity, attr, "0.19", work_b)


def test_a_second_publisher_is_denied_while_the_first_holds_the_scope(live_pg, live_neo4j_driver, tmp_path):
    """No overlap: once worker 2 holds the scope, worker 1 is denied; both finish one after the other."""
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "f", lease_seconds=2)
    entity, attr = _seed(stack)
    work_b = stack.submit(ALPHA, "B", key="b-first")
    work_a = stack.submit(ALPHA, "A", key="a-second")
    denied = []

    def try_to_overlap(name):
        if name == "graph_preimage_committed" and not denied:     # worker 2 now HOLDS the scope
            try:
                stack.worker(owner="worker1").run_once()
                denied.append("NOT DENIED")
            except Conflict as exc:
                denied.append(str(exc))

    assert stack.worker(owner="worker2", failpoint=try_to_overlap).run_once()["status"] == "published"
    assert denied and "owns tenant/namespace mutation scope" in denied[0], denied
    deadline = time.time() + 40
    while time.time() < deadline:
        stack.worker().run_once() if False else None
        try:
            r = stack.worker().run_once()
        except BaseException:         # noqa: BLE001
            r = {"status": "error"}
        if pg_state(stack.sessions, ALPHA)["works"].get(work_a) == "published":
            break
        time.sleep(0.5)
    st = pg_state(stack.sessions, ALPHA)
    assert st["works"] == {work_a: "published", work_b: "published"}, st["works"]
    _assert_consistent(stack, ALPHA, entity, attr, "0.21", work_a)      # A replaced B, in both systems


# ----------------------------------------------------------------------------- crash and replay (G3/G4)

CRASH_POINTS = ["graph_preimage_committed", "vector_preimage_committed", "graph_written",
                "graph_verified", "pointer_switched", "vector_verified"]


@pytest.mark.parametrize("point", CRASH_POINTS)
def test_crash_during_replacement_converges_to_one_verified_corpus(live_pg, live_neo4j_driver, tmp_path, point):
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "f", lease_seconds=1)
    entity, attr = _seed(stack)
    work_a, _ = _publish(stack, ALPHA, "A")
    work_b = stack.submit(ALPHA, "B")

    with pytest.raises(Crash):
        stack.worker(failpoint=crash_at(point)).run_once()

    mid = pg_state(stack.sessions, ALPHA)
    graph_prepared = point not in ("graph_preimage_committed", "vector_preimage_committed")
    if graph_prepared:
        assert mid["authority"]["status"] == "SUSPENDED" and mid["authority"]["suspended_by"] == work_b
        assert mid["claim"]["status"] == "HELD" and mid["claim"]["owner"] == work_b
        assert not serving_allowed(stack, ALPHA), "serving must be denied while a crashed publication is in flight"
    assert len(mid["receipts"]) == 1, "the crash must not have produced a receipt for the new work"

    time.sleep(1.3)                              # the dead worker's lease expires
    result = stack.worker().run_once()           # a NEW process recovers purely from durable state
    assert result["status"] == "published", (point, result)

    _assert_consistent(stack, ALPHA, entity, attr, "0.19", work_b)
    st = pg_state(stack.sessions, ALPHA)
    assert len(st["receipts"]) == 2, "exactly one new receipt: replay must not duplicate"
    assert sorted(k for w, k, s in st["effects"] if w == work_b) == ["graph", "vector"], "no duplicated effects"
    assert all(s == "verified" for w, k, s in st["effects"] if w == work_b)


def test_crash_during_the_very_first_publication_recovers(live_pg, live_neo4j_driver, tmp_path):
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "f", lease_seconds=1)
    entity, attr = _seed(stack)
    work = stack.submit(ALPHA, "A")
    with pytest.raises(Crash):
        stack.worker(failpoint=crash_at("graph_verified")).run_once()
    mid = pg_state(stack.sessions, ALPHA)
    assert mid["claim"]["status"] == "HELD" and mid["authority"] is None and not serving_allowed(stack, ALPHA)
    time.sleep(1.3)
    assert stack.worker().run_once()["status"] == "published"
    _assert_consistent(stack, ALPHA, entity, attr, "0.21", work)


def test_crash_during_rollback_recovers_to_the_previous_generation(live_pg, live_neo4j_driver, tmp_path):
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "f", lease_seconds=1)
    entity, attr = _seed(stack)
    work_a, _ = _publish(stack, ALPHA, "A")
    work_b, _ = _publish(stack, ALPHA, "B")
    stack.journal.request_rollback(work_b, ALPHA)
    with pytest.raises(Crash):
        stack.worker(failpoint=crash_at("vector_rollback_committed")).run_once()
    assert not serving_allowed(stack, ALPHA)
    time.sleep(1.3)
    assert stack.worker().run_once()["status"] == "rolled_back"
    _assert_consistent(stack, ALPHA, entity, attr, "0.21", work_a)


# ----------------------------------------------------------------------------- failure leaves serving denied


def test_an_unrelated_graph_write_blocks_publication_and_serving_stays_denied(live_pg, live_neo4j_driver, tmp_path):
    support.clean_graph(live_neo4j_driver)
    stack = support.make_stack(live_pg.sessions, live_neo4j_driver, tmp_path / "f", lease_seconds=1)
    entity, attr = _seed(stack)
    work_a, _ = _publish(stack, ALPHA, "A")
    work_b = stack.submit(ALPHA, "B")

    def interfere(name):
        if name == "graph_written":              # after the durable preimage, before the CAS
            seed_graph(stack.driver, ALPHA, entity, attr, "written-by-someone-else")

    first = stack.worker(failpoint=interfere).run_once()
    assert first["status"] == "failed" and "CAS" in first["error"], first
    for _ in range(6):                            # every retry must also refuse, until attempts run out
        if stack.worker().run_once()["status"] == "no_jobs":
            break
    assert pg_state(stack.sessions, ALPHA)["works"][work_b] == "failed"
    assert not serving_allowed(stack, ALPHA), "failed publication must leave serving suspended"
    assert read_graph(stack.driver, ALPHA, entity, attr) == "written-by-someone-else", "never overwrite an unrelated write"
    mid = pg_state(stack.sessions, ALPHA)
    assert mid["authority"]["status"] == "SUSPENDED" and mid["authority"]["suspended_by"] == work_b
    assert mid["claim"]["status"] == "HELD", "an in-flight claim is never auto-released; operator review is required"
    assert len(mid["receipts"]) == 1

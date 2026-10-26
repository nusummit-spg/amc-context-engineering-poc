"""Module providing metrics functionality."""

try:
    from prometheus_client import Counter, Histogram, Gauge, REGISTRY
except ImportError:
    Counter = Histogram = Gauge = None

if Counter is not None:
    # Feedback submission metrics
    feedback_submissions_total = Counter(
        "feedback_submissions_total",
        "Total feedback submissions",
        ["source", "category"]
    )

    # Pipeline execution metrics
    pipeline_duration_seconds = Histogram(
        "pipeline_duration_seconds",
        "Feedback pipeline execution duration",
        ["step", "source"]
    )

    pipeline_errors_total = Counter(
        "pipeline_errors_total",
        "Total pipeline errors",
        ["step", "error_type"]
    )

    # Evaluation metrics
    evaluation_tier_executions = Counter(
        "evaluation_tier_executions",
        "Evaluation tier executions",
        ["tier", "verdict"]
    )

    evaluation_duration_seconds = Histogram(
        "evaluation_duration_seconds",
        "Evaluation duration by tier",
        ["tier"]
    )

    # Repair metrics
    repair_proposals_total = Counter(
        "repair_proposals_total",
        "Total repair proposals",
        ["proposal_type", "status"]
    )

    # Lifecycle metrics
    lifecycle_transitions_total = Counter(
        "lifecycle_transitions_total",
        "Lifecycle state transitions",
        ["from_status", "to_status"]
    )

    # Queue metrics
    pending_feedback_gauge = Gauge(
        "pending_feedback_count",
        "Number of pending feedback records"
    )

    pending_evaluation_gauge = Gauge(
        "pending_evaluation_count",
        "Number of records awaiting evaluation"
    )
else:
    # Graceful mock fallbacks if prometheus_client is absent
    class DummyMetric:
        def labels(self, *args, **kwargs):
            """Labels.

            Returns:
                Result of the operation.
            """
            return self
        def inc(self, *args, **kwargs):
            """Inc.
            """
            pass
        def set(self, *args, **kwargs):
            """Set operation.
            """
            pass
        def observe(self, *args, **kwargs):
            """Observe.
            """
            pass

    feedback_submissions_total = DummyMetric()
    pipeline_duration_seconds = DummyMetric()
    pipeline_errors_total = DummyMetric()
    evaluation_tier_executions = DummyMetric()
    evaluation_duration_seconds = DummyMetric()
    repair_proposals_total = DummyMetric()
    lifecycle_transitions_total = DummyMetric()
    pending_feedback_gauge = DummyMetric()
    pending_evaluation_gauge = DummyMetric()

# Feedback Package Disposition — Decision Record

## Package: feedback_loop (nusummit-spg/human-feedback-loop)

## Finding (W22-05)

`app/services/feedback.py` performed a top-level import at module load time:

    from feedback_loop import FeedbackLoopConfig, start_feedback_loop

This caused `ModuleNotFoundError` at application startup when the package was
absent, blocking ALL test collection and all API routes.

## Decision: EXPLICITLY_DISABLE_EVALUATION

The `feedback_loop` package is treated as an **optional runtime dependency**.

When absent:
- Application starts without error (W22-05 fix)
- GET/read Feedback API endpoints remain available
- POST evaluation endpoints return HTTP 503 with message:
  "Feedback recorded. Evaluation is pending — evaluator unavailable."
- No repair is triggered; no issue is marked resolved
- Setting env var `FEEDBACK_LOOP_REQUIRED=true` promotes absence to a fatal
  startup error (for environments where the evaluator is mandatory)

## Implementation

`app/services/feedback.py` wraps the import in `try/except ImportError` and
sets `_FEEDBACK_LOOP_AVAILABLE = False` when the package is absent.

## TODO for maintainer

Confirm package availability, ownership, and license before re-enabling as a
mandatory dependency in production environments.

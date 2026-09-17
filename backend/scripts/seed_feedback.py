# #app/scripts/seed_feedback.py
# import uuid
# from datetime import datetime, timezone

# from app.core.database import SessionLocal, init_db
# from app.core.models import (
#     FeedbackRecord,
#     FeedbackType,
#     RatingType,
# )
# from app.services.feedback import trigger_feedback_loop


# def create_dummy_feedback():
#     """
#     Create a dummy FeedbackRecord for local development/testing.
#     """

#     db = SessionLocal()

#     try:
#         feedback = FeedbackRecord(
#             response_id="11111111-1111-1111-1111-111111111111",

#             session_id=str(uuid.uuid4()),

#             user_id="33333333-3333-3333-3333-333333333333",

#             rating=RatingType.NEGATIVE.value,

#             feedback_type=FeedbackType.CORRECTION.value,

#             entity_name="Axis Bluechip Fund",

#             entity_type="FUND",

#             notes=(
#                 "The response incorrectly identified the benchmark "
#                 "for Axis Bluechip Fund. The benchmark should be NIFTY 50."
#             ),

#             corrections={
#                 "proposed_entity": "Axis Bluechip Fund",
#                 "proposed_value": "NIFTY 50",
#                 "proposed_relationship": "uses_benchmark",
#             },

#             timestamp=datetime.now(timezone.utc),
#         )

#         db.add(feedback)
#         db.commit()
#         db.refresh(feedback)

#         print("Dummy feedback created successfully.")
#         print(f"feedback_id: {feedback.feedback_id}")
#         print(f"response_id: {feedback.response_id}")
#         print(f"session_id: {feedback.session_id}")

#         # Trigger feedback evaluation
#         evaluation = trigger_feedback_loop(
#             db=db,
#             feedback=feedback,
#         )

#         print("Feedback evaluation completed.")
#         print(f"evaluation_id: {evaluation.id}")
#         print(f"verdict: {evaluation.adjudication_verdict}")
#         print(f"confidence: {evaluation.adjudication_confidence}")
#         print(f"root_cause: {evaluation.root_cause}")
#         print(f"severity: {evaluation.severity}")

#         return feedback

#     except Exception:
#         db.rollback()
#         raise

#     finally:
#         db.close()


# if __name__ == "__main__":
#     init_db()
#     create_dummy_feedback()

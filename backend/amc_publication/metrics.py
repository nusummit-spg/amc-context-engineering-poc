"""Operational observability derived from persistent SQL state (no local lists)."""
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from .models import PublicationWork, PublicationEffect, FeedbackPublicationLink


def durable_metrics(sessions: sessionmaker, tenant: str) -> dict:
    with sessions() as s:
        jobs = s.execute(select(PublicationWork.status, func.count()).where(
            PublicationWork.tenant == tenant).group_by(PublicationWork.status)).all()
        effects = s.execute(select(PublicationEffect.state, func.count()).where(
            PublicationEffect.tenant == tenant).group_by(PublicationEffect.state)).all()
        feedback = s.execute(select(FeedbackPublicationLink.status, func.count()).where(
            FeedbackPublicationLink.tenant == tenant).group_by(FeedbackPublicationLink.status)).all()
        return {"jobs": dict(jobs), "effects": dict(effects), "feedback": dict(feedback)}

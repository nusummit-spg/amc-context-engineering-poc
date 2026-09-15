# ---------------------------------------------------------
# TABLE 7: sessions
# Named ChatSession in Python to avoid clashing with
# sqlalchemy.orm.Session; table name stays "sessions".
# ---------------------------------------------------------

import uuid
from app.core.database import Base
from sqlalchemy import (
    ForeignKey,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone

from app.schemas.models import _now_iso

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    ended_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    audit_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("audit_metadata.audit_id"), nullable=True, index=True
    )
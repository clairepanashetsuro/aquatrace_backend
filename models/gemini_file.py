from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class GeminiFileStatus(str, PyEnum):
    ACTIVE = "active"
    EXPIRED = "expired"


class GeminiFile(Base):
    __tablename__ = "gemini_files"
    __table_args__ = (
        CheckConstraint(
            "expires_at > uploaded_at", name="ck_gemini_files_expires_after_upload"
        ),
        Index(
            "uq_gemini_files_active_document",
            "source_document",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    gemini_file_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_document = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False)
    mime_type = Column(String(100), nullable=False, default="text/markdown")
    gemini_file_name = Column(String(100), unique=True, nullable=False)
    gemini_file_uri = Column(Text, nullable=False)

    status = Column(
        Enum(GeminiFileStatus, name="gemini_file_status"),
        nullable=False,
        default=GeminiFileStatus.ACTIVE,
    )
    uploaded_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)

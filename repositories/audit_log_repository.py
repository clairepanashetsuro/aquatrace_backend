from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, audit_log_id: UUID) -> AuditLog | None:
        return self.db.get(AuditLog, audit_log_id)

    def list_logs(self, limit: int = 50, offset: int = 0) -> list[AuditLog]:
        statement = (
            select(AuditLog)
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_log_id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(statement).all())

    def count_logs(self) -> int:
        statement = select(func.count()).select_from(AuditLog)
        return self.db.scalar(statement) or 0

    def list_by_user(
        self, user_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_log_id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(statement).all())

    def count_by_user(self, user_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.user_id == user_id)
        )
        return self.db.scalar(statement) or 0

    def list_by_action(
        self, action: str, limit: int = 50, offset: int = 0
    ) -> list[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.action == action)
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_log_id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(statement).all())

    def count_by_action(self, action: str) -> int:
        statement = (
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
        return self.db.scalar(statement) or 0

    def list_by_user_and_action(
        self,
        user_id: UUID,
        action: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id, AuditLog.action == action)
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_log_id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(statement).all())

    def count_by_user_and_action(self, user_id: UUID, action: str) -> int:
        statement = (
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.user_id == user_id, AuditLog.action == action)
        )
        return self.db.scalar(statement) or 0

    def add(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.user import User, UserRole, UserStatus


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        normalized_email = email.strip().lower()
        statement = select(User).where(func.lower(User.email) == normalized_email)
        return self.db.scalar(statement)

    def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        statement = (
            select(User)
            .order_by(User.created_at.desc(), User.user_id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(statement).all())

    def list_users_by_status(
        self,
        status: UserStatus,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        statement = (
            select(User)
            .where(User.status == status)
            .order_by(User.created_at.desc(), User.user_id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(statement).all())

    def count_users(self) -> int:
        statement = select(func.count()).select_from(User)
        return self.db.scalar(statement) or 0

    def count_users_by_status(self, status: UserStatus) -> int:
        statement = select(func.count()).select_from(User).where(User.status == status)
        return self.db.scalar(statement) or 0

    def count_active_admins(self) -> int:
        statement = (
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMIN,
                User.status == UserStatus.ACTIVE,
            )
        )
        return self.db.scalar(statement) or 0

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def add_record(self, record: object) -> object:
        self.db.add(record)
        return record

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def refresh(self, user: User) -> User:
        self.db.refresh(user)
        return user

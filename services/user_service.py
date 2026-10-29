from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.exceptions import (
    ApplicationError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from core.security import hash_password
from models.audit_log import AuditLog
from models.user import User, UserRole, UserStatus
from repositories.user_repository import UserRepository
from schemas.user import AdminRegister, UserCreate, UserUpdate


class UserService:
    def __init__(self, db: Session):
        self.users = UserRepository(db)

    def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: UserStatus | None = None,
    ) -> dict:
        if status_filter is None:
            items = self.users.list_users(limit=limit, offset=offset)
            total = self.users.count_users()
        else:
            items = self.users.list_users_by_status(
                status=status_filter,
                limit=limit,
                offset=offset,
            )
            total = self.users.count_users_by_status(status_filter)

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_user(self, user_id: UUID) -> User:
        user = self.users.get_by_id(user_id)

        if user is None:
            raise ResourceNotFoundError("User not found")

        return user

    def create_user(
        self,
        payload: UserCreate,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        if payload.role == UserRole.ADMIN:
            raise PermissionDeniedError(
                "Use the dedicated administrator registration endpoint"
            )

        email = str(payload.email).strip().lower()

        if self.users.get_by_email(email):
            raise ConflictError("A user with this email already exists")

        user = User(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=email,
            password_hash=hash_password(payload.password),
            role=payload.role,
            status=UserStatus.ACTIVE,
        )

        try:
            self.users.add(user)
            self.users.add_record(
                AuditLog(
                    user_id=actor.user_id,
                    action="user.created",
                    entity_type="user",
                    entity_id=user.user_id,
                    ip_address=ip_address,
                    details={"role": user.role.value},
                )
            )
            self.users.commit()
            return self.users.refresh(user)
        except IntegrityError:
            self.users.rollback()
            raise ConflictError("A user with this email already exists") from None
        except Exception:
            self.users.rollback()
            raise

    def register_admin(
        self,
        payload: AdminRegister,
        actor: User | None = None,
        ip_address: str | None = None,
    ) -> User:
        email = str(payload.email).strip().lower()

        if self.users.get_by_email(email):
            raise ConflictError("A user with this email already exists")

        user = User(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=email,
            password_hash=hash_password(payload.password),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )

        try:
            self.users.add(user)
            self.users.add_record(
                AuditLog(
                    user_id=actor.user_id if actor else None,
                    action="admin.registered",
                    entity_type="user",
                    entity_id=user.user_id,
                    ip_address=ip_address,
                    details={
                        "role": UserRole.ADMIN.value,
                        "registration_method": "admin" if actor else "public",
                    },
                )
            )
            self.users.commit()
            return self.users.refresh(user)
        except IntegrityError:
            self.users.rollback()
            raise ConflictError("A user with this email already exists") from None
        except Exception:
            self.users.rollback()
            raise

    def update_user(
        self,
        user_id: UUID,
        payload: UserUpdate,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        user = self.get_user(user_id)
        changes = payload.model_dump(exclude_unset=True)

        if not changes:
            return user

        if "role" in changes and changes["role"] != user.role:
            if actor.role != UserRole.ADMIN:
                raise PermissionDeniedError("Only administrators can change user roles")

            if user.role == UserRole.ADMIN and changes["role"] != UserRole.ADMIN:
                if self.users.count_active_admins() <= 1:
                    raise ConflictError(
                        "The last active administrator cannot be demoted"
                    )

                if user.user_id == actor.user_id:
                    raise ApplicationError(
                        "You cannot change your own administrator role",
                        status_code=400,
                    )

        if "email" in changes:
            email = str(changes["email"]).strip().lower()
            existing = self.users.get_by_email(email)

            if existing and existing.user_id != user.user_id:
                raise ConflictError("A user with this email already exists")

            changes["email"] = email

        tracked_fields = {"first_name", "last_name", "email", "role"}

        previous_values = {
            field: (
                getattr(user, field).value
                if isinstance(getattr(user, field), UserRole)
                else getattr(user, field)
            )
            for field in changes
            if field in tracked_fields
        }

        previous_role = user.role.value

        for field, value in changes.items():
            setattr(user, field, value)

        try:
            self.users.add(user)
            self.users.add_record(
                AuditLog(
                    user_id=actor.user_id,
                    action="user.updated",
                    entity_type="user",
                    entity_id=user.user_id,
                    ip_address=ip_address,
                    details={
                        "changed_fields": sorted(changes.keys()),
                        "previous_values": previous_values,
                        "new_values": {
                            field: (
                                getattr(user, field).value
                                if isinstance(getattr(user, field), UserRole)
                                else getattr(user, field)
                            )
                            for field in changes
                            if field in tracked_fields
                        },
                        "previous_role": previous_role,
                        "new_role": user.role.value,
                    },
                )
            )
            self.users.commit()
            return self.users.refresh(user)
        except IntegrityError:
            self.users.rollback()
            raise ConflictError(
                "The update conflicts with an existing record"
            ) from None
        except Exception:
            self.users.rollback()
            raise

    def deactivate_user(
        self,
        user_id: UUID,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        user = self.get_user(user_id)

        if user.user_id == actor.user_id:
            raise ApplicationError(
                "You cannot deactivate your own account",
                status_code=400,
            )

        if (
            user.role == UserRole.ADMIN
            and user.status == UserStatus.ACTIVE
            and self.users.count_active_admins() <= 1
        ):
            raise ConflictError("The last active administrator cannot be deactivated")

        if user.status == UserStatus.INACTIVE:
            return user

        user.status = UserStatus.INACTIVE
        user.otp_hash = None
        user.otp_expires_at = None
        user.otp_attempts = 0
        user.mfa_challenge_hash = None
        user.mfa_challenge_expires_at = None

        try:
            self.users.add(user)
            self.users.add_record(
                AuditLog(
                    user_id=actor.user_id,
                    action="user.deactivated",
                    entity_type="user",
                    entity_id=user.user_id,
                    ip_address=ip_address,
                    details={"status": UserStatus.INACTIVE.value},
                )
            )
            self.users.commit()
            return self.users.refresh(user)
        except Exception:
            self.users.rollback()
            raise

    def activate_user(
        self,
        user_id: UUID,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        user = self.get_user(user_id)

        if user.status == UserStatus.ACTIVE:
            return user

        user.status = UserStatus.ACTIVE
        user.failed_login_attempts = 0
        user.locked_until = None

        try:
            self.users.add(user)
            self.users.add_record(
                AuditLog(
                    user_id=actor.user_id,
                    action="user.activated",
                    entity_type="user",
                    entity_id=user.user_id,
                    ip_address=ip_address,
                    details={"status": UserStatus.ACTIVE.value},
                )
            )
            self.users.commit()
            return self.users.refresh(user)
        except Exception:
            self.users.rollback()
            raise

    def reset_password(
        self,
        user_id: UUID,
        new_password: str,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        user = self.get_user(user_id)
        user.password_hash = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.otp_hash = None
        user.otp_expires_at = None
        user.otp_attempts = 0
        user.mfa_challenge_hash = None
        user.mfa_challenge_expires_at = None

        try:
            self.users.add(user)
            self.users.add_record(
                AuditLog(
                    user_id=actor.user_id,
                    action="user.password_reset",
                    entity_type="user",
                    entity_id=user.user_id,
                    ip_address=ip_address,
                    details={"reset_by_admin": True},
                )
            )
            self.users.commit()
            return self.users.refresh(user)
        except Exception:
            self.users.rollback()
            raise

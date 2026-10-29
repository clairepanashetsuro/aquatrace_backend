from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_admin
from models.user import User, UserStatus
from schemas.user import (
    AdminRegister,
    PasswordResetRequest,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserSelfUpdate,
    UserUpdate,
)
from services.user_service import UserService

router = APIRouter(prefix="/users", tags=["User Management"])
admin_router = APIRouter(prefix="/admin", tags=["Admin Management"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@admin_router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_admin(
    payload: AdminRegister,
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    return UserService(db).register_admin(
        payload,
        None,
        _client_ip(request),
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: UserSelfUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    return UserService(db).update_user(
        current_user.user_id,
        payload,
        current_user,
        _client_ip(request),
    )


@router.get("", response_model=UserListResponse)
def list_users(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    account_status: UserStatus | None = Query(default=None, alias="status"),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return UserService(db).list_users(
        limit=limit,
        offset=offset,
        status_filter=account_status,
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    return UserService(db).create_user(payload, actor, _client_ip(request))


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    return UserService(db).get_user(user_id)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    return UserService(db).update_user(
        user_id,
        payload,
        actor,
        _client_ip(request),
    )


@router.post("/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
    user_id: UUID,
    request: Request,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    return UserService(db).deactivate_user(
        user_id,
        actor,
        _client_ip(request),
    )


@router.post("/{user_id}/activate", response_model=UserResponse)
def activate_user(
    user_id: UUID,
    request: Request,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    return UserService(db).activate_user(
        user_id,
        actor,
        _client_ip(request),
    )


@router.post(
    "/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def reset_user_password(
    user_id: UUID,
    payload: PasswordResetRequest,
    request: Request,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    UserService(db).reset_password(
        user_id,
        payload.new_password,
        actor,
        _client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

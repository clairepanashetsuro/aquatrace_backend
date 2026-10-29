from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from core.rate_limiter import limiter
from database import get_db
from dependencies import get_current_user, get_current_user_for_mfa_setup
from models.user import User
from schemas.auth import (
    MfaDisableRequest,
    MfaEnabledResponse,
    MfaSetupResponse,
    MfaSetupVerifyRequest,
    MfaVerifyRequest,
    PasswordChangeRequest,
    PasswordResetCodeRequest,
    PasswordResetConfirmRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from services.auth_service import (
    authenticate_and_create_login_result,
    change_password as change_user_password,
    complete_mfa_login,
    disable_mfa as disable_user_mfa,
    refresh_tokens,
    request_password_reset,
    reset_password as reset_user_password,
    start_mfa_setup,
    verify_mfa_setup,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(
    request: Request,
    payload: PasswordResetCodeRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    request_password_reset(str(payload.email), db)

    return {
        "message": (
            "If an eligible account exists for that email, "
            "a password reset code will be sent."
        )
    }


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(
    request: Request,
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    reset_user_password(
        email=str(payload.email),
        otp_code=payload.otp_code,
        new_password=payload.new_password,
        db=db,
    )

    return {"message": "Password reset successfully"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    result = authenticate_and_create_login_result(
        email=form_data.username,
        password=form_data.password,
        db=db,
        ip_address=getattr(request.client, "host", None),
    )

    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        mfa_required=result.mfa_required,
        mfa_token=result.mfa_token,
    )


@router.post("/verify-mfa", response_model=TokenResponse)
@limiter.limit("5/minute")
def verify_mfa(
    request: Request,
    payload: MfaVerifyRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    access_token, refresh_token = complete_mfa_login(
        token=payload.mfa_token,
        code=payload.code,
        db=db,
        ip_address=getattr(request.client, "host", None),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_access_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    access_token, refresh_token = refresh_tokens(
        refresh_token=payload.refresh_token,
        db=db,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    change_user_password(
        current_user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        db=db,
    )

    return {"message": "Password changed successfully"}


@router.post("/mfa/setup", response_model=MfaSetupResponse)
@limiter.limit("5/minute")
def setup_mfa(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MfaSetupResponse:
    secret, uri, setup_token = start_mfa_setup(current_user, db)

    return MfaSetupResponse(
        secret=secret,
        provisioning_uri=uri,
        setup_token=setup_token,
    )


@router.post("/mfa/setup/verify", response_model=MfaEnabledResponse)
@limiter.limit("5/minute")
def verify_mfa_setup_code(
    request: Request,
    payload: MfaSetupVerifyRequest,
    current_user: User = Depends(get_current_user_for_mfa_setup),
    db: Session = Depends(get_db),
) -> MfaEnabledResponse:
    recovery_codes = verify_mfa_setup(
        current_user=current_user,
        code=payload.code,
        db=db,
    )

    return MfaEnabledResponse(
        enabled=True,
        recovery_codes=recovery_codes,
    )


@router.post("/mfa/disable")
@limiter.limit("5/minute")
def disable_mfa(
    request: Request,
    payload: MfaDisableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    disable_user_mfa(
        current_user=current_user,
        password=payload.password,
        code=payload.code,
        db=db,
    )

    return {"message": "MFA disabled successfully"}

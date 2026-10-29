class ApplicationError(Exception):
    def __init__(
        self,
        detail: str,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.headers = headers or {}


class CredentialsError(ApplicationError):
    def __init__(
        self,
        detail: str = "Invalid email or password",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=401,
            headers=headers or {"WWW-Authenticate": "Bearer"},
        )


class PermissionDeniedError(ApplicationError):
    def __init__(self, detail: str = "Permission denied") -> None:
        super().__init__(detail=detail, status_code=403)


class OtpError(ApplicationError):
    def __init__(self, detail: str = "Invalid or expired verification code") -> None:
        super().__init__(detail=detail, status_code=400)


class ConflictError(ApplicationError):
    def __init__(self, detail: str = "Resource conflict") -> None:
        super().__init__(detail=detail, status_code=409)


class ResourceNotFoundError(ApplicationError):
    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(detail=detail, status_code=404)


class CurrentPasswordError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            detail="Current password is incorrect",
            status_code=400,
        )


class ServiceUnavailableError(ApplicationError):
    def __init__(self, detail: str = "Service temporarily unavailable") -> None:
        super().__init__(detail=detail, status_code=503)

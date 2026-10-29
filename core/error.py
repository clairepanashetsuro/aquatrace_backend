from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class. Each subclass fixes its own HTTP status code."""

    status_code = 500
    default_message = "Something went wrong."

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class UnauthenticatedError(AppError):
    status_code = 401
    default_message = "Authentication is required."


class PermissionDeniedError(AppError):
    status_code = 403
    default_message = "You are not allowed to do this."


class NotFoundError(AppError):
    status_code = 404
    default_message = "Not found."


class BusinessRuleError(AppError):
    status_code = 422
    default_message = "The request breaks a business rule."


class ServiceUnavailableError(AppError):
    status_code = 503
    default_message = "Service unavailable."


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)

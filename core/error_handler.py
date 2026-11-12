import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.errors import application_error_response
from core.error import AppError as LegacyAppError
from core.exceptions import ApplicationError


logger = logging.getLogger(__name__)


async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    return application_error_response(exc)


async def unexpected_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error(
        "Unhandled application error on %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred"},
    )


async def legacy_app_error_handler(
    request: Request,
    exc: LegacyAppError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(LegacyAppError, legacy_app_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

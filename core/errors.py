from fastapi.responses import JSONResponse

from core.exceptions import ApplicationError


def application_error_response(error: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail},
        headers=error.headers,
    )

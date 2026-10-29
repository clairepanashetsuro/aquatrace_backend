import ipaddress
import logging
import re
from time import perf_counter
from uuid import uuid4

import anyio

from database import SessionLocal
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class HTTPAuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in AUDITED_METHODS:
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        status_code = 500
        request_id = self._get_request_id(scope)
        client_ip = self._get_client_ip(scope)

        async def send_with_request_id(message):
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}

            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)

            try:
                await anyio.to_thread.run_sync(
                    self._record_event,
                    method,
                    path,
                    status_code,
                    duration_ms,
                    request_id,
                    client_ip,
                )
            except Exception:
                logger.error("Unable to persist HTTP request audit event")

    @staticmethod
    def _get_request_id(scope) -> str:
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-request-id":
                try:
                    supplied_id = value.decode("ascii")
                except UnicodeDecodeError:
                    break

                if REQUEST_ID_PATTERN.fullmatch(supplied_id):
                    return supplied_id

                break

        return str(uuid4())

    @staticmethod
    def _get_client_ip(scope) -> str | None:
        client = scope.get("client")

        if not client or not client[0]:
            return None

        try:
            return str(ipaddress.ip_address(client[0]))
        except ValueError:
            return None

    @staticmethod
    def _record_event(
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        request_id: str,
        client_ip: str | None,
    ) -> None:
        db = None

        try:
            db = SessionLocal()

            AuditService(db).record_event(
                action="HTTP_REQUEST",
                entity_type="HTTP",
                ip_address=client_ip,
                details={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                },
            )

            db.commit()
        except Exception:
            if db is not None:
                db.rollback()

            logger.error("Unable to persist HTTP request audit event")
        finally:
            if db is not None:
                db.close()

from uuid import uuid4
from models.user import UserRole
from datetime import datetime, timezone
from core.security import hash_password
from models.user import User, UserStatus
from pydantic import ValidationError
from schemas.audit_log import AuditLogPage, AuditLogRead
import pytest

from models.audit_log import AuditLog
from services.audit_service import AuditService


def test_record_event_creates_audit_log(db_session):
    service = AuditService(db_session)

    event = service.record_event(
        action="DEVICE_REGISTERED",
        entity_type="device",
        details={"source": "test"},
    )

    assert event.audit_log_id is not None
    assert event.action == "DEVICE_REGISTERED"
    assert event.entity_type == "device"
    assert event.details == {"source": "test"}
    assert event.user_id is None


def test_get_event_returns_recorded_event(db_session):
    service = AuditService(db_session)

    event = service.record_event(action="ALERT_CREATED")
    retrieved = service.get_event(event.audit_log_id)

    assert retrieved is not None
    assert retrieved.audit_log_id == event.audit_log_id
    assert retrieved.action == "ALERT_CREATED"


def test_get_event_returns_none_for_unknown_id(db_session):
    service = AuditService(db_session)

    assert service.get_event(uuid4()) is None


def test_list_events_returns_recorded_events(db_session):
    service = AuditService(db_session)

    service.record_event(action="DEVICE_REGISTERED")
    service.record_event(action="ALERT_CREATED")

    events = service.list_events()

    assert len(events) == 2
    assert {event.action for event in events} == {
        "DEVICE_REGISTERED",
        "ALERT_CREATED",
    }


def test_list_events_by_action_filters_results(db_session):
    service = AuditService(db_session)

    service.record_event(action="ALERT_CREATED")
    service.record_event(action="ALERT_CREATED")
    service.record_event(action="DEVICE_REGISTERED")

    events = service.list_events_by_action("ALERT_CREATED")

    assert len(events) == 2
    assert all(event.action == "ALERT_CREATED" for event in events)


def test_list_events_by_user_returns_matching_results(db_session):
    service = AuditService(db_session)

    events = service.list_events_by_user(uuid4())

    assert events == []


def test_list_events_supports_pagination(db_session):
    service = AuditService(db_session)

    service.record_event(action="EVENT_ONE")
    service.record_event(action="EVENT_TWO")
    service.record_event(action="EVENT_THREE")

    events = service.list_events(limit=2, offset=1)

    assert len(events) == 2


@pytest.mark.parametrize("action", ["", " ", "\t"])
def test_record_event_rejects_empty_action(db_session, action):
    service = AuditService(db_session)

    with pytest.raises(ValueError, match="Audit action cannot be empty"):
        service.record_event(action=action)


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_list_events_rejects_invalid_limit(db_session, limit):
    service = AuditService(db_session)

    with pytest.raises(ValueError, match="Limit must be between 1 and 100"):
        service.list_events(limit=limit)


@pytest.mark.parametrize("offset", [-1, -10])
def test_list_events_rejects_negative_offset(db_session, offset):
    service = AuditService(db_session)

    with pytest.raises(ValueError, match="Offset cannot be negative"):
        service.list_events(offset=offset)


def test_record_event_does_not_commit_transaction(db_session):
    service = AuditService(db_session)

    event = service.record_event(action="TRANSACTION_TEST")
    event_id = event.audit_log_id

    db_session.rollback()

    assert db_session.get(AuditLog, event_id) is None


def test_audit_log_read_from_model():
    event = AuditLog(
        audit_log_id=uuid4(),
        user_id=None,
        action="DEVICE_REGISTERED",
        entity_type="device",
        entity_id=uuid4(),
        ip_address="127.0.0.1",
        details={"source": "test"},
        created_at=datetime.now(timezone.utc),
    )

    result = AuditLogRead.model_validate(event)

    assert result.audit_log_id == event.audit_log_id
    assert result.action == "DEVICE_REGISTERED"
    assert result.details == {"source": "test"}


def test_audit_log_page_accepts_valid_pagination():
    page = AuditLogPage(
        items=[],
        total=0,
        limit=50,
        offset=0,
    )

    assert page.total == 0
    assert page.limit == 50
    assert page.offset == 0


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (50, -1)],
)
def test_audit_log_page_rejects_invalid_pagination(limit, offset):
    with pytest.raises(ValidationError):
        AuditLogPage(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
        )


def _create_audit_access_user(db_session, email, role, password):

    user = User(
        first_name="Audit",
        last_name="Test",
        email=email,
        password_hash=hash_password(password),
        role=role,
        status=UserStatus.ACTIVE,
        mfa_enabled=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _get_audit_access_headers(client, email, password):
    response = client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_can_access_audit_logs(client, db_session):

    password = "AuditAdminPass123!"
    _create_audit_access_user(
        db_session,
        "audit.admin@example.com",
        UserRole.ADMIN,
        password,
    )

    event = AuditService(db_session).record_event(action="AUDIT_ACCESS_TEST")
    db_session.commit()

    headers = _get_audit_access_headers(
        client,
        "audit.admin@example.com",
        password,
    )

    list_response = client.get("/audit-logs", headers=headers)
    detail_response = client.get(
        f"/audit-logs/{event.audit_log_id}",
        headers=headers,
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1
    assert detail_response.status_code == 200
    assert detail_response.json()["audit_log_id"] == str(event.audit_log_id)


def test_non_admin_cannot_access_audit_logs(client, db_session):

    password = "AuditWorkerPass123!"
    _create_audit_access_user(
        db_session,
        "audit.worker@example.com",
        UserRole.FIELD_OFFICER,
        password,
    )

    event = AuditService(db_session).record_event(action="AUDIT_ACCESS_TEST")
    db_session.commit()

    headers = _get_audit_access_headers(
        client,
        "audit.worker@example.com",
        password,
    )

    list_response = client.get("/audit-logs", headers=headers)
    detail_response = client.get(
        f"/audit-logs/{event.audit_log_id}",
        headers=headers,
    )

    assert list_response.status_code == 403
    assert detail_response.status_code == 403


def test_unauthenticated_user_cannot_access_audit_logs(client, db_session):
    event = AuditService(db_session).record_event(action="AUDIT_ACCESS_TEST")
    db_session.commit()

    list_response = client.get("/audit-logs")
    detail_response = client.get(f"/audit-logs/{event.audit_log_id}")

    assert list_response.status_code == 401
    assert detail_response.status_code == 401

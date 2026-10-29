from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.thresholds import LIMITS, NAMES
from models.alert import Alert, AlertStatus, AlertType, SeverityLevel
from models.device import Device, DeviceStatus
from models.user import User, UserRole
from schemas.alert import AlertResolveUpdate
from services import alert_service, threshold_service
from tests.test_user_endpoints import auth_headers, create_user


def test_get_alert_with_bad_id_returns_422(client, db_session):
    create_user(db_session, role=UserRole.WATER_QUALITY_OFFICER)
    headers = auth_headers(client)

    response = client.get("/alerts/not-a-uuid", headers=headers)

    assert response.status_code == 422


def test_list_alerts_limit_is_capped(client, db_session):
    create_user(db_session, role=UserRole.WATER_QUALITY_OFFICER)
    headers = auth_headers(client)

    response = client.get(
        "/alerts",
        params={"limit": 1000},
        headers=headers,
    )

    assert response.status_code == 422


def test_search_text_is_limited(client, db_session):
    create_user(db_session, role=UserRole.WATER_QUALITY_OFFICER)
    headers = auth_headers(client)

    response = client.get(
        "/alerts",
        params={"search": "x" * 101},
        headers=headers,
    )

    assert response.status_code == 422


def test_unknown_status_filter_returns_422(client, db_session):
    create_user(db_session, role=UserRole.WATER_QUALITY_OFFICER)
    headers = auth_headers(client)

    response = client.get(
        "/alerts",
        params={"status": "burning"},
        headers=headers,
    )

    assert response.status_code == 422


def test_resolve_with_bad_id_returns_422(client, db_session):
    create_user(db_session, role=UserRole.WATER_QUALITY_OFFICER)
    headers = auth_headers(client)

    response = client.patch(
        "/alerts/not-a-uuid/resolve",
        headers=headers,
    )

    assert response.status_code == 422


@pytest.fixture
def alert_record(db_session: Session):
    user = User(
        first_name="Test",
        last_name="User",
        email=f"test-{uuid4().hex}@example.com",
        role=UserRole.FIELD_OFFICER,
        status="active",
    )
    db_session.add(user)
    db_session.flush()

    device = Device(
        user_id=user.user_id,
        serial_number=f"TEST-{uuid4().hex[:12]}",
        status=DeviceStatus.ACTIVE,
        latitude=52.0,
        longitude=5.0,
        address="Test location",
    )
    db_session.add(device)
    db_session.flush()

    alert = Alert(
        device_id=device.device_id,
        alert_type=AlertType.THRESHOLD_BREACH,
        parameter="ph",
        observed_value=5.5,
        threshold_value=6.5,
        severity=SeverityLevel.WARNING,
        message="pH below threshold",
        status=AlertStatus.TRIGGERED,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    return alert


def test_unknown_alert_returns_404(db_session: Session):
    with pytest.raises(HTTPException) as error:
        alert_service.get_alert(db_session, uuid4())

    assert error.value.status_code == 404


def test_resolve_moves_triggered_alert_to_resolved(
    db_session: Session,
    alert_record: Alert,
):
    payload = AlertResolveUpdate(status=AlertStatus.RESOLVED)

    result = alert_service.resolve_alert(
        db_session,
        alert_record.alert_id,
        payload,
    )

    assert result.status == AlertStatus.RESOLVED


def test_resolve_twice_returns_409(
    db_session: Session,
    alert_record: Alert,
):
    payload = AlertResolveUpdate(status=AlertStatus.RESOLVED)

    alert_service.resolve_alert(
        db_session,
        alert_record.alert_id,
        payload,
    )

    with pytest.raises(HTTPException) as error:
        alert_service.resolve_alert(
            db_session,
            alert_record.alert_id,
            payload,
        )

    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "limits",
    [
        {"ph": (None, None)},
        {"ph": (8.5, 6.5)},
        {"ph": (6.5, 6.5)},
    ],
)
def test_validate_limits_rejects_invalid_limits(limits):
    with pytest.raises(ValueError):
        threshold_service.validate_limits(limits)


def test_validate_limits_accepts_valid_limits():
    threshold_service.validate_limits(LIMITS)


@pytest.mark.parametrize(
    ("parameter", "value", "expected"),
    [
        ("ph", 6.0, 6.5),
        ("ph", 9.0, 8.5),
        ("ph", 7.0, None),
        ("ph", 6.5, None),
        ("turbidity", 6.0, 5.0),
        ("turbidity", 5.0, None),
    ],
)
def test_crossed_limit(parameter, value, expected):
    assert threshold_service.crossed_limit(LIMITS, parameter, value) == expected


def test_breach_distance_inside_limits():
    assert threshold_service.breach_distance(LIMITS, "ph", 7.0) == 0.0


def test_breach_distance_outside_limits():
    assert threshold_service.breach_distance(LIMITS, "ph", 9.0) == 0.5


def test_breach_message_for_lower_limit():
    assert (
        threshold_service.breach_message(LIMITS, NAMES, "ph", 6.0)
        == "pH is below its limit"
    )


def test_breach_message_for_upper_limit():
    assert (
        threshold_service.breach_message(
            LIMITS,
            NAMES,
            "turbidity",
            6.0,
        )
        == "Turbidity is above its limit"
    )

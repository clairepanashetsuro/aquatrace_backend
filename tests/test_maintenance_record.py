import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from core.error import register_exception_handlers
import routers.maintenance_record as router_module
from database import Base, get_db
from models.device import Device
from models.incident import Incident
from models.maintenance_record import MaintenanceRecord
from models.user import User, UserRole, UserStatus
from types import SimpleNamespace

from core.error import (
    PermissionDeniedError,
    UnauthenticatedError,
)

from services.maintenance_record import MaintenanceRecordService


@compiles(ARRAY, "sqlite")
def _compile_array(type_, compiler, **kw):
    return "JSON"


@compiles(JSONB, "sqlite")
def _compile_jsonb(type_, compiler, **kw):
    return "JSON"


@compiles(INET, "sqlite")
def _compile_inet(type_, compiler, **kw):
    return "TEXT"


PERFORMED_AT = "2026-10-15T10:00:00Z"
URL = "/maintenance-records"

TABLES = [
    User.__table__,
    Device.__table__,
    Incident.__table__,
    MaintenanceRecord.__table__,
]


class Api:
    def __init__(self, client, holder):
        self.client = client
        self._holder = holder

    def login(self, user):
        self._holder["user"] = user
        return self.client


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=TABLES)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def people(db_session):
    def make(first, role):
        user = User(
            first_name=first,
            last_name="Test",
            email=f"{first.lower()}@example.com",
            role=role,
        )
        db_session.add(user)
        db_session.commit()
        return user

    return {
        "fiona": make("Fiona", UserRole.FIELD_OFFICER),
        "felix": make("Felix", UserRole.FIELD_OFFICER),
        "wanda": make("Wanda", UserRole.WATER_QUALITY_OFFICER),
        "adam": make("Adam", UserRole.ADMIN),
    }


@pytest.fixture
def device(db_session, people):
    device = Device(
        user_id=people["fiona"].user_id,
        serial_number="AQ-0001",
        latitude=-1.29,
        longitude=36.82,
    )
    db_session.add(device)
    db_session.commit()
    return device


@pytest.fixture
def api(db_session):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_module.router)
    holder = {"user": None}

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[router_module.get_current_user] = lambda: holder["user"]
    return Api(TestClient(app), holder)


def body(device, **overrides):
    data = {
        "device_id": str(device.device_id),
        "maintenance_type": "calibration",
        "performed_at": PERFORMED_AT,
        "notes": "Calibrated pH probe with buffer 7.0",
        "pre_maintenance_value": 8.4,
        "post_maintenance_value": 7.0,
    }
    data.update(overrides)
    return data


def create(api, user, device, **overrides):
    response = api.login(user).post(URL, json=body(device, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_update_record_success(db_session, people, device):
    from datetime import datetime, timezone

    from schemas.maintenance_record import (
        MaintenanceRecordCreate,
        MaintenanceRecordUpdate,
    )
    from services.maintenance_record import MaintenanceRecordService
    from models.maintenance_record import MaintenanceStatus, MaintenanceType

    fiona = people["fiona"]
    service = MaintenanceRecordService(db_session)

    record = service.create(
        MaintenanceRecordCreate(
            device_id=device.device_id,
            maintenance_type=MaintenanceType.REPAIR,
            performed_at=datetime.now(timezone.utc),
            status=MaintenanceStatus.COMPLETED,
        ),
        fiona,
    )

    updated = service.update(
        record.maintenance_id,
        MaintenanceRecordUpdate(notes="Updated maintenance notes"),
        fiona,
    )

    assert updated.notes == "Updated maintenance notes"


def test_field_officer_can_create_record(api, people, device):
    record = create(api, people["fiona"], device)

    assert record["performed_by"] == str(people["fiona"].user_id)
    assert record["status"] == "completed"
    assert record["maintenance_type"] == "calibration"
    assert record["pre_maintenance_value"] == 8.4
    assert record["post_maintenance_value"] == 7.0


def test_performed_by_comes_from_login_not_request_body(api, people, device):
    record = create(
        api,
        people["fiona"],
        device,
        performed_by=str(people["adam"].user_id),
    )

    assert record["performed_by"] == str(people["fiona"].user_id)


def test_get_current_user_resolves_user(monkeypatch):
    import uuid
    import routers.maintenance_record as router_module

    user_id = uuid.uuid4()
    expected_user = object()

    class FakeService:
        def __init__(self, db):
            pass

        def resolve_active_user(self, supplied_id):
            assert supplied_id == user_id
            return expected_user

    monkeypatch.setattr(router_module, "MaintenanceRecordService", FakeService)

    assert (
        router_module.get_current_user(x_user_id=user_id, db=object()) is expected_user
    )


def test_admin_can_create_record(api, people, device):
    record = create(api, people["adam"], device, maintenance_type="repair")

    assert record["performed_by"] == str(people["adam"].user_id)


def test_water_quality_officer_cannot_create(api, people, device):
    response = api.login(people["wanda"]).post(URL, json=body(device))

    assert response.status_code == 403


def test_create_with_unknown_device_returns_404(api, people, device):
    response = api.login(people["fiona"]).post(
        URL, json=body(device, device_id=str(uuid.uuid4()))
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Device not found."


def test_create_with_unknown_incident_returns_404(api, people, device):
    response = api.login(people["fiona"]).post(
        URL, json=body(device, incident_id=str(uuid.uuid4()))
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found."


def test_update_with_unknown_incident_returns_404(api, people, device):
    record = create(api, people["fiona"], device, maintenance_type="repair")

    response = api.login(people["fiona"]).patch(
        f"{URL}/{record['maintenance_id']}",
        json={"incident_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found."


def test_create_with_invalid_type_returns_422(api, people, device):
    response = api.login(people["fiona"]).post(
        URL, json=body(device, maintenance_type="paint")
    )

    assert response.status_code == 422


def test_create_without_required_fields_returns_422(api, people):
    response = api.login(people["fiona"]).post(URL, json={})

    assert response.status_code == 422


def test_scheduled_record_requires_next_scheduled_date(api, people, device):
    client = api.login(people["fiona"])

    missing = client.post(
        URL,
        json=body(
            device,
            status="scheduled",
            pre_maintenance_value=None,
            post_maintenance_value=None,
        ),
    )
    assert missing.status_code == 422

    valid = client.post(
        URL,
        json=body(
            device,
            status="scheduled",
            next_scheduled_date="2026-11-01T08:00:00Z",
            pre_maintenance_value=None,
            post_maintenance_value=None,
        ),
    )
    assert valid.status_code == 201
    assert valid.json()["status"] == "scheduled"


def test_scheduled_record_cannot_carry_readings(api, people, device):
    response = api.login(people["fiona"]).post(
        URL,
        json=body(
            device,
            status="scheduled",
            next_scheduled_date="2026-11-01T08:00:00Z",
        ),
    )

    assert response.status_code == 422


def test_any_signed_in_role_can_list(api, people, device):
    create(api, people["fiona"], device)

    for who in ("fiona", "wanda", "adam"):
        response = api.login(people[who]).get(URL)
        assert response.status_code == 200
        assert response.json()["total"] == 1


def test_list_filters_by_type_and_device(api, people, device):
    create(api, people["fiona"], device, maintenance_type="cleaning")
    create(api, people["fiona"], device, maintenance_type="repair")
    client = api.login(people["wanda"])

    by_type = client.get(URL, params={"maintenance_type": "repair"}).json()
    assert by_type["total"] == 1
    assert by_type["items"][0]["maintenance_type"] == "repair"

    other_device = client.get(URL, params={"device_id": str(uuid.uuid4())}).json()
    assert other_device["total"] == 0


def test_list_is_paginated_and_newest_first(api, people, device):
    for day in (10, 11, 12):
        create(api, people["fiona"], device, performed_at=f"2026-10-{day}T10:00:00Z")
    client = api.login(people["wanda"])

    page = client.get(URL, params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["items"][0]["performed_at"].startswith("2026-10-12")

    last = client.get(URL, params={"limit": 2, "offset": 2}).json()
    assert len(last["items"]) == 1


def test_list_rejects_bad_paging(api, people):
    client = api.login(people["wanda"])

    assert client.get(URL, params={"limit": 0}).status_code == 422
    assert client.get(URL, params={"limit": 101}).status_code == 422
    assert client.get(URL, params={"offset": -1}).status_code == 422


def test_get_one_record(api, people, device):
    record = create(api, people["fiona"], device)

    response = api.login(people["wanda"]).get(f"{URL}/{record['maintenance_id']}")

    assert response.status_code == 200
    assert response.json()["maintenance_id"] == record["maintenance_id"]


def test_get_unknown_record_returns_404(api, people):
    response = api.login(people["wanda"]).get(f"{URL}/{uuid.uuid4()}")

    assert response.status_code == 404


def test_resolve_active_user_requires_user_id(db_session):
    service = MaintenanceRecordService(db_session)

    with pytest.raises(UnauthenticatedError):
        service.resolve_active_user(None)


def test_resolve_active_user_rejects_unknown_user(db_session, monkeypatch):
    service = MaintenanceRecordService(db_session)
    monkeypatch.setattr(service.repo, "get_user_by_id", lambda user_id: None)

    with pytest.raises(UnauthenticatedError, match="Unknown user"):
        service.resolve_active_user(uuid.uuid4())


def test_resolve_active_user_rejects_inactive_user(db_session, monkeypatch):
    service = MaintenanceRecordService(db_session)
    user = SimpleNamespace(status=UserStatus.INACTIVE)
    monkeypatch.setattr(service.repo, "get_user_by_id", lambda user_id: user)

    with pytest.raises(PermissionDeniedError, match="User is not active"):
        service.resolve_active_user(uuid.uuid4())


def test_resolve_active_user_returns_active_user(db_session, monkeypatch):
    service = MaintenanceRecordService(db_session)
    user = SimpleNamespace(status=UserStatus.ACTIVE)
    monkeypatch.setattr(service.repo, "get_user_by_id", lambda user_id: user)

    result = service.resolve_active_user(uuid.uuid4())

    assert result is user


def test_owner_can_update_own_record(api, people, device):
    record = create(api, people["fiona"], device)

    response = api.login(people["fiona"]).patch(
        f"{URL}/{record['maintenance_id']}",
        json={"notes": "Updated note", "post_maintenance_value": 7.1},
    )

    assert response.status_code == 200
    assert response.json()["notes"] == "Updated note"
    assert response.json()["post_maintenance_value"] == 7.1


def test_other_field_officer_cannot_update(api, people, device):
    record = create(api, people["fiona"], device)

    response = api.login(people["felix"]).patch(
        f"{URL}/{record['maintenance_id']}", json={"notes": "Not mine"}
    )

    assert response.status_code == 403


def test_admin_can_update_any_record(api, people, device):
    record = create(api, people["fiona"], device)

    response = api.login(people["adam"]).patch(
        f"{URL}/{record['maintenance_id']}", json={"status": "failed"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_water_quality_officer_cannot_update(api, people, device):
    record = create(api, people["fiona"], device)

    response = api.login(people["wanda"]).patch(
        f"{URL}/{record['maintenance_id']}", json={"notes": "No"}
    )

    assert response.status_code == 403


def test_device_and_performer_cannot_be_changed(api, people, device):
    record = create(api, people["fiona"], device)
    client = api.login(people["fiona"])
    url = f"{URL}/{record['maintenance_id']}"

    assert client.patch(url, json={"device_id": str(uuid.uuid4())}).status_code == 422
    assert (
        client.patch(
            url, json={"performed_by": str(people["adam"].user_id)}
        ).status_code
        == 422
    )


def test_required_fields_cannot_be_set_to_null(api, people, device):
    record = create(api, people["fiona"], device)
    client = api.login(people["fiona"])
    url = f"{URL}/{record['maintenance_id']}"

    for field in ("status", "maintenance_type", "performed_at"):
        assert client.patch(url, json={field: None}).status_code == 422


def test_update_to_scheduled_needs_a_date_and_no_readings(api, people, device):
    record = create(api, people["fiona"], device)

    response = api.login(people["fiona"]).patch(
        f"{URL}/{record['maintenance_id']}", json={"status": "scheduled"}
    )

    assert response.status_code == 422


def test_update_unknown_record_returns_404(api, people):
    response = api.login(people["adam"]).patch(
        f"{URL}/{uuid.uuid4()}", json={"notes": "x"}
    )

    assert response.status_code == 404


def test_service_source_has_no_fastapi_or_httpexception():
    import pathlib

    here = pathlib.Path(__file__).resolve().parent.parent
    source = (here / "services" / "maintenance_record.py").read_text()
    assert "fastapi" not in source
    assert "HTTPException" not in source


def test_router_source_has_no_direct_db_calls():
    import pathlib

    here = pathlib.Path(__file__).resolve().parent.parent
    source = (here / "routers" / "maintenance_record.py").read_text()
    assert ".get(User" not in source
    assert "select(" not in source
    assert "db.execute" not in source


def test_repository_source_has_no_httpexception():
    import pathlib

    here = pathlib.Path(__file__).resolve().parent.parent
    source = (here / "repositories" / "maintenance_record.py").read_text()
    assert "HTTPException" not in source


def test_repository_get_user_by_id(db_session, people):
    from repositories.maintenance_record import MaintenanceRecordRepository

    repo = MaintenanceRecordRepository(db_session)
    user = people["fiona"]

    assert repo.get_user_by_id(user.user_id) == user


def test_repository_list_optional_filters(db_session, people):
    from datetime import datetime, timezone

    from models.maintenance_record import MaintenanceStatus, MaintenanceType
    from repositories.maintenance_record import MaintenanceRecordRepository

    repo = MaintenanceRecordRepository(db_session)

    records, total = repo.list(
        incident_id=uuid.uuid4(),
        performed_by=people["fiona"].user_id,
        status=MaintenanceStatus.COMPLETED,
        performed_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        performed_to=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert records == []
    assert total == 0

    records, total = repo.list(maintenance_type=MaintenanceType.REPAIR)
    assert records == []
    assert total == 0

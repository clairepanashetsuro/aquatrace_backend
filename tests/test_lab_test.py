import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Boolean as SABoolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.sqltypes import DateTime
import models  # noqa: F401
import routers.lab_test as router_module
from core.error import register_exception_handlers
from database import Base, get_db
from models.incident import Incident
from models.lab_test import LabTest
from models.user import User, UserRole


@compiles(ARRAY, "sqlite")
def _compile_array(type_, compiler, **kw):
    return "JSON"


@compiles(JSONB, "sqlite")
def _compile_jsonb(type_, compiler, **kw):
    return "JSON"


@compiles(INET, "sqlite")
def _compile_inet(type_, compiler, **kw):
    return "TEXT"


URL = "/lab-tests"
SAMPLED = "2026-10-13T08:00:00Z"
TESTED = "2026-10-13T14:15:00Z"

TABLES = [User.__table__, Incident.__table__, LabTest.__table__]


def _value_for(column):

    kind = column.type
    if isinstance(kind, UUID):
        return uuid.uuid4()
    if isinstance(kind, SAEnum):
        enum_cls = kind.enum_class
        if enum_cls is not None:
            return next(iter(enum_cls))
        return kind.enums[0]
    if isinstance(kind, DateTime):
        return datetime.now(timezone.utc)
    if isinstance(kind, SABoolean):
        return False
    if isinstance(kind, (Integer, Float)):
        return 1
    if isinstance(kind, (String, Text)):
        return "x"
    raise TypeError(f"Add a dummy value for {column.name}: {kind!r}")


def make_incident(session):
    values = {}
    for column in Incident.__table__.columns:
        required = (
            not column.nullable
            and not column.primary_key
            and column.default is None
            and column.server_default is None
        )
        if required:
            values[column.name] = _value_for(column)
    incident = Incident(**values)
    session.add(incident)
    session.commit()
    return incident


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
def incident(db_session):
    return make_incident(db_session)


@pytest.fixture
def client(db_session):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_module.router)

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def as_user(user):
    return {"X-User-Id": str(user.user_id)}


def test_require_write_role_returns_authorized_user():
    from types import SimpleNamespace

    from routers.lab_test import require_write_role

    user = SimpleNamespace(role="admin")
    assert require_write_role(user) is user


def body(incident, **overrides):
    data = {
        "incident_id": str(incident.incident_id),
        "laboratory_name": "Kenya Water Labs",
        "parameter": "E. coli",
        "result_value": 12.5,
        "unit": "CFU/100ml",
        "sample_collected_at": SAMPLED,
        "tested_at": TESTED,
        "notes": "Sample no. 4471",
    }
    data.update(overrides)
    return data


def create(client, user, incident, **overrides):
    response = client.post(URL, json=body(incident, **overrides), headers=as_user(user))
    assert response.status_code == 201, response.text
    return response.json()


def test_officer_can_log_a_lab_result(client, people, incident):
    record = create(client, people["fiona"], incident)

    assert record["incident_id"] == str(incident.incident_id)
    assert record["recorded_by"] == str(people["fiona"].user_id)
    assert record["parameter"] == "E. coli"
    assert record["result_value"] == 12.5
    assert record["unit"] == "CFU/100ml"
    assert record["created_at"]


def test_every_role_can_log_a_lab_result(client, people, incident):
    for who in ("fiona", "wanda", "adam"):
        record = create(client, people[who], incident, parameter=f"p-{who}")
        assert record["recorded_by"] == str(people[who].user_id)


def test_ensure_can_write_rejects_non_admin():
    from types import SimpleNamespace

    import pytest
    from core.error import PermissionDeniedError
    from services.lab_test import ensure_can_write

    with pytest.raises(PermissionDeniedError):
        ensure_can_write(SimpleNamespace(role="Field officer"))


def test_recorded_by_comes_from_the_caller_not_the_body(client, people, incident):
    record = create(
        client,
        people["fiona"],
        incident,
        recorded_by=str(people["adam"].user_id),
    )

    assert record["recorded_by"] == str(people["fiona"].user_id)


def test_tested_at_and_notes_are_optional(client, people, incident):
    record = create(client, people["fiona"], incident, tested_at=None, notes=None)

    assert record["tested_at"] is None
    assert record["notes"] is None


def test_create_with_unknown_incident_returns_404(client, people, incident):
    response = client.post(
        URL,
        json=body(incident, incident_id=str(uuid.uuid4())),
        headers=as_user(people["fiona"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found."


def test_tested_before_sample_returns_422(client, people, incident):
    response = client.post(
        URL,
        json=body(
            incident,
            sample_collected_at="2026-10-13T14:15:00Z",
            tested_at="2026-10-13T08:00:00Z",
        ),
        headers=as_user(people["fiona"]),
    )

    assert response.status_code == 422
    assert "tested_at" in response.json()["detail"]


def test_tested_at_equal_to_sample_time_is_allowed(client, people, incident):
    create(client, people["fiona"], incident, tested_at=SAMPLED)


@pytest.mark.parametrize(
    "field", ["laboratory_name", "parameter", "result_value", "unit"]
)
def test_missing_required_field_returns_422(client, people, incident, field):
    data = body(incident)
    del data[field]

    response = client.post(URL, json=data, headers=as_user(people["fiona"]))

    assert response.status_code == 422


def test_missing_sample_time_returns_422(client, people, incident):
    data = body(incident)
    del data["sample_collected_at"]

    response = client.post(URL, json=data, headers=as_user(people["fiona"]))

    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"laboratory_name": "   "},
        {"parameter": ""},
        {"unit": "  "},
        {"laboratory_name": "x" * 101},
        {"parameter": "x" * 51},
        {"unit": "x" * 21},
        {"result_value": "not a number"},
    ],
)
def test_invalid_values_return_422(client, people, incident, overrides):
    response = client.post(
        URL, json=body(incident, **overrides), headers=as_user(people["fiona"])
    )

    assert response.status_code == 422


def test_text_is_trimmed(client, people, incident):
    record = create(
        client, people["fiona"], incident, parameter="  pH  ", unit=" mg/L "
    )

    assert record["parameter"] == "pH"
    assert record["unit"] == "mg/L"


def test_zero_and_negative_results_are_allowed(client, people, incident):
    assert (
        create(client, people["fiona"], incident, result_value=0)["result_value"] == 0
    )
    assert (
        create(client, people["fiona"], incident, result_value=-3.2)["result_value"]
        == -3.2
    )


def test_list_returns_newest_sample_first(client, people, incident):
    for day in (10, 11, 12):
        create(
            client,
            people["fiona"],
            incident,
            sample_collected_at=f"2026-10-{day}T08:00:00Z",
            tested_at=None,
        )

    page = client.get(URL, headers=as_user(people["wanda"])).json()

    assert page["total"] == 3
    assert page["items"][0]["sample_collected_at"].startswith("2026-10-12")


def test_list_filters_by_incident(client, people, incident, db_session):
    other = make_incident(db_session)
    create(client, people["fiona"], incident)
    create(client, people["fiona"], other)

    page = client.get(
        URL,
        params={"incident_id": str(incident.incident_id)},
        headers=as_user(people["wanda"]),
    ).json()

    assert page["total"] == 1
    assert page["items"][0]["incident_id"] == str(incident.incident_id)


def test_list_filters_by_parameter_ignoring_case(client, people, incident):
    create(client, people["fiona"], incident, parameter="E. coli")
    create(client, people["fiona"], incident, parameter="Turbidity")

    page = client.get(
        URL, params={"parameter": "e. COLI"}, headers=as_user(people["wanda"])
    ).json()

    assert page["total"] == 1
    assert page["items"][0]["parameter"] == "E. coli"


def test_list_filters_by_laboratory_name_part(client, people, incident):
    create(client, people["fiona"], incident, laboratory_name="Kenya Water Labs")
    create(client, people["fiona"], incident, laboratory_name="Coast Analytics")

    page = client.get(
        URL, params={"laboratory_name": "water"}, headers=as_user(people["wanda"])
    ).json()

    assert page["total"] == 1


def test_list_filters_by_recorder(client, people, incident):
    create(client, people["fiona"], incident)
    create(client, people["adam"], incident)

    page = client.get(
        URL,
        params={"recorded_by": str(people["adam"].user_id)},
        headers=as_user(people["wanda"]),
    ).json()

    assert page["total"] == 1
    assert page["items"][0]["recorder"]["first_name"] == "Adam"


def test_list_filters_by_sample_date_range(client, people, incident):
    for day in (5, 15, 25):
        create(
            client,
            people["fiona"],
            incident,
            sample_collected_at=f"2026-10-{day:02d}T08:00:00Z",
            tested_at=None,
        )

    page = client.get(
        URL,
        params={
            "sampled_from": "2026-10-10T00:00:00Z",
            "sampled_to": "2026-10-20T00:00:00Z",
        },
        headers=as_user(people["wanda"]),
    ).json()

    assert page["total"] == 1
    assert page["items"][0]["sample_collected_at"].startswith("2026-10-15")


def test_list_is_paginated(client, people, incident):
    for day in (10, 11, 12):
        create(
            client,
            people["fiona"],
            incident,
            sample_collected_at=f"2026-10-{day}T08:00:00Z",
            tested_at=None,
        )
    headers = as_user(people["wanda"])

    first = client.get(URL, params={"limit": 2, "offset": 0}, headers=headers).json()
    last = client.get(URL, params={"limit": 2, "offset": 2}, headers=headers).json()

    assert first["total"] == 3
    assert len(first["items"]) == 2
    assert len(last["items"]) == 1


def test_list_rejects_bad_paging(client, people):
    headers = as_user(people["wanda"])

    assert client.get(URL, params={"limit": 0}, headers=headers).status_code == 422
    assert client.get(URL, params={"limit": 101}, headers=headers).status_code == 422
    assert client.get(URL, params={"offset": -1}, headers=headers).status_code == 422


def test_every_role_can_read(client, people, incident):
    create(client, people["fiona"], incident)

    for who in ("fiona", "wanda", "adam"):
        response = client.get(URL, headers=as_user(people[who]))
        assert response.status_code == 200
        assert response.json()["total"] == 1


def test_get_one_result(client, people, incident):
    record = create(client, people["fiona"], incident)

    response = client.get(
        f"{URL}/{record['lab_test_id']}", headers=as_user(people["wanda"])
    )

    assert response.status_code == 200
    assert response.json()["lab_test_id"] == record["lab_test_id"]


def test_get_unknown_result_returns_404(client, people):
    response = client.get(f"{URL}/{uuid.uuid4()}", headers=as_user(people["wanda"]))

    assert response.status_code == 404


def test_get_with_malformed_id_returns_422(client, people):
    response = client.get(f"{URL}/not-a-uuid", headers=as_user(people["wanda"]))

    assert response.status_code == 422


def test_record_includes_recorder_summary(client, people, incident):
    record = create(client, people["fiona"], incident)

    assert record["recorder"] == {
        "user_id": str(people["fiona"].user_id),
        "first_name": "Fiona",
        "last_name": "Test",
        "role": "Field officer",
    }


def test_recorder_can_update_own_result(client, people, incident):
    record = create(client, people["fiona"], incident)

    response = client.patch(
        f"{URL}/{record['lab_test_id']}",
        json={"result_value": 3.2, "notes": "Re-run"},
        headers=as_user(people["fiona"]),
    )

    assert response.status_code == 200
    assert response.json()["result_value"] == 3.2
    assert response.json()["notes"] == "Re-run"
    assert response.json()["recorder"]["first_name"] == "Fiona"


def test_other_user_cannot_update(
    client, people, incident, db_session
):  # 1. Add db_session here
    record = create(client, people["fiona"], incident)

    db_session.commit()
    db_session.expire_all()

    for who in ("felix", "wanda"):
        response = client.patch(
            f"{URL}/{record['lab_test_id']}",
            json={"notes": "Not mine"},
            headers=as_user(people[who]),
        )
        assert response.status_code == 403


def test_admin_can_update_any_result(client, people, incident):
    record = create(client, people["fiona"], incident)

    response = client.patch(
        f"{URL}/{record['lab_test_id']}",
        json={"unit": "mg/L"},
        headers=as_user(people["adam"]),
    )

    assert response.status_code == 200
    assert response.json()["unit"] == "mg/L"


def test_incident_and_recorder_cannot_be_changed(client, people, incident):
    record = create(client, people["fiona"], incident)
    url = f"{URL}/{record['lab_test_id']}"
    headers = as_user(people["fiona"])

    assert (
        client.patch(
            url, json={"incident_id": str(uuid.uuid4())}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.patch(
            url, json={"recorded_by": str(people["adam"].user_id)}, headers=headers
        ).status_code
        == 422
    )


def test_required_fields_cannot_be_set_to_null(client, people, incident):
    record = create(client, people["fiona"], incident)
    url = f"{URL}/{record['lab_test_id']}"
    headers = as_user(people["fiona"])

    for field in (
        "laboratory_name",
        "parameter",
        "result_value",
        "unit",
        "sample_collected_at",
    ):
        response = client.patch(url, json={field: None}, headers=headers)

        assert response.status_code == 422, (
            f"Failed on field '{field}': Got {response.status_code} with body: {response.text}"
        )


def test_tested_at_can_be_cleared(client, people, incident):
    record = create(client, people["fiona"], incident)

    response = client.patch(
        f"{URL}/{record['lab_test_id']}",
        json={"tested_at": None},
        headers=as_user(people["fiona"]),
    )

    assert response.status_code == 200
    assert response.json()["tested_at"] is None


def test_update_cannot_make_test_earlier_than_sample(client, people, incident):
    record = create(client, people["fiona"], incident)
    url = f"{URL}/{record['lab_test_id']}"
    headers = as_user(people["fiona"])

    earlier_test = client.patch(
        url, json={"tested_at": "2026-10-12T00:00:00Z"}, headers=headers
    )
    later_sample = client.patch(
        url, json={"sample_collected_at": "2026-10-14T00:00:00Z"}, headers=headers
    )

    assert earlier_test.status_code == 422
    assert later_sample.status_code == 422


def test_update_unknown_result_returns_404(client, people):
    response = client.patch(
        f"{URL}/{uuid.uuid4()}", json={"notes": "x"}, headers=as_user(people["adam"])
    )

    assert response.status_code == 404


def test_missing_user_header_returns_401(client):
    assert client.get(URL).status_code == 401


def test_unknown_user_returns_401(client):
    response = client.get(URL, headers={"X-User-Id": str(uuid.uuid4())})

    assert response.status_code == 401


def test_inactive_user_returns_403(client, db_session, people):
    from models.user import UserStatus

    people["fiona"].status = UserStatus.INACTIVE
    db_session.commit()

    response = client.get(URL, headers=as_user(people["fiona"]))

    assert response.status_code == 403


def test_create_without_header_returns_401(client, incident):
    assert client.post(URL, json=body(incident)).status_code == 401

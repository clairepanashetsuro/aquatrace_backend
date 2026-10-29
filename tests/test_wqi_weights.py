from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from database import get_db
from dependencies import get_current_user, require_water_quality_officer
from main import app
from models.user import UserRole, UserStatus
from repositories import wqi_weight_repository


client = TestClient(app)

GOOD = {
    "weights": [
        {"parameter": "ph", "weight": 30},
        {"parameter": "temperature", "weight": 20},
        {"parameter": "turbidity", "weight": 30},
        {"parameter": "electrical_conductivity", "weight": 20},
    ]
}

UPDATED = {
    "weights": [
        {"parameter": "ph", "weight": 25},
        {"parameter": "temperature", "weight": 15},
        {"parameter": "turbidity", "weight": 35},
        {"parameter": "electrical_conductivity", "weight": 25},
    ]
}

PARAMETERS = {
    "ph",
    "temperature",
    "turbidity",
    "electrical_conductivity",
}


def make_rows(weights=None):
    if weights is None:
        weights = {
            "ph": 25.0,
            "temperature": 25.0,
            "turbidity": 25.0,
            "electrical_conductivity": 25.0,
        }

    return [
        SimpleNamespace(
            wqi_weight_id=uuid4(),
            parameter=parameter,
            weight=weight,
        )
        for parameter, weight in weights.items()
    ]


def log_in_as(role):
    user = SimpleNamespace(
        user_id=uuid4(),
        role=role,
        status=UserStatus.ACTIVE,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides.pop(require_water_quality_officer, None)
    return user


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    stored = make_rows()
    created = []
    saved = []

    app.dependency_overrides[get_db] = lambda: None

    def list_weights(db, lock=False):
        return stored if stored else created

    def add_weights(db, rows):
        for row in rows:
            if row.wqi_weight_id is None:
                row.wqi_weight_id = uuid4()
        created.extend(rows)
        return rows

    def save(db):
        saved.append(True)

    monkeypatch.setattr(
        wqi_weight_repository,
        "list_weights",
        list_weights,
    )
    monkeypatch.setattr(
        wqi_weight_repository,
        "add_weights",
        add_weights,
        raising=False,
    )
    monkeypatch.setattr(
        wqi_weight_repository,
        "save",
        save,
    )

    yield SimpleNamespace(
        stored=stored,
        created=created,
        saved=saved,
    )

    app.dependency_overrides.clear()


def test_get_without_token_is_rejected():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_water_quality_officer, None)

    response = client.get("/wqi-weights")

    assert response.status_code in (401, 403)


def test_put_without_token_is_rejected():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_water_quality_officer, None)

    response = client.put("/wqi-weights", json=UPDATED)

    assert response.status_code in (401, 403)


@pytest.mark.parametrize("role", list(UserRole))
def test_every_authenticated_role_can_read(role):
    log_in_as(role)

    response = client.get("/wqi-weights")

    assert response.status_code == 200
    assert len(response.json()) == 4
    assert {item["parameter"] for item in response.json()} == PARAMETERS


@pytest.mark.parametrize(
    "role",
    [
        UserRole.ADMIN,
        UserRole.FIELD_OFFICER,
    ],
)
def test_non_wqo_cannot_create_weights(role, no_database):
    log_in_as(role)

    response = client.post("/wqi-weights", json=GOOD)

    assert response.status_code == 403
    assert no_database.created == []
    assert no_database.saved == []


@pytest.mark.parametrize(
    "role",
    [
        UserRole.ADMIN,
        UserRole.FIELD_OFFICER,
    ],
)
def test_non_wqo_cannot_update_weights(role, no_database):
    log_in_as(role)
    original = {row.parameter: row.weight for row in no_database.stored}

    response = client.put("/wqi-weights", json=UPDATED)

    assert response.status_code == 403
    assert {row.parameter: row.weight for row in no_database.stored} == original
    assert no_database.saved == []


def test_wqo_can_create_initial_weights(no_database):
    log_in_as(UserRole.WATER_QUALITY_OFFICER)
    no_database.stored.clear()

    response = client.post("/wqi-weights", json=GOOD)

    assert response.status_code == 201
    assert len(response.json()) == 4
    assert {item["parameter"] for item in response.json()} == PARAMETERS
    assert sum(item["weight"] for item in response.json()) == pytest.approx(100)
    assert len(no_database.created)

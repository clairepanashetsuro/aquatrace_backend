import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app
from database import get_db
from models.sensor_reading import WqiStatus, SensorStatus
import routers.sensor_reading_router as sensor_router

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_database_dependency():
    app.dependency_overrides[get_db] = lambda: object()
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def sample_reading():
    now = datetime.now(timezone.utc)
    return {
        "reading_id": uuid4(),
        "device_id": uuid4(),
        "message_number": 42,
        "ph": 7.2,
        "temperature": 22.4,
        "turbidity": 1.2,
        "electrical_conductivity": 520.0,
        "wqi_score": 85.0,
        "wqi_status": WqiStatus.EXCELLENT,
        "sensor_status": SensorStatus.OK,
        "is_buffered": False,
        "recorded_at": now,
        "created_at": now,
    }


@pytest.fixture
def valid_payload():
    return {
        "device_id": str(uuid4()),
        "message_number": 1,
        "ph": 7.0,
        "temperature": 22.0,
        "turbidity": 1.0,
        "electrical_conductivity": 500.0,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "sensor_status": "ok",
    }


def test_create_reading_success(monkeypatch, sample_reading, valid_payload):
    def fake_ingest(db, payload):
        return sample_reading

    monkeypatch.setattr(sensor_router, "ingest_sensor_reading", fake_ingest)

    response = client.post("/sensor-readings/", json=valid_payload)

    assert response.status_code == 201
    assert response.json()["reading_id"] == str(sample_reading["reading_id"])
    assert response.json()["message_number"] == 42


def test_create_reading_handles_value_error(monkeypatch, valid_payload):
    def fake_ingest(db, payload):
        raise HTTPException(status_code=422, detail="Invalid sensor data calculation.")

    monkeypatch.setattr(sensor_router, "ingest_sensor_reading", fake_ingest)

    response = client.post("/sensor-readings/", json=valid_payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid sensor data calculation."


@pytest.mark.parametrize(
    "bad_data",
    [
        {"ph": 15.0},
        {"temperature": "hot"},
        {"message_number": 0},
    ],
)
def test_create_reading_rejects_invalid_payloads(bad_data, valid_payload):
    payload = {**valid_payload, **bad_data}

    response = client.post("/sensor-readings/", json=payload)

    assert response.status_code == 422


def test_list_readings_returns_200(monkeypatch, sample_reading):
    monkeypatch.setattr(
        sensor_router,
        "list_sensor_readings",
        lambda db, device_id, limit: [sample_reading],
    )

    response = client.get("/sensor-readings/")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["reading_id"] == str(sample_reading["reading_id"])


def test_list_readings_filters_by_device_id(monkeypatch, sample_reading):
    device_id = uuid4()
    sample_reading["device_id"] = device_id
    called = {}

    def fake_list(db, device_id=None, limit=100):
        called["device_id"] = device_id
        return [sample_reading]

    monkeypatch.setattr(sensor_router, "list_sensor_readings", fake_list)

    response = client.get(f"/sensor-readings/?device_id={device_id}")

    assert response.status_code == 200
    assert called["device_id"] == str(device_id)
    assert response.json()[0]["device_id"] == str(device_id)


@pytest.mark.parametrize("limit", [0, -1, 501, 1000])
def test_list_readings_rejects_invalid_limit(limit):
    response = client.get(f"/sensor-readings/?limit={limit}")

    assert response.status_code == 422


def test_list_readings_returns_empty_list(monkeypatch):
    monkeypatch.setattr(sensor_router, "list_sensor_readings", lambda **kwargs: [])

    response = client.get("/sensor-readings/")

    assert response.status_code == 200
    assert response.json() == []


def test_latest_readings_returns_200(monkeypatch, sample_reading):
    monkeypatch.setattr(
        sensor_router,
        "list_latest_readings_per_device",
        lambda **kwargs: [sample_reading],
    )

    response = client.get("/sensor-readings/latest")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_reading_by_id_returns_200(monkeypatch, sample_reading):
    reading_id = sample_reading["reading_id"]
    monkeypatch.setattr(
        sensor_router, "find_sensor_reading", lambda db, reading_id: sample_reading
    )

    response = client.get(f"/sensor-readings/{reading_id}")

    assert response.status_code == 200
    assert response.json()["reading_id"] == str(reading_id)


def test_get_missing_reading_returns_404(monkeypatch):
    reading_id = uuid4()

    def fake_find(db, reading_id):
        raise HTTPException(status_code=404, detail="Sensor reading not found.")

    monkeypatch.setattr(sensor_router, "find_sensor_reading", fake_find)

    response = client.get(f"/sensor-readings/{reading_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Sensor reading not found."


def test_get_reading_rejects_invalid_uuid():
    response = client.get("/sensor-readings/invalid-uuid-format")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_readings_by_device_returns_200(monkeypatch, sample_reading):
    device_id = uuid4()
    sample_reading["device_id"] = device_id
    monkeypatch.setattr(
        sensor_router,
        "list_readings_by_device",
        lambda db, device_id, limit: [sample_reading],
    )

    response = client.get(f"/sensor-readings/device/{device_id}")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["device_id"] == str(device_id)


def test_wqi_calculation_and_deduplication_logic(monkeypatch, valid_payload):
    from services import sensor_reading_service as service

    monkeypatch.setattr(
        service,
        "fetch_active_weights",
        lambda db: {
            "ph": 0.25,
            "temperature": 0.25,
            "turbidity": 0.25,
            "electrical_conductivity": 0.25,
        },
    )

    monkeypatch.setattr(
        service, "get_reading_by_device_and_message", lambda db, dev, msg: None
    )

    class DummyDB:
        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return True

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    class DummyReading:
        reading_id = uuid4()
        device_id = valid_payload["device_id"]
        message_number = valid_payload["message_number"]
        ph = valid_payload["ph"]
        temperature = valid_payload["temperature"]
        turbidity = valid_payload["turbidity"]
        electrical_conductivity = valid_payload["electrical_conductivity"]
        recorded_at = datetime.fromisoformat(valid_payload["recorded_at"])
        created_at = datetime.now(timezone.utc)
        sensor_status = SensorStatus.OK
        is_buffered = False
        wqi_score = 100.0
        wqi_status = WqiStatus.EXCELLENT

    monkeypatch.setattr(service, "create_reading", lambda db, data: DummyReading())

    from schemas.sensor_reading import SensorReadingCreate
     
    monkeypatch.setattr(service, "create_reading", lambda db, data: DummyReading())
    monkeypatch.setattr(
    service.alert_service,
    "process_new_reading",
    lambda db, reading_id: None,
)
    payload_obj = SensorReadingCreate(**valid_payload)
    result = service.ingest_sensor_reading(DummyDB(), payload_obj)

    assert result.wqi_score == 100.0
    assert result.wqi_status == WqiStatus.EXCELLENT
    assert result.is_buffered is False


def test_buffered_logic_when_recorded_at_is_old(monkeypatch):
    from services import sensor_reading_service as service
    from schemas.sensor_reading import SensorReadingCreate

    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    payload = {
        "device_id": str(uuid4()),
        "message_number": 99,
        "ph": 7.0,
        "temperature": 22.0,
        "turbidity": 1.0,
        "electrical_conductivity": 500.0,
        "recorded_at": old_time.isoformat(),
        "sensor_status": "ok",
    }
    payload_obj = SensorReadingCreate(**payload)

    class DummyDB:
        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return True

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    class DummyReading:
        reading_id = uuid4()
        is_buffered = True
        
        

    def fake_create(db, data):
        assert data["is_buffered"] is True, (
            "Service failed to flag reading as buffered!"
        )
        return DummyReading()

    monkeypatch.setattr(
        service, "get_reading_by_device_and_message", lambda db, dev, msg: None
    )
    
    monkeypatch.setattr(
        service,
        "fetch_active_weights",
        lambda db: {
            "ph": 0.25,
            "temperature": 0.25,
            "turbidity": 0.25,
            "electrical_conductivity": 0.25,
        },
    )


    monkeypatch.setattr(service, "create_reading", fake_create)

    monkeypatch.setattr(
    service.alert_service,
    "process_new_reading",
    lambda db, reading_id: None,
)



    result = service.ingest_sensor_reading(DummyDB(), payload_obj)

    assert result.is_buffered is True

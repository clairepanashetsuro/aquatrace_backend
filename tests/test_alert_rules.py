from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from models.alert import AlertStatus, SeverityLevel
from models.sensor_reading import SensorStatus
from repositories import alert_repository
from services import alert_rules, alert_service

DEVICE = uuid4()


def reading(status=SensorStatus.OK, **values):
    data = {
        "ph": 7.0,
        "temperature": 20.0,
        "turbidity": 2.0,
        "electrical_conductivity": 800.0,
    }
    data.update(values)
    return SimpleNamespace(
        reading_id=uuid4(),
        device_id=DEVICE,
        sensor_status=status,
        recorded_at=datetime.now(timezone.utc),
        **data,
    )


class FakeQuery:
    def __init__(self):
        self.filters = []

    def filter(self, *conditions):
        self.filters.extend(str(condition) for condition in conditions)
        return self

    def order_by(self, *args):
        return self

    def limit(self, number):
        return self

    def all(self):
        return []


class RulesHarness:
    def __init__(self):
        self.readings = []
        self.open_alert = None
        self.created = []
        self.updated = []

    def recent_readings(self, db, device, up_to, limit):
        return self.readings

    def find_open_alert(self, db, device, parameter):
        alert = self.open_alert
        if (
            alert is not None
            and alert.parameter == parameter
            and alert.status != AlertStatus.RESOLVED
        ):
            return alert
        return None

    def create_alert(self, db, data):
        alert = SimpleNamespace(alert_id=uuid4(), **data)
        self.created.append(alert)
        return alert

    def add_occurrence(self, db, alert, observed, limit, severity):
        self.updated.append((observed, severity))

    def evaluate(self, item):
        originals = {
            "recent_readings": alert_repository.recent_readings,
            "find_open_alert": alert_repository.find_open_alert,
            "create_alert": alert_repository.create_alert,
            "add_occurrence": alert_service.add_occurrence,
        }

        try:
            alert_repository.recent_readings = self.recent_readings
            alert_repository.find_open_alert = self.find_open_alert
            alert_repository.create_alert = self.create_alert
            alert_service.add_occurrence = self.add_occurrence

            return alert_rules.evaluate_reading(None, item)
        finally:
            alert_repository.recent_readings = originals["recent_readings"]
            alert_repository.find_open_alert = originals["find_open_alert"]
            alert_repository.create_alert = originals["create_alert"]
            alert_service.add_occurrence = originals["add_occurrence"]


@pytest.fixture
def latest():
    return SimpleNamespace(readings=[])


@pytest.fixture
def fakes():
    return RulesHarness()


def test_normal_readings_breach_nothing(latest):
    latest.readings = [reading() for _ in range(3)]
    original = alert_repository.recent_readings
    try:
        alert_repository.recent_readings = lambda *args, **kwargs: latest.readings
        assert alert_rules.breached_parameters(None, latest.readings[0]) == []
    finally:
        alert_repository.recent_readings = original


def test_two_breaches_are_not_enough(latest):
    latest.readings = [
        reading(turbidity=6.8),
        reading(turbidity=6.8),
    ]
    original = alert_repository.recent_readings
    try:
        alert_repository.recent_readings = lambda *args, **kwargs: latest.readings
        assert alert_rules.breached_parameters(None, latest.readings[0]) == []
    finally:
        alert_repository.recent_readings = original


def test_three_breaches_in_a_row_count(latest):
    latest.readings = [reading(turbidity=6.8) for _ in range(3)]
    original = alert_repository.recent_readings
    try:
        alert_repository.recent_readings = lambda *args, **kwargs: latest.readings
        assert alert_rules.breached_parameters(None, latest.readings[0]) == [
            "turbidity"
        ]
    finally:
        alert_repository.recent_readings = original


def test_one_normal_reading_breaks_the_run(latest):
    latest.readings = [
        reading(turbidity=6.8),
        reading(turbidity=2.0),
        reading(turbidity=6.8),
    ]
    original = alert_repository.recent_readings
    try:
        alert_repository.recent_readings = lambda *args, **kwargs: latest.readings
        assert alert_rules.breached_parameters(None, latest.readings[0]) == []
    finally:
        alert_repository.recent_readings = original


def test_faulty_reading_never_counts(latest):
    faulty = reading(status=SensorStatus.FAULT, turbidity=6.8)

    assert alert_rules.breached_parameters(None, faulty) == []


def test_two_parameters_can_breach_together(latest):
    latest.readings = [reading(turbidity=6.8, ph=9.5) for _ in range(3)]
    original = alert_repository.recent_readings
    try:
        alert_repository.recent_readings = lambda *args, **kwargs: latest.readings
        result = alert_rules.breached_parameters(None, latest.readings[0])
        assert sorted(result) == ["ph", "turbidity"]
    finally:
        alert_repository.recent_readings = original


def test_database_query_only_asks_for_good_readings():
    query = FakeQuery()
    fake_db = SimpleNamespace(query=lambda model: query)

    alert_repository.recent_readings(
        fake_db,
        DEVICE,
        datetime.now(timezone.utc),
        3,
    )

    assert any("sensor_status" in text for text in query.filters)


def test_two_breaches_do_not_raise_an_alert(fakes):
    fakes.readings = [
        reading(turbidity=6.8),
        reading(turbidity=6.8),
    ]

    assert fakes.evaluate(fakes.readings[0]) == []
    assert fakes.created == []


def test_three_breaches_in_a_row_raise_one_warning(fakes):
    fakes.readings = [reading(turbidity=6.8) for _ in range(3)]

    new = fakes.evaluate(fakes.readings[0])

    assert len(new) == 1
    assert new[0].parameter == "turbidity"
    assert new[0].severity == SeverityLevel.WARNING
    assert new[0].threshold_value == 5.0
    assert new[0].message == "Turbidity is above its limit"


def test_faulty_reading_never_raises_an_alert(fakes):
    fakes.readings = [reading(turbidity=6.8) for _ in range(3)]
    faulty = reading(status=SensorStatus.FAULT, turbidity=6.8)

    assert fakes.evaluate(faulty) == []
    assert fakes.created == []


def test_two_parameters_together_are_critical(fakes):
    fakes.readings = [reading(turbidity=6.8, ph=9.5) for _ in range(3)]

    new = fakes.evaluate(fakes.readings[0])

    assert len(new) == 2
    assert all(alert.severity == SeverityLevel.CRITICAL for alert in new)


def test_repeat_breach_updates_the_open_alert(fakes):
    fakes.readings = [reading(turbidity=9.0) for _ in range(3)]
    fakes.open_alert = SimpleNamespace(
        parameter="turbidity",
        observed_value=6.8,
        severity=SeverityLevel.WARNING,
        status=AlertStatus.TRIGGERED,
    )

    assert fakes.evaluate(fakes.readings[0]) == []
    assert fakes.created == []
    assert fakes.updated == [(9.0, SeverityLevel.WARNING)]


def test_repeat_breach_keeps_the_worst_reading(fakes):
    fakes.readings = [reading(turbidity=5.5) for _ in range(3)]
    fakes.open_alert = SimpleNamespace(
        parameter="turbidity",
        observed_value=9.1,
        severity=SeverityLevel.WARNING,
        status=AlertStatus.TRIGGERED,
    )

    fakes.evaluate(fakes.readings[0])

    assert fakes.updated == [(None, SeverityLevel.WARNING)]


def test_open_warning_is_escalated_when_a_second_parameter_breaches(fakes):
    fakes.readings = [reading(turbidity=6.8, ph=9.5) for _ in range(3)]
    fakes.open_alert = SimpleNamespace(
        parameter="turbidity",
        observed_value=6.8,
        severity=SeverityLevel.WARNING,
        status=AlertStatus.TRIGGERED,
    )

    fakes.evaluate(fakes.readings[0])

    assert (None, SeverityLevel.CRITICAL) in fakes.updated

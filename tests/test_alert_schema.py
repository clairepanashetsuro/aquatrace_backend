from pydantic import TypeAdapter

from schemas.alert import AlertResponse


def test_alert_location_name_accepts_none():
    field = AlertResponse.model_fields["location_name"]
    adapter = TypeAdapter(field.annotation)

    assert adapter.validate_python(None) is None


def test_alert_location_name_accepts_string():
    field = AlertResponse.model_fields["location_name"]
    adapter = TypeAdapter(field.annotation)

    assert adapter.validate_python("Nairobi Reservoir") == "Nairobi Reservoir"

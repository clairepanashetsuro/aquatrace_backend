
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.exceptions import ResourceNotFoundError
from services import rag_service


def make_context_objects():
    now = datetime.now(timezone.utc)
    device_id = uuid4()
    reading_id = uuid4()
    alert_id = uuid4()

    device = SimpleNamespace(
        device_id=device_id,
        serial_number="AT-TEST-001",
        address="Test location",
    )

    reading = SimpleNamespace(
        reading_id=reading_id,
        device_id=device_id,
        ph=7.2,
        temperature=22.0,
        turbidity=1.5,
        electrical_conductivity=450.0,
        wqi_score=85.0,
        wqi_status="excellent",
        sensor_status="ok",
        recorded_at=now,
    )

    alert = SimpleNamespace(
        alert_id=alert_id,
        device_id=device_id,
        reading_id=reading_id,
        alert_type="threshold_breach",
        parameter="ph",
        observed_value=7.2,
        threshold_value=6.5,
        severity="warning",
        status="triggered",
        message="Test alert",
        occurrence_count=1,
        created_at=now,
        device=device,
        reading=reading,
    )

    return alert, device, reading


def test_build_alert_context_includes_alert_device_and_reading(monkeypatch):
    alert, _, _ = make_context_objects()
    monkeypatch.setattr(rag_service, "get_alert", lambda db, alert_id: alert)

    context = rag_service.build_alert_context(None, alert.alert_id)

    assert context.alert.alert_id == alert.alert_id
    assert context.alert.severity == "warning"
    assert context.alert.status == "triggered"
    assert context.device.serial_number == "AT-TEST-001"
    assert context.reading is not None
    assert context.reading.ph == 7.2
    assert context.missing_information == []


def test_build_alert_context_records_missing_reading(monkeypatch):
    alert, _, _ = make_context_objects()
    alert.reading_id = None
    alert.reading = None
    monkeypatch.setattr(rag_service, "get_alert", lambda db, alert_id: alert)

    context = rag_service.build_alert_context(None, alert.alert_id)

    assert context.reading is None
    assert any(
        "no linked sensor reading" in item
        for item in context.missing_information
    )


def test_build_alert_context_rejects_reading_from_another_device(monkeypatch):
    alert, _, _ = make_context_objects()
    alert.reading.device_id = uuid4()
    monkeypatch.setattr(rag_service, "get_alert", lambda db, alert_id: alert)

    context = rag_service.build_alert_context(None, alert.alert_id)

    assert context.reading is None
    assert any(
        "does not match this device" in item
        for item in context.missing_information
    )


def test_build_alert_context_excludes_non_finite_measurements(monkeypatch):
    alert, _, _ = make_context_objects()
    alert.reading.ph = float("nan")
    monkeypatch.setattr(rag_service, "get_alert", lambda db, alert_id: alert)

    context = rag_service.build_alert_context(None, alert.alert_id)

    assert context.reading is None
    assert any(
        "non-finite measurement" in item
        for item in context.missing_information
    )


def test_build_alert_context_raises_for_missing_alert(monkeypatch):
    monkeypatch.setattr(rag_service, "get_alert", lambda db, alert_id: None)

    with pytest.raises(ResourceNotFoundError, match="Alert not found"):
        rag_service.build_alert_context(None, uuid4())


def test_parse_explanation_payload_accepts_json():
    payload = (
        '{"what_changed":"pH alert","evidence_used":["No source found"],'
        '"still_to_confirm":[],"ideas_to_check":[],"missing_information":[]}'
    )

    result = rag_service._parse_explanation_payload(payload)

    assert result.what_changed == "pH alert"
    assert result.evidence_used == ["No source found"]


def test_parse_explanation_payload_accepts_fenced_json():
    payload = '''```json
{
  "what_changed": "Turbidity alert",
  "evidence_used": [],
  "still_to_confirm": [],
  "ideas_to_check": [],
  "missing_information": []
}
```'''

    result = rag_service._parse_explanation_payload(payload)

    assert result.what_changed == "Turbidity alert"


def test_extract_source_citations_excludes_unapproved_or_unverified_sources():
    approved = SimpleNamespace(
        type="file_citation",
        file_name="01_limits_and_standards.md",
        custom_metadata={
            "category": "limits_and_standards",
            "review_status": "approved",
            "source_sha256": "abc123",
        },
        start_index=0,
        end_index=20,
    )
    needs_review = SimpleNamespace(
        type="file_citation",
        file_name="04_ec_troubleshooting.md",
        custom_metadata={
            "category": "ec_troubleshooting",
            "review_status": "needs_review",
        },
        start_index=21,
        end_index=40,
    )
    missing_metadata = SimpleNamespace(
        type="file_citation",
        file_name="unknown.md",
        custom_metadata=None,
        start_index=41,
        end_index=50,
    )
    interaction = SimpleNamespace(
        steps=[
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        annotations=[approved, needs_review, missing_metadata]
                    )
                ]
            )
        ]
    )

    citations = rag_service._extract_source_citations(interaction)

    assert len(citations) == 1
    assert citations[0].source_file == "01_limits_and_standards.md"
    assert citations[0].review_status == "approved"


def test_parameter_guidance_query_targets_ec(monkeypatch):
    alert, _, _ = make_context_objects()
    alert.parameter = "ec"
    monkeypatch.setattr(rag_service, "get_alert", lambda db, alert_id: alert)

    context = rag_service.build_alert_context(None, alert.alert_id)

    query = rag_service._parameter_guidance_query(context)

    assert "electrical conductivity" in query
    assert "troubleshooting" in query


def configure_mock_gemini(monkeypatch, interaction=None, error=None):
    from core.config import settings

    monkeypatch.setattr(rag_service, "build_alert_context", lambda db, alert_id: None)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        settings,
        "gemini_file_search_store_name",
        "fileSearchStores/test-store",
    )
    monkeypatch.setattr(settings, "gemini_model", "test-model")

    def create(**kwargs):
        if error:
            raise error
        return interaction

    client = SimpleNamespace(
        interactions=SimpleNamespace(create=create)
    )
    monkeypatch.setattr(rag_service.genai, "Client", lambda **kwargs: client)


def test_generate_alert_explanation_returns_valid_response(monkeypatch):
    from schemas.rag import RAGAlertContext, RAGDeviceContext

    alert, device, reading = make_context_objects()
    monkeypatch.setattr(
        rag_service,
        "build_alert_context",
        lambda db, alert_id: rag_service.RAGContext(
            alert=RAGAlertContext(
                alert_id=alert.alert_id,
                device_id=alert.device_id,
                reading_id=alert.reading_id,
                alert_type=alert.alert_type,
                parameter=alert.parameter,
                observed_value=alert.observed_value,
                threshold_value=alert.threshold_value,
                severity=alert.severity,
                status=alert.status,
                message=alert.message,
                occurrence_count=alert.occurrence_count,
                created_at=alert.created_at,
            ),
            device=RAGDeviceContext(
                device_id=device.device_id,
                serial_number=device.serial_number,
                location_name=device.address,
            ),
            reading=None,
            missing_information=[],
        ),
    )
    from core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_file_search_store_name", "test-store")
    monkeypatch.setattr(settings, "gemini_model", "test-model")

    response = SimpleNamespace(
        status="completed",
        output_text=(
            '{"what_changed":"pH alert","evidence_used":["No relevant source found"],'
            '"still_to_confirm":[],"ideas_to_check":[],"missing_information":[]}'
        ),
        steps=[],
    )
    client = SimpleNamespace(
        interactions=SimpleNamespace(
            create=lambda **kwargs: response
        )
    )
    monkeypatch.setattr(rag_service.genai, "Client", lambda **kwargs: client)

    result = rag_service.generate_alert_explanation(None, alert.alert_id)

    assert result.alert_id == alert.alert_id
    assert result.what_changed == "pH alert"
    assert result.model == "test-model"
    assert result.sources == []
    assert alert.severity == "warning"
    assert alert.status == "triggered"


def test_generate_alert_explanation_rejects_missing_api_key(monkeypatch):
    from core.config import settings
    from core.exceptions import ServiceUnavailableError

    alert, _, _ = make_context_objects()
    monkeypatch.setattr(
        rag_service,
        "build_alert_context",
        lambda db, alert_id: SimpleNamespace(alert=SimpleNamespace(alert_id=alert.alert_id)),
    )
    monkeypatch.setattr(settings, "gemini_api_key", None)

    with pytest.raises(ServiceUnavailableError, match="not configured"):
        rag_service.generate_alert_explanation(None, alert.alert_id)


def test_generate_alert_explanation_handles_gemini_failure(monkeypatch):
    from core.exceptions import ServiceUnavailableError

    alert, _, _ = make_context_objects()
    context = SimpleNamespace(
        alert=SimpleNamespace(
            alert_id=alert.alert_id,
            parameter=alert.parameter,
            alert_type=alert.alert_type,
            message=alert.message,
        ),
        missing_information=[],
        model_dump_json=lambda: "{}",
    )
    monkeypatch.setattr(rag_service, "build_alert_context", lambda db, alert_id: context)
    from core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_file_search_store_name", "test-store")
    monkeypatch.setattr(
        rag_service.genai,
        "Client",
        lambda **kwargs: SimpleNamespace(
            interactions=SimpleNamespace(
                create=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("API error"))
            )
        ),
    )

    with pytest.raises(ServiceUnavailableError, match="temporarily unavailable"):
        rag_service.generate_alert_explanation(None, alert.alert_id)


def test_generate_alert_explanation_rejects_invalid_json(monkeypatch):
    from core.exceptions import ServiceUnavailableError

    alert, _, _ = make_context_objects()
    context = SimpleNamespace(
        alert=SimpleNamespace(
            alert_id=alert.alert_id,
            parameter=alert.parameter,
            alert_type=alert.alert_type,
            message=alert.message,
        ),
        missing_information=[],
        model_dump_json=lambda: "{}",
    )
    monkeypatch.setattr(rag_service, "build_alert_context", lambda db, alert_id: context)
    from core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_file_search_store_name", "test-store")
    monkeypatch.setattr(
        rag_service.genai,
        "Client",
        lambda **kwargs: SimpleNamespace(
            interactions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    status="completed",
                    output_text="not valid JSON",
                    steps=[],
                )
            )
        ),
    )

    with pytest.raises(ServiceUnavailableError, match="invalid explanation"):
        rag_service.generate_alert_explanation(None, alert.alert_id)


def test_generate_alert_explanation_rejects_incomplete_interaction(monkeypatch):
    from core.exceptions import ServiceUnavailableError
    from core.config import settings

    alert, _, _ = make_context_objects()
    context = SimpleNamespace(
        alert=SimpleNamespace(
            alert_id=alert.alert_id,
            parameter=alert.parameter,
            alert_type=alert.alert_type,
            message=alert.message,
        ),
        missing_information=[],
        model_dump_json=lambda: "{}",
    )
    monkeypatch.setattr(rag_service, "build_alert_context", lambda db, alert_id: context)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_file_search_store_name", "test-store")
    monkeypatch.setattr(
        rag_service.genai,
        "Client",
        lambda **kwargs: SimpleNamespace(
            interactions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    status="in_progress",
                    output_text="",
                    steps=[],
                )
            )
        ),
    )

    with pytest.raises(ServiceUnavailableError, match="did not complete"):
        rag_service.generate_alert_explanation(None, alert.alert_id)

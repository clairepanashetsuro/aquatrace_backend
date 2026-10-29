from models.audit_log import AuditLog


def test_get_request_is_not_recorded(client, db_session):
    response = client.get("/health")

    assert response.status_code == 200

    events = db_session.query(AuditLog).filter(AuditLog.action == "HTTP_REQUEST").all()

    assert events == []


def test_post_request_is_recorded_without_sensitive_data(client, db_session):
    request_id = "middleware-test-123"

    response = client.post(
        "/auth/login?token=must-not-be-logged",
        headers={
            "X-Request-ID": request_id,
            "Authorization": "Bearer sensitive-token",
        },
        json={
            "email": "test@example.com",
            "password": "test-password",
        },
    )

    assert response.status_code in {400, 401, 422}

    event = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "HTTP_REQUEST",
            AuditLog.details["request_id"].as_string() == request_id,
        )
        .one()
    )

    assert event.details["method"] == "POST"
    assert event.details["path"] == "/auth/login"
    assert event.details["status_code"] == response.status_code
    assert event.details["duration_ms"] >= 0
    assert event.ip_address is None
    assert "must-not-be-logged" not in str(event.details)
    assert "sensitive-token" not in str(event.details)
    assert "test-password" not in str(event.details)

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.error import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    UnauthenticatedError,
    register_exception_handlers,
)
from models.incident import IncidentPriority as P
from models.incident import IncidentStatus as S
from routers import incident as router_module
from services.incident import IncidentService


def make_user(role, status="Active"):
    return NS(user_id=uuid4(), first_name="A", last_name="B", role=role, status=status)


class FakeRepo:
    def __init__(self):
        self.users, self.alerts, self.incidents = {}, set(), {}

    def add_user(self, user):
        self.users[user.user_id] = user
        return user

    def get_user_by_id(self, user_id):
        return self.users.get(user_id)

    def get_alert(self, alert_id):
        return alert_id if alert_id in self.alerts else None

    def incident_exists_for_alert(self, alert_id):
        return any(i.alert_id == alert_id for i in self.incidents.values())

    def get(self, incident_id):
        return self.incidents.get(incident_id)

    def create(self, data):
        now = datetime.now(timezone.utc)
        fields = {
            "assigned_to": None,
            "resolved_by": None,
            "findings": None,
            "corrective_action": None,
            "visited_at": None,
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "assigned_user": None,
            "resolved_user": None,
        }
        fields.update(data)
        inc = NS(incident_id=uuid4(), **fields)
        self.incidents[inc.incident_id] = inc
        return inc

    def update(self, incident, data):
        for k, v in data.items():
            setattr(incident, k, v)
        return incident

    def list(self, limit, offset, status, priority, assigned_to, alert_id, cf, ct):
        items = [
            i
            for i in self.incidents.values()
            if (not status or i.status == status)
            and (not assigned_to or i.assigned_to == assigned_to)
        ]
        return items[offset : offset + limit], len(items)


@pytest.fixture
def world():
    repo = FakeRepo()
    w = NS(
        repo=repo,
        svc=IncidentService(repo),
        wqo=repo.add_user(make_user("Water quality officer")),
        admin=repo.add_user(make_user("Admin")),
        field=repo.add_user(make_user("Field officer")),
        other_field=repo.add_user(make_user("Field officer")),
        inactive=repo.add_user(make_user("Field officer", "Inactive")),
    )
    w.alert = uuid4()
    repo.alerts.add(w.alert)
    return w


def new_incident(w, assign=True):
    payload = {
        "alert_id": uuid4(),
        "priority": P.HIGH,
        "assigned_to": w.field.user_id if assign else None,
    }
    w.repo.alerts.add(payload["alert_id"])
    return w.svc.create(w.wqo, payload)


def ready_for_review(w):
    inc = new_incident(w)
    w.svc.update(
        w.field,
        inc.incident_id,
        {
            "findings": "Silt",
            "corrective_action": "Flushed",
            "visited_at": datetime.now(timezone.utc) - timedelta(hours=1),
        },
    )
    return w.svc.submit(w.field, inc.incident_id)


def test_create_without_assignee_is_open(world):
    inc = new_incident(world, assign=False)
    assert inc.status == S.OPEN and inc.assigned_to is None


def test_create_with_assignee_starts_investigating(world):
    assert new_incident(world).status == S.INVESTIGATING


def test_create_requires_manager_role(world):
    with pytest.raises(PermissionDeniedError):
        world.svc.create(world.field, {"alert_id": world.alert, "priority": P.LOW})


def test_create_unknown_alert(world):
    with pytest.raises(NotFoundError):
        world.svc.create(world.wqo, {"alert_id": uuid4(), "priority": P.LOW})


def test_create_duplicate_alert(world):
    world.svc.create(world.wqo, {"alert_id": world.alert, "priority": P.LOW})
    with pytest.raises(BusinessRuleError):
        world.svc.create(world.wqo, {"alert_id": world.alert, "priority": P.LOW})


@pytest.mark.parametrize("who", ["wqo", "inactive"])
def test_create_assignee_must_be_active_field_officer(world, who):
    with pytest.raises(BusinessRuleError):
        world.svc.create(
            world.wqo,
            {
                "alert_id": world.alert,
                "priority": P.LOW,
                "assigned_to": getattr(world, who).user_id,
            },
        )


def test_resolve_active_user(world):
    assert world.svc.resolve_active_user(world.wqo.user_id) is world.wqo
    for bad in (None, uuid4(), world.inactive.user_id):
        with pytest.raises(UnauthenticatedError):
            world.svc.resolve_active_user(bad)


def test_assign_moves_open_to_investigating(world):
    inc = new_incident(world, assign=False)
    out = world.svc.assign(world.wqo, inc.incident_id, world.field.user_id)
    assert out.status == S.INVESTIGATING and out.assigned_to == world.field.user_id


def test_assign_forbidden_for_field_officer(world):
    inc = new_incident(world, assign=False)
    with pytest.raises(PermissionDeniedError):
        world.svc.assign(world.field, inc.incident_id, world.field.user_id)


def test_assign_blocked_while_awaiting_verification(world):
    inc = ready_for_review(world)
    with pytest.raises(BusinessRuleError):
        world.svc.assign(world.wqo, inc.incident_id, world.other_field.user_id)


def test_field_notes_only_by_assignee(world):
    inc = new_incident(world)
    with pytest.raises(PermissionDeniedError):
        world.svc.update(world.other_field, inc.incident_id, {"findings": "x"})
    with pytest.raises(PermissionDeniedError):
        world.svc.update(world.wqo, inc.incident_id, {"findings": "x"})
    assert (
        world.svc.update(world.admin, inc.incident_id, {"findings": "x"}).findings
        == "x"
    )


def test_notes_need_investigating_status(world):
    inc = new_incident(world, assign=False)
    with pytest.raises(BusinessRuleError):
        world.svc.update(world.admin, inc.incident_id, {"findings": "x"})


def test_visited_at_not_in_future(world):
    inc = new_incident(world)
    with pytest.raises(BusinessRuleError):
        world.svc.update(
            world.field,
            inc.incident_id,
            {"visited_at": datetime.now(timezone.utc) + timedelta(days=1)},
        )


def test_priority_change_manager_only(world):
    inc = new_incident(world)
    with pytest.raises(PermissionDeniedError):
        world.svc.update(world.field, inc.incident_id, {"priority": P.LOW})
    assert (
        world.svc.update(world.wqo, inc.incident_id, {"priority": P.LOW}).priority
        == P.LOW
    )
    with pytest.raises(BusinessRuleError):
        world.svc.update(world.wqo, inc.incident_id, {"priority": None})


def test_submit_needs_complete_notes(world):
    inc = new_incident(world)
    with pytest.raises(BusinessRuleError) as exc:
        world.svc.submit(world.field, inc.incident_id)
    assert "findings" in str(exc.value)


def test_submit_by_wrong_user(world):
    inc = new_incident(world)
    with pytest.raises(PermissionDeniedError):
        world.svc.submit(world.other_field, inc.incident_id)


def test_submit_wrong_status(world):
    inc = ready_for_review(world)
    with pytest.raises(BusinessRuleError):
        world.svc.submit(world.field, inc.incident_id)


def test_reopen_and_close_flow(world):
    inc = ready_for_review(world)
    assert inc.status == S.AWAITING_VERIFICATION
    assert world.svc.reopen(world.wqo, inc.incident_id).status == S.INVESTIGATING
    world.svc.submit(world.field, inc.incident_id)
    closed = world.svc.close(world.wqo, inc.incident_id)
    assert closed.status == S.CLOSED
    assert closed.resolved_by == world.wqo.user_id and closed.closed_at is not None


def test_close_rules(world):
    inc = new_incident(world)
    with pytest.raises(BusinessRuleError):
        world.svc.close(world.wqo, inc.incident_id)
    inc = ready_for_review(world)
    with pytest.raises(PermissionDeniedError):
        world.svc.close(world.field, inc.incident_id)
    with pytest.raises(PermissionDeniedError):
        world.svc.reopen(world.field, inc.incident_id)


def test_closed_incident_is_read_only(world):
    inc = ready_for_review(world)
    world.svc.close(world.wqo, inc.incident_id)
    with pytest.raises(BusinessRuleError):
        world.svc.update(world.admin, inc.incident_id, {"findings": "late"})
    with pytest.raises(BusinessRuleError):
        world.svc.assign(world.wqo, inc.incident_id, world.field.user_id)


def test_not_found(world):
    with pytest.raises(NotFoundError):
        world.svc.get(world.wqo, uuid4())


def test_field_officer_sees_only_own(world):
    mine = new_incident(world)
    other = world.svc.create(
        world.wqo,
        {
            "alert_id": (world.alert),
            "priority": P.LOW,
            "assigned_to": world.other_field.user_id,
        },
    )
    items, total = world.svc.list(world.field)
    assert [i.incident_id for i in items] == [mine.incident_id] and total == 1
    with pytest.raises(PermissionDeniedError):
        world.svc.get(world.field, other.incident_id)
    assert world.svc.get(world.wqo, other.incident_id) is other


@pytest.mark.parametrize(
    "kw",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"created_from": datetime(2026, 2, 1), "created_to": datetime(2026, 1, 1)},
    ],
)
def test_list_validation(world, kw):
    with pytest.raises(BusinessRuleError):
        world.svc.list(world.wqo, **kw)


@pytest.fixture
def client(world):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.get_service] = lambda: world.svc
    return TestClient(app)


def h(user):
    return {"X-User-Id": str(user.user_id)}


def test_router_requires_header(client):
    assert client.get("/incidents").status_code == 401


def test_router_full_flow(client, world):
    alert = str(uuid4())
    world.repo.alerts.add(UUID(alert))
    r = client.post(
        "/incidents", json={"alert_id": alert, "priority": "high"}, headers=h(world.wqo)
    )
    assert r.status_code == 201 and r.json()["status"] == "open"
    iid = r.json()["incident_id"]
    r = client.patch(
        f"/incidents/{iid}/assign",
        json={"assigned_to": str(world.field.user_id)},
        headers=h(world.wqo),
    )
    assert r.json()["status"] == "investigating"
    assert (
        client.post(f"/incidents/{iid}/submit", headers=h(world.field)).status_code
        == 422
    )
    body = {
        "findings": "Silt",
        "corrective_action": "Flushed",
        "visited_at": "2026-01-01T10:00:00Z",
    }
    assert (
        client.patch(f"/incidents/{iid}", json=body, headers=h(world.field)).status_code
        == 200
    )
    assert (
        client.post(f"/incidents/{iid}/submit", headers=h(world.field)).json()["status"]
        == "awaiting_verification"
    )
    assert (
        client.post(f"/incidents/{iid}/close", headers=h(world.field)).status_code
        == 403
    )
    r = client.post(f"/incidents/{iid}/close", headers=h(world.wqo))
    assert r.json()["status"] == "closed"
    assert (
        client.get("/incidents?status=closed", headers=h(world.wqo)).json()["total"]
        == 1
    )


def test_router_validation_and_404(client, world):
    assert client.get(f"/incidents/{uuid4()}", headers=h(world.wqo)).status_code == 404
    assert client.get("/incidents/not-a-uuid", headers=h(world.wqo)).status_code == 422
    assert client.get("/incidents?limit=500", headers=h(world.wqo)).status_code == 422
    assert (
        client.post(
            "/incidents",
            json={"alert_id": str(uuid4()), "priority": "urgent"},
            headers=h(world.wqo),
        ).status_code
        == 422
    )
    iid = new_incident(world).incident_id
    assert (
        client.patch(
            f"/incidents/{iid}", json={"status": "closed"}, headers=h(world.admin)
        ).status_code
        == 422
    )


def test_note_length_limit(world):
    inc = new_incident(world)
    with pytest.raises(BusinessRuleError):
        world.svc.update(world.field, inc.incident_id, {"findings": "x" * 5001})

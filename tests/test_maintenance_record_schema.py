import uuid
from datetime import datetime, timezone

from schemas.maintenance_record import (
    DeviceSummary,
    MaintenanceRecordPage,
    MaintenanceRecordRead,
)
from models.maintenance_record import MaintenanceType


def test_device_summary_accepts_null_coordinates():
    device = DeviceSummary(
        device_id=uuid.uuid4(),
        serial_number="AT-001",
        latitude=None,
        longitude=None,
    )

    assert device.latitude is None
    assert device.longitude is None


def test_maintenance_record_page_accepts_device_without_coordinates():
    now = datetime.now(timezone.utc)
    device_id = uuid.uuid4()

    record = MaintenanceRecordRead(
        maintenance_id=uuid.uuid4(),
        device_id=device_id,
        performed_by=uuid.uuid4(),
        maintenance_type=next(iter(MaintenanceType)),
        performed_at=now,
        created_at=now,
        updated_at=now,
        device=DeviceSummary(
            device_id=device_id,
            serial_number="AT-001",
            latitude=None,
            longitude=None,
        ),
    )

    result = MaintenanceRecordPage(
        items=[record],
        total=1,
        limit=10,
        offset=0,
    )

    assert len(result.items) == 1
    assert result.items[0].device is not None
    assert result.items[0].device.latitude is None
    assert result.items[0].device.longitude is None

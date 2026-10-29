from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


DeviceStatusValue = Literal["active", "inactive", "revoked"]


class DeviceCreate(BaseModel):
    serial_number: str = Field(min_length=1, max_length=50)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = Field(default=None, max_length=255)
    description: str | None = None

    @model_validator(mode="after")
    def validate_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "Latitude and longitude must both be provided or both be omitted."
            )
        return self


class DeviceGPSUpdate(BaseModel):
    serial_number: str = Field(min_length=1, max_length=50)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DeviceUpdate(BaseModel):
    serial_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    status: DeviceStatusValue | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = Field(default=None, max_length=255)
    description: str | None = None

    @model_validator(mode="after")
    def validate_coordinates(self):
        fields_set = self.model_fields_set

        latitude_provided = "latitude" in fields_set
        longitude_provided = "longitude" in fields_set

        if latitude_provided != longitude_provided:
            raise ValueError("Latitude and longitude must be updated together.")

        if latitude_provided and longitude_provided:
            if (self.latitude is None) != (self.longitude is None):
                raise ValueError(
                    "Latitude and longitude must both be provided or both be null."
                )

            if self.latitude is None:
                raise ValueError("Coordinates cannot be cleared through this update.")

        return self


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: UUID
    user_id: UUID
    serial_number: str
    status: DeviceStatusValue
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    description: str | None = None
    last_seen_at: datetime | None = None
    installed_at: datetime
    revoked_at: datetime | None = None

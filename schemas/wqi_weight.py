from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

Parameter = Literal["ph", "temperature", "turbidity", "electrical_conductivity"]


class WqiWeightItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter: Parameter
    weight: float


class WqiWeightsUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "weights": [
                    {"parameter": "ph", "weight": 25},
                    {"parameter": "temperature", "weight": 15},
                    {"parameter": "turbidity", "weight": 35},
                    {"parameter": "electrical_conductivity", "weight": 25},
                ]
            }
        },
    )

    weights: list[WqiWeightItem]


class WqiWeightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wqi_weight_id: UUID
    parameter: str
    weight: float

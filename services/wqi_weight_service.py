import math
from typing import get_args

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.wqi_weight import WqiWeight
from repositories import wqi_weight_repository as repository
from schemas.wqi_weight import Parameter, WqiWeightsUpdate

PARAMETERS = set(get_args(Parameter))
TOTAL = 100
TOLERANCE = 0.01


def _validate_weights(payload: WqiWeightsUpdate) -> dict[str, float]:
    weights = payload.weights

    if len(weights) != len(PARAMETERS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Exactly four parameter weights must be provided.",
        )

    parameters = [item.parameter for item in weights]

    if len(set(parameters)) != len(parameters):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each parameter can appear only once.",
        )

    new = {item.parameter: item.weight for item in weights}

    if set(new) != PARAMETERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Send all four parameters: " + ", ".join(sorted(PARAMETERS)),
        )

    for parameter, weight in new.items():
        if not math.isfinite(weight) or not 0 < weight <= 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Weight for '{parameter}' must be greater than 0 and at most 100."
                ),
            )

    total = sum(new.values())

    if not math.isclose(total, TOTAL, rel_tol=0.0, abs_tol=TOLERANCE):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Weights must add up to {TOTAL}; they add up to {round(total, 2)}."
            ),
        )

    return new


def _stored_weights(db: Session, lock: bool = False) -> list[WqiWeight]:
    rows = repository.list_weights(db, lock=lock)

    if {row.parameter for row in rows} != PARAMETERS or len(rows) != len(PARAMETERS):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WQI weights are not set up correctly in the database.",
        )

    return rows


def list_weights(db: Session) -> list[WqiWeight]:
    return _stored_weights(db)


def get_weight_map(db: Session) -> dict[str, float]:
    return {row.parameter: row.weight for row in _stored_weights(db)}


def create_weights(
    db: Session,
    payload: WqiWeightsUpdate,
) -> list[WqiWeight]:
    new = _validate_weights(payload)
    existing = repository.list_weights(db)

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="WQI weights are already configured. Use PUT to update them.",
        )

    rows = [
        WqiWeight(parameter=parameter, weight=weight)
        for parameter, weight in new.items()
    ]

    repository.add_weights(db, rows)
    repository.save(db)

    return rows


def update_weights(
    db: Session,
    payload: WqiWeightsUpdate,
) -> list[WqiWeight]:
    new = _validate_weights(payload)
    rows = _stored_weights(db, lock=True)

    for row in rows:
        row.weight = new[row.parameter]

    repository.save(db)

    return rows

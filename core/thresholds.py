from services import threshold_service

LIMITS = {
    "ph": (6.5, 8.5),
    "temperature": (12.0, 25.0),
    "turbidity": (None, 5.0),
    "electrical_conductivity": (None, 1500.0),
}

CONSECUTIVE_READINGS = 3

NAMES = {
    "ph": "pH",
    "temperature": "Temperature",
    "turbidity": "Turbidity",
    "electrical_conductivity": "EC",
}


def validate_limits() -> None:
    threshold_service.validate_limits(LIMITS)


def crossed_limit(parameter: str, value: float) -> float | None:
    return threshold_service.crossed_limit(LIMITS, parameter, value)


def breach_distance(parameter: str, value: float) -> float:
    return threshold_service.breach_distance(LIMITS, parameter, value)


def breach_message(parameter: str, value: float) -> str:
    return threshold_service.breach_message(LIMITS, NAMES, parameter, value)

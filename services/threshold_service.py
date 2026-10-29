def validate_limits(limits: dict) -> None:
    """Raise an error if any configured limit is invalid."""
    for parameter, (lower, upper) in limits.items():
        if lower is None and upper is None:
            raise ValueError(f"{parameter} has no limit at all")
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError(f"{parameter}: lower limit must be below upper limit")


def crossed_limit(limits: dict, parameter: str, value: float) -> float | None:
    """Return the limit crossed, or None if the value is within limits."""
    lower, upper = limits[parameter]
    if lower is not None and value < lower:
        return lower
    if upper is not None and value > upper:
        return upper
    return None


def breach_distance(limits: dict, parameter: str, value: float) -> float:
    """Return how far the value is outside its limits."""
    limit = crossed_limit(limits, parameter, value)
    return 0.0 if limit is None else abs(value - limit)


def breach_message(limits: dict, names: dict, parameter: str, value: float) -> str:
    lower = limits[parameter][0]
    side = "below" if lower is not None and value < lower else "above"
    return f"{names[parameter]} is {side} its limit"

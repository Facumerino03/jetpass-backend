import re


_ICAO_RE = re.compile(r"^[A-Z0-9]{4}$")
_HHMM_RE = re.compile(r"^\d{4}$")


def ensure_valid_icao_code(value: str) -> str:
    normalized = value.upper()
    if not _ICAO_RE.fullmatch(normalized):
        raise ValueError("ICAO code must be 4 alphanumeric characters")
    return normalized


def hhmm_to_minutes(value: str) -> int:
    if not _HHMM_RE.fullmatch(value):
        raise ValueError("HHMM value must contain exactly 4 digits")
    hours = int(value[:2])
    minutes = int(value[2:])
    if minutes > 59:
        raise ValueError("HHMM minutes must be between 00 and 59")
    return hours * 60 + minutes


def ensure_rule_change_point_valid(flight_rules: str, route: str | None, rule_change_point: str | None) -> None:
    if flight_rules not in {"Y", "Z"}:
        return
    if not rule_change_point:
        raise ValueError("rule_change_point is required for Y/Z flight rules")
    if not route or rule_change_point.upper() not in route.upper().split():
        raise ValueError("rule_change_point must appear in route")

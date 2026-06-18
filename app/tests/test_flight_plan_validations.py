import pytest

from app.services.flight_plan_validations import (
    ensure_all_aerodromes_distinct,
    ensure_rule_change_point_valid,
    ensure_valid_icao_code,
    hhmm_to_minutes,
)


def test_ensure_valid_icao_code_normalizes_uppercase():
    assert ensure_valid_icao_code("saez") == "SAEZ"


def test_ensure_valid_icao_code_rejects_invalid_length():
    with pytest.raises(ValueError, match="ICAO code must be 4 alphanumeric characters"):
        ensure_valid_icao_code("SAE")


def test_ensure_all_aerodromes_distinct_rejects_duplicates():
    with pytest.raises(ValueError, match="Aerodrome codes must be distinct"):
        ensure_all_aerodromes_distinct("SABE", "SAEZ", "SADP", "SAEZ")


def test_hhmm_to_minutes_parses_time_duration():
    assert hhmm_to_minutes("0130") == 90


def test_hhmm_to_minutes_rejects_bad_minutes():
    with pytest.raises(ValueError, match="HHMM minutes must be between 00 and 59"):
        hhmm_to_minutes("0160")


def test_rule_change_point_required_for_y_or_z_and_must_appear_in_route():
    ensure_rule_change_point_valid("Y", "DCT GUALE DCT", "GUALE")
    with pytest.raises(ValueError, match="rule_change_point is required"):
        ensure_rule_change_point_valid("Z", "DCT GUALE DCT", None)
    with pytest.raises(ValueError, match="rule_change_point must appear in route"):
        ensure_rule_change_point_valid("Y", "DCT GUALE DCT", "PAL")

from datetime import date
from uuid import uuid4

from app.models.aircraft import WakeTurbulenceCat
from app.models.flight_plan import FlightPlan, FlightPlanStatus, FlightRules, FlightType
from app.pdf.map_flight_plan_to_pdf_data import map_flight_plan_to_pdf_data


def _base_plan(**overrides) -> FlightPlan:
    defaults = {
        "id": uuid4(),
        "pilot_user_id": uuid4(),
        "status": FlightPlanStatus.DRAFT,
        "aircraft_number": 1,
        "flight_rules": FlightRules.V,
        "flight_type": FlightType.G,
        "departure_aerodrome_icao": "SABE",
        "departure_time_utc": "1430",
        "flight_date": date(2026, 5, 18),
        "destination_aerodrome_icao": "SAEZ",
        "alternate1_aerodrome_icao": "SADP",
        "alternate2_aerodrome_icao": "SADF",
        "aircraft_identification_snapshot": "LV-ABC",
        "aircraft_type_designator_snapshot": "C172",
        "wake_turbulence_category_snapshot": WakeTurbulenceCat.L,
        "equipment_com_nav_snapshot": "SDFGR",
        "equipment_surveillance_snapshot": "B1",
        "cruising_speed": "N0120",
        "cruising_level": "A045",
        "route": "DCT GUALE DCT",
        "total_eet": "0100",
        "endurance": "0230",
        "persons_on_board": 2,
        "emergency_radio_uhf_snapshot": True,
        "emergency_radio_vhf_snapshot": False,
        "emergency_radio_elt_snapshot": False,
        "survival_equipment_present_snapshot": True,
        "survival_polar_snapshot": True,
        "survival_desert_snapshot": False,
        "survival_maritime_snapshot": False,
        "survival_jungle_snapshot": False,
        "life_jackets_present_snapshot": True,
        "life_jackets_lights_snapshot": True,
        "life_jackets_fluorescein_snapshot": False,
        "life_jackets_uhf_snapshot": False,
        "life_jackets_vhf_snapshot": False,
        "dinghies_present_snapshot": True,
        "dinghies_number_snapshot": 2,
        "dinghies_capacity_snapshot": 4,
        "dinghies_cover_present_snapshot": False,
        "dinghies_color_snapshot": "YELLOW",
        "color_and_markings_snapshot": "WHITE BLUE",
        "remarks_present": True,
        "remarks": "RMK TEST",
        "pilot_in_command": "Amelia Earhart",
    }
    defaults.update(overrides)
    return FlightPlan(**defaults)


def test_map_flight_plan_to_pdf_data_maps_text_and_radio_strikes():
    data = map_flight_plan_to_pdf_data(_base_plan(), signature_png_bytes=b"png")

    assert data.text_fields["aircraft_identification_snapshot"] == "LV-ABC"
    assert "flight_date" not in data.text_fields
    assert data.text_fields["flight_rules"] == "V"
    assert data.text_fields["flight_type"] == "G"
    assert data.mark_fields["emergency_radio_uhf"] is False
    assert data.mark_fields["emergency_radio_vhf"] is True
    assert data.mark_fields["emergency_radio_elt"] is True
    assert data.signature_png_bytes == b"png"


def test_map_strikes_survival_subitems_when_type_not_carried():
    data = map_flight_plan_to_pdf_data(_base_plan())

    assert data.mark_fields["survival_equipment_present"] is False
    assert data.mark_fields["survival_polar"] is False
    assert data.mark_fields["survival_desert"] is True
    assert data.mark_fields["survival_maritime"] is True


def test_map_strikes_all_survival_when_equipment_not_present():
    data = map_flight_plan_to_pdf_data(
        _base_plan(
            survival_equipment_present_snapshot=False,
            survival_polar_snapshot=True,
        )
    )

    assert data.mark_fields["survival_equipment_present"] is True
    assert data.mark_fields["survival_polar"] is True
    assert data.mark_fields["survival_desert"] is True
    assert data.mark_fields["survival_maritime"] is True
    assert data.mark_fields["survival_jungle"] is True


def test_map_strikes_all_life_jacket_marks_when_not_present():
    data = map_flight_plan_to_pdf_data(
        _base_plan(
            life_jackets_present_snapshot=False,
            life_jackets_lights_snapshot=True,
        )
    )

    assert data.mark_fields["life_jackets_present"] is True
    assert data.mark_fields["life_jackets_lights"] is True
    assert data.mark_fields["life_jackets_fluorescein"] is True
    assert data.mark_fields["life_jackets_uhf"] is True
    assert data.mark_fields["life_jackets_vhf"] is True


def test_map_dinghies_without_cover_strikes_cover_and_omits_color():
    data = map_flight_plan_to_pdf_data(
        _base_plan(
            dinghies_cover_present_snapshot=False,
            dinghies_color_snapshot=None,
        )
    )

    assert data.mark_fields["dinghies_present"] is False
    assert data.mark_fields["dinghies_cover_present"] is True
    assert data.text_fields["dinghies_number"] == "2"
    assert data.text_fields["dinghies_color"] == ""


def test_map_no_dinghies_strikes_d_and_c_and_clears_dinghy_text():
    data = map_flight_plan_to_pdf_data(
        _base_plan(
            dinghies_present_snapshot=False,
            dinghies_number_snapshot=2,
            dinghies_capacity_snapshot=4,
            dinghies_color_snapshot="RED",
        )
    )

    assert data.mark_fields["dinghies_present"] is True
    assert data.mark_fields["dinghies_cover_present"] is True
    assert data.text_fields["dinghies_number"] == ""
    assert data.text_fields["dinghies_capacity"] == ""
    assert data.text_fields["dinghies_color"] == ""


def test_map_remarks_present_false_strikes_n():
    data = map_flight_plan_to_pdf_data(_base_plan(remarks_present=False, remarks=None))

    assert data.mark_fields["remarks_present"] is True
    assert data.text_fields["remarks"] == ""


def test_map_null_text_fields_render_empty():
    data = map_flight_plan_to_pdf_data(
        _base_plan(
            other_information=None,
            route=None,
            equipment_surveillance_snapshot=None,
        )
    )

    assert data.text_fields["other_information"] == ""
    assert data.text_fields["route"] == ""
    assert data.text_fields["equipment_surveillance_snapshot"] == ""

from datetime import date
from uuid import uuid4

from app.models.aircraft import WakeTurbulenceCat
from app.models.flight_plan import FlightPlan, FlightPlanStatus, FlightRules, FlightType
from app.pdf.map_flight_plan_to_pdf_data import map_flight_plan_to_pdf_data


def test_map_flight_plan_to_pdf_data_maps_text_and_marks():
    plan = FlightPlan(
        id=uuid4(),
        pilot_user_id=uuid4(),
        status=FlightPlanStatus.DRAFT,
        aircraft_number=1,
        flight_rules=FlightRules.V,
        flight_type=FlightType.G,
        departure_aerodrome_icao="SABE",
        departure_time_utc="1430",
        flight_date=date(2026, 5, 18),
        destination_aerodrome_icao="SAEZ",
        alternate1_aerodrome_icao="SADP",
        alternate2_aerodrome_icao="SADF",
        aircraft_identification_snapshot="LV-ABC",
        aircraft_type_designator_snapshot="C172",
        wake_turbulence_category_snapshot=WakeTurbulenceCat.L,
        equipment_com_nav_snapshot="SDFGR",
        equipment_surveillance_snapshot="B1",
        cruising_speed="N0120",
        cruising_level="A045",
        route="DCT GUALE DCT",
        total_eet="0100",
        endurance="0230",
        persons_on_board=2,
        emergency_radio_uhf_snapshot=True,
        emergency_radio_vhf_snapshot=False,
        pilot_in_command="Amelia Earhart",
    )

    data = map_flight_plan_to_pdf_data(plan, signature_png_bytes=b"png")

    assert data.text_fields["aircraft_identification_snapshot"] == "LV-ABC"
    assert data.text_fields["flight_date"] == "18MAY26"
    assert data.text_fields["flight_rules"] == "V"
    assert data.text_fields["flight_type"] == "G"
    assert data.mark_fields["emergency_radio_uhf"] is False
    assert data.mark_fields["emergency_radio_vhf"] is False
    assert data.signature_png_bytes == b"png"

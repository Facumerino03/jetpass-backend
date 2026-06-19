from __future__ import annotations

from app.models.flight_plan import FlightPlan
from app.pdf.eana_flight_plan_data import EanaFlightPlanPdfData


def _text(value: str | None) -> str:
    return value or ""


def _text_int(value: int | None) -> str:
    return str(value) if value is not None else ""


def _strike(value: bool) -> bool:
    """PDF block mark: True = tachar letra impresa (DB False = no tiene)."""
    return not value


def _build_text_fields(plan: FlightPlan) -> dict[str, str]:
    dinghies_present = plan.dinghies_present_snapshot

    return {
        "aircraft_identification_snapshot": _text(plan.aircraft_identification_snapshot),
        "aircraft_number": str(plan.aircraft_number),
        "aircraft_type_designator_snapshot": _text(plan.aircraft_type_designator_snapshot),
        "wake_turbulence_category_snapshot": (
            plan.wake_turbulence_category_snapshot.value
            if plan.wake_turbulence_category_snapshot is not None
            else ""
        ),
        "equipment_com_nav_snapshot": _text(plan.equipment_com_nav_snapshot),
        "equipment_surveillance_snapshot": _text(plan.equipment_surveillance_snapshot),
        "departure_aerodrome_icao": _text(plan.departure_aerodrome_icao),
        "departure_time_utc": _text(plan.departure_time_utc),
        "cruising_speed": _text(plan.cruising_speed),
        "cruising_level": _text(plan.cruising_level),
        "route": _text(plan.route),
        "total_eet": _text(plan.total_eet),
        "destination_aerodrome_icao": _text(plan.destination_aerodrome_icao),
        "alternate1_aerodrome_icao": _text(plan.alternate1_aerodrome_icao),
        "alternate2_aerodrome_icao": _text(plan.alternate2_aerodrome_icao),
        "other_information": _text(plan.other_information),
        "remarks": _text(plan.remarks),
        "endurance": _text(plan.endurance),
        "persons_on_board": _text_int(plan.persons_on_board),
        "dinghies_number": _text_int(plan.dinghies_number_snapshot) if dinghies_present else "",
        "dinghies_capacity": _text_int(plan.dinghies_capacity_snapshot) if dinghies_present else "",
        "dinghies_color": _text(plan.dinghies_color_snapshot) if dinghies_present else "",
        "color_and_markings_snapshot": _text(plan.color_and_markings_snapshot),
        "pilot_in_command": _text(plan.pilot_in_command),
        "flight_rules": plan.flight_rules.value if plan.flight_rules is not None else "",
        "flight_type": plan.flight_type.value if plan.flight_type is not None else "",
    }


def _build_mark_fields(plan: FlightPlan) -> dict[str, bool]:
    marks: dict[str, bool] = {
        "emergency_radio_uhf": _strike(plan.emergency_radio_uhf_snapshot),
        "emergency_radio_vhf": _strike(plan.emergency_radio_vhf_snapshot),
        "emergency_radio_elt": _strike(plan.emergency_radio_elt_snapshot),
    }

    has_survival = plan.survival_equipment_present_snapshot
    marks["survival_equipment_present"] = _strike(has_survival)
    if has_survival:
        marks["survival_polar"] = _strike(plan.survival_polar_snapshot)
        marks["survival_desert"] = _strike(plan.survival_desert_snapshot)
        marks["survival_maritime"] = _strike(plan.survival_maritime_snapshot)
        marks["survival_jungle"] = _strike(plan.survival_jungle_snapshot)
    else:
        marks["survival_polar"] = True
        marks["survival_desert"] = True
        marks["survival_maritime"] = True
        marks["survival_jungle"] = True

    has_jackets = plan.life_jackets_present_snapshot
    marks["life_jackets_present"] = _strike(has_jackets)
    if has_jackets:
        marks["life_jackets_lights"] = _strike(plan.life_jackets_lights_snapshot)
        marks["life_jackets_fluorescein"] = _strike(plan.life_jackets_fluorescein_snapshot)
        marks["life_jackets_uhf"] = _strike(plan.life_jackets_uhf_snapshot)
        marks["life_jackets_vhf"] = _strike(plan.life_jackets_vhf_snapshot)
    else:
        marks["life_jackets_lights"] = True
        marks["life_jackets_fluorescein"] = True
        marks["life_jackets_uhf"] = True
        marks["life_jackets_vhf"] = True

    has_dinghies = plan.dinghies_present_snapshot
    marks["dinghies_present"] = _strike(has_dinghies)
    if has_dinghies:
        marks["dinghies_cover_present"] = _strike(plan.dinghies_cover_present_snapshot)
    else:
        marks["dinghies_cover_present"] = True

    marks["remarks_present"] = _strike(plan.remarks_present)

    return marks


def map_flight_plan_to_pdf_data(
    plan: FlightPlan,
    *,
    signature_png_bytes: bytes | None = None,
) -> EanaFlightPlanPdfData:
    return EanaFlightPlanPdfData(
        text_fields=_build_text_fields(plan),
        mark_fields=_build_mark_fields(plan),
        signature_png_bytes=signature_png_bytes,
    )

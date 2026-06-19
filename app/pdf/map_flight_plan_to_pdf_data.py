from __future__ import annotations

from datetime import date

from app.models.flight_plan import FlightPlan
from app.pdf.eana_flight_plan_data import EanaFlightPlanPdfData


def _format_flight_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d%b%y").upper()


def _mark(value: bool | None) -> bool:
    return value is True


def _strike(value: bool | None) -> bool:
    """Casilla 19: tachar cuando el equipo NO está presente."""
    return value is not True


def map_flight_plan_to_pdf_data(
    plan: FlightPlan,
    *,
    signature_png_bytes: bytes | None = None,
) -> EanaFlightPlanPdfData:
    text_fields: dict[str, str] = {
        "aircraft_identification_snapshot": plan.aircraft_identification_snapshot or "",
        "aircraft_number": str(plan.aircraft_number),
        "aircraft_type_designator_snapshot": plan.aircraft_type_designator_snapshot or "",
        "wake_turbulence_category_snapshot": (
            plan.wake_turbulence_category_snapshot.value
            if plan.wake_turbulence_category_snapshot is not None
            else ""
        ),
        "equipment_com_nav_snapshot": plan.equipment_com_nav_snapshot or "",
        "equipment_surveillance_snapshot": plan.equipment_surveillance_snapshot or "",
        "departure_aerodrome_icao": plan.departure_aerodrome_icao or "",
        "departure_time_utc": plan.departure_time_utc or "",
        "cruising_speed": plan.cruising_speed or "",
        "cruising_level": plan.cruising_level or "",
        "route": plan.route or "",
        "total_eet": plan.total_eet or "",
        "destination_aerodrome_icao": plan.destination_aerodrome_icao or "",
        "alternate1_aerodrome_icao": plan.alternate1_aerodrome_icao or "",
        "alternate2_aerodrome_icao": plan.alternate2_aerodrome_icao or "",
        "other_information": plan.other_information or "",
        "remarks": plan.remarks or "",
        "endurance": plan.endurance or "",
        "persons_on_board": str(plan.persons_on_board) if plan.persons_on_board is not None else "",
        "dinghies_number": str(plan.dinghies_number_snapshot) if plan.dinghies_number_snapshot is not None else "",
        "dinghies_capacity": str(plan.dinghies_capacity_snapshot) if plan.dinghies_capacity_snapshot is not None else "",
        "dinghies_color": plan.dinghies_color_snapshot or "",
        "color_and_markings_snapshot": plan.color_and_markings_snapshot or "",
        "pilot_in_command": plan.pilot_in_command or "",
        "flight_date": _format_flight_date(plan.flight_date),
        "flight_rules": plan.flight_rules.value if plan.flight_rules is not None else "",
        "flight_type": plan.flight_type.value if plan.flight_type is not None else "",
    }

    mark_fields: dict[str, bool] = {
        "remarks_present": _mark(plan.remarks_present),
        "emergency_radio_uhf": _strike(plan.emergency_radio_uhf_snapshot),
        "emergency_radio_vhf": _mark(plan.emergency_radio_vhf_snapshot),
        "emergency_radio_elt": _mark(plan.emergency_radio_elt_snapshot),
        "survival_polar": _mark(plan.survival_polar_snapshot),
        "survival_desert": _mark(plan.survival_desert_snapshot),
        "survival_maritime": _mark(plan.survival_maritime_snapshot),
        "survival_jungle": _mark(plan.survival_jungle_snapshot),
        "life_jackets_lights": _mark(plan.life_jackets_lights_snapshot),
        "life_jackets_fluorescein": _mark(plan.life_jackets_fluorescein_snapshot),
        "life_jackets_uhf": _mark(plan.life_jackets_uhf_snapshot),
        "life_jackets_vhf": _mark(plan.life_jackets_vhf_snapshot),
        "dinghies_present": _mark(plan.dinghies_present_snapshot),
        "dinghies_cover_present": _mark(plan.dinghies_cover_present_snapshot),
    }

    return EanaFlightPlanPdfData(
        text_fields=text_fields,
        mark_fields=mark_fields,
        signature_png_bytes=signature_png_bytes,
    )

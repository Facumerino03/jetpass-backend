from app.pdf.eana_flight_plan_data import EanaFlightPlanPdfData


def test_text_fields_are_normalized_to_uppercase():
    data = EanaFlightPlanPdfData(
        text_fields={
            "pilot_in_command": "amelia earhart",
            "route": "dct guale dct",
            "dinghies_color": "red",
        }
    )

    assert data.text_fields["pilot_in_command"] == "AMELIA EARHART"
    assert data.text_fields["route"] == "DCT GUALE DCT"
    assert data.text_fields["dinghies_color"] == "RED"

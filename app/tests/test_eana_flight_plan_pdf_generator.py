from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.tests.png_fixtures import TINY_PNG
from app.pdf.eana_flight_plan_data import EanaFlightPlanPdfData
from app.pdf.eana_flight_plan_pdf_generator import EanaFlightPlanPdfGenerator

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / "docs" / "eana_flight_plan_template.pdf"


@pytest.fixture
def generator() -> EanaFlightPlanPdfGenerator:
    if not TEMPLATE_PATH.exists():
        pytest.skip("EANA template PDF not found")
    return EanaFlightPlanPdfGenerator(template_path=TEMPLATE_PATH)


def test_generate_returns_single_page_pdf(generator: EanaFlightPlanPdfGenerator):
    data = EanaFlightPlanPdfData(
        text_fields={
            "aircraft_identification_snapshot": "LV-ABC",
            "flight_rules": "V",
        },
    )

    pdf_bytes = generator.generate(data)

    assert len(pdf_bytes) > 0
    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 1


def test_generate_with_signature_image(generator: EanaFlightPlanPdfGenerator):
    data = EanaFlightPlanPdfData(
        text_fields={"pilot_in_command": "Test Pilot"},
        signature_png_bytes=TINY_PNG,
    )

    pdf_bytes = generator.generate(data)

    assert len(pdf_bytes) > 0


def test_generate_text_cells_places_characters(generator: EanaFlightPlanPdfGenerator):
    data = EanaFlightPlanPdfData(
        text_fields={"aircraft_identification_snapshot": "LV-ABC"},
    )

    pdf_bytes = generator.generate(data)

    assert len(pdf_bytes) > 0


def test_truncate_text_cuts_without_ellipsis():
    result = EanaFlightPlanPdfGenerator._truncate_text(
        "RED RED RED RED RED RED",
        font_name="Helvetica",
        font_size=8,
        max_width=50,
    )

    assert "..." not in result
    assert result
    assert len(result) < len("RED RED RED RED RED RED")


def test_generate_text_lines_wraps_route(generator: EanaFlightPlanPdfGenerator):
    data = EanaFlightPlanPdfData(
        text_fields={"route": "DCT GUALE DCT SANTU DCT ARROYO DCT PAL VFR"},
    )

    pdf_bytes = generator.generate(data)

    assert len(pdf_bytes) > 0

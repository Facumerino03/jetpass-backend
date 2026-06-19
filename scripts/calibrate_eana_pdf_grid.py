#!/usr/bin/env python3
"""Overlay a coordinate grid on the EANA template PDF for field calibration."""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pdf.eana_flight_plan_pdf_generator import EanaFlightPlanPdfGenerator  # noqa: E402


def build_grid_overlay(*, width: float, height: float, step: float = 10) -> bytes:
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(width, height))
    pdf_canvas.setStrokeColorRGB(1, 0, 0)
    pdf_canvas.setFont("Helvetica", 6)

    x = 0.0
    while x <= width:
        pdf_canvas.line(x, 0, x, height)
        if int(x) % 50 == 0:
            pdf_canvas.drawString(x + 1, 2, str(int(x)))
        x += step

    y = 0.0
    while y <= height:
        pdf_canvas.line(0, y, width, y)
        if int(y) % 50 == 0:
            pdf_canvas.drawString(2, y + 1, str(int(y)))
        y += step

    pdf_canvas.save()
    return buffer.getvalue()


def main() -> None:
    generator = EanaFlightPlanPdfGenerator()
    width, height = generator._page_size()
    template_reader = PdfReader(str(generator.template_path))
    overlay_reader = PdfReader(BytesIO(build_grid_overlay(width=width, height=height)))

    writer = PdfWriter()
    for index, page in enumerate(template_reader.pages):
        if index == 0:
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    output_path = ROOT / "docs" / "eana_calibration_grid.pdf"
    with output_path.open("wb") as output_file:
        writer.write(output_file)

    print(f"Wrote calibration grid to {output_path}")
    print(f"Template page size: {width:.1f} x {height:.1f} points")


if __name__ == "__main__":
    main()

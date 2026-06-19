from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.pdf.eana_field_types import (
    ImageFieldLayout,
    MarkFieldLayout,
    TextCellsFieldLayout,
    TextFieldLayout,
    TextLinesFieldLayout,
    parse_field_layout,
)
from app.pdf.text_wrap import wrap_text_into_line_chunks
from app.pdf.eana_flight_plan_data import EanaFlightPlanPdfData


class EanaFlightPlanPdfGenerator:
    def __init__(
        self,
        *,
        layout_path: Path | None = None,
        template_path: Path | None = None,
        layout: dict[str, Any] | None = None,
    ) -> None:
        if layout is not None:
            self._layout = layout
        else:
            resolved_layout_path = layout_path or Path(__file__).resolve().parent / "eana_layout.json"
            self._layout = json.loads(resolved_layout_path.read_text(encoding="utf-8"))

        layout_template = self._layout.get("template_path")
        if template_path is not None:
            self._template_path = template_path
        elif layout_template:
            self._template_path = Path(__file__).resolve().parents[2] / layout_template
        else:
            raise ValueError("template_path is required when layout has no template_path")

        self._page_index = int(self._layout.get("page_index", 0))
        self._field_layouts = {
            name: parse_field_layout(definition)
            for name, definition in self._layout.get("fields", {}).items()
        }

    @property
    def template_path(self) -> Path:
        return self._template_path

    def _page_size(self) -> tuple[float, float]:
        reader = PdfReader(str(self._template_path))
        page = reader.pages[self._page_index]
        media_box = page.mediabox
        return float(media_box.width), float(media_box.height)

    @staticmethod
    def _draw_text_lines(
        pdf_canvas: canvas.Canvas,
        layout: TextLinesFieldLayout,
        text: str,
    ) -> None:
        pdf_canvas.setFont(layout.font_name, layout.font_size)
        for line, chunk in wrap_text_into_line_chunks(
            text,
            layout.lines,
            font_name=layout.font_name,
            font_size=layout.font_size,
        ):
            pdf_canvas.drawString(line.x, line.y, chunk)

    @staticmethod
    def _draw_text_cells(
        pdf_canvas: canvas.Canvas,
        layout: TextCellsFieldLayout,
        text: str,
    ) -> None:
        pdf_canvas.setFont(layout.font_name, layout.font_size)
        for index, char in enumerate(text[: layout.max_chars]):
            cell_x = layout.x + index * layout.cell_width
            if layout.align == "center":
                char_width = stringWidth(char, layout.font_name, layout.font_size)
                cell_x += (layout.cell_width - char_width) / 2
            pdf_canvas.drawString(cell_x, layout.y, char)

    @staticmethod
    def _truncate_text(text: str, *, font_name: str, font_size: float, max_width: float | None) -> str:
        if max_width is None or stringWidth(text, font_name, font_size) <= max_width:
            return text
        trimmed = text
        while trimmed and stringWidth(trimmed, font_name, font_size) > max_width:
            trimmed = trimmed[:-1]
        return trimmed

    def _build_overlay(self, data: EanaFlightPlanPdfData) -> bytes:
        width, height = self._page_size()
        buffer = BytesIO()
        pdf_canvas = canvas.Canvas(buffer, pagesize=(width, height))

        for field_name, layout in self._field_layouts.items():
            if isinstance(layout, TextFieldLayout):
                value = data.text_fields.get(field_name)
                if not value:
                    continue
                text = self._truncate_text(
                    value,
                    font_name=layout.font_name,
                    font_size=layout.font_size,
                    max_width=layout.max_width,
                )
                pdf_canvas.setFont(layout.font_name, layout.font_size)
                pdf_canvas.drawString(layout.x, layout.y, text)
                continue

            if isinstance(layout, TextCellsFieldLayout):
                value = data.text_fields.get(field_name)
                if not value:
                    continue
                self._draw_text_cells(pdf_canvas, layout, value)
                continue

            if isinstance(layout, TextLinesFieldLayout):
                value = data.text_fields.get(field_name)
                if not value:
                    continue
                self._draw_text_lines(pdf_canvas, layout, value)
                continue

            if isinstance(layout, MarkFieldLayout):
                if not data.mark_fields.get(field_name):
                    continue
                if layout.mark == "block":
                    pdf_canvas.setFillColorRGB(0, 0, 0)
                    pdf_canvas.setStrokeColorRGB(0, 0, 0)
                    pdf_canvas.rect(
                        layout.x,
                        layout.y,
                        layout.width or 0,
                        layout.height or 0,
                        fill=1,
                        stroke=0,
                    )
                elif layout.mark == "x":
                    pdf_canvas.setFont("Helvetica-Bold", layout.size)
                    pdf_canvas.drawString(layout.x, layout.y, "X")
                else:
                    pdf_canvas.line(layout.x, layout.y, layout.x + layout.size, layout.y)
                continue

            if isinstance(layout, ImageFieldLayout):
                if field_name != "signature" or not data.signature_png_bytes:
                    continue
                pdf_canvas.drawImage(
                    ImageReader(BytesIO(data.signature_png_bytes)),
                    layout.x,
                    layout.y,
                    width=layout.width,
                    height=layout.height,
                    mask="auto",
                )

        pdf_canvas.save()
        return buffer.getvalue()

    def generate(self, data: EanaFlightPlanPdfData) -> bytes:
        template_reader = PdfReader(str(self._template_path))
        overlay_reader = PdfReader(BytesIO(self._build_overlay(data)))

        writer = PdfWriter()
        for index, page in enumerate(template_reader.pages):
            if index == self._page_index:
                page.merge_page(overlay_reader.pages[0])
            writer.add_page(page)

        output = BytesIO()
        writer.write(output)
        return output.getvalue()

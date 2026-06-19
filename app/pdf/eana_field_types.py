from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.pdf.text_wrap import TextLineSpec


@dataclass(frozen=True)
class TextFieldLayout:
    type: Literal["text"]
    x: float
    y: float
    font_name: str = "Helvetica"
    font_size: float = 9
    max_width: float | None = None


@dataclass(frozen=True)
class TextCellsFieldLayout:
    type: Literal["text_cells"]
    x: float
    y: float
    cell_width: float
    max_chars: int
    font_name: str = "Helvetica"
    font_size: float = 9
    align: Literal["left", "center"] = "center"


@dataclass(frozen=True)
class TextLinesFieldLayout:
    type: Literal["text_lines"]
    lines: tuple[TextLineSpec, ...]
    font_name: str = "Helvetica"
    font_size: float = 8


@dataclass(frozen=True)
class MarkFieldLayout:
    type: Literal["mark"]
    x: float
    y: float
    mark: Literal["x", "line", "block"] = "x"
    size: float = 8
    width: float | None = None
    height: float | None = None


@dataclass(frozen=True)
class ImageFieldLayout:
    type: Literal["image"]
    x: float
    y: float
    width: float
    height: float


FieldLayout = TextFieldLayout | TextCellsFieldLayout | TextLinesFieldLayout | MarkFieldLayout | ImageFieldLayout


def parse_field_layout(raw: dict) -> FieldLayout:
    field_type = raw["type"]
    if field_type == "text":
        return TextFieldLayout(
            type="text",
            x=float(raw["x"]),
            y=float(raw["y"]),
            font_name=str(raw.get("font_name", "Helvetica")),
            font_size=float(raw.get("font_size", 9)),
            max_width=float(raw["max_width"]) if raw.get("max_width") is not None else None,
        )
    if field_type == "text_cells":
        align = raw.get("align", "center")
        if align not in ("left", "center"):
            raise ValueError(f"Unsupported text_cells align: {align}")
        return TextCellsFieldLayout(
            type="text_cells",
            x=float(raw["x"]),
            y=float(raw["y"]),
            cell_width=float(raw["cell_width"]),
            max_chars=int(raw["max_chars"]),
            font_name=str(raw.get("font_name", "Helvetica")),
            font_size=float(raw.get("font_size", 9)),
            align=align,
        )
    if field_type == "text_lines":
        line_specs = tuple(
            TextLineSpec(
                x=float(line["x"]),
                y=float(line["y"]),
                max_width=float(line["max_width"]),
            )
            for line in raw["lines"]
        )
        if not line_specs:
            raise ValueError("text_lines requires at least one line")
        return TextLinesFieldLayout(
            type="text_lines",
            lines=line_specs,
            font_name=str(raw.get("font_name", "Helvetica")),
            font_size=float(raw.get("font_size", 8)),
        )
    if field_type == "mark":
        mark = raw.get("mark", "x")
        if mark not in ("x", "line", "block"):
            raise ValueError(f"Unsupported mark type: {mark}")
        width = float(raw["width"]) if raw.get("width") is not None else None
        height = float(raw["height"]) if raw.get("height") is not None else None
        if mark == "block" and (width is None or height is None):
            raise ValueError("block marks require width and height")
        return MarkFieldLayout(
            type="mark",
            x=float(raw["x"]),
            y=float(raw["y"]),
            mark=mark,
            size=float(raw.get("size", 8)),
            width=width,
            height=height,
        )
    if field_type == "image":
        return ImageFieldLayout(
            type="image",
            x=float(raw["x"]),
            y=float(raw["y"]),
            width=float(raw["width"]),
            height=float(raw["height"]),
        )
    raise ValueError(f"Unsupported field layout type: {field_type}")

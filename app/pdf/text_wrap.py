from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reportlab.pdfbase.pdfmetrics import stringWidth


@dataclass(frozen=True)
class TextLineSpec:
    x: float
    y: float
    max_width: float


def fit_text_chunk(
    text: str,
    *,
    max_width: float,
    font_name: str,
    font_size: float,
) -> str:
    if not text:
        return ""

    if stringWidth(text, font_name, font_size) <= max_width:
        return text

    words = text.split(" ")
    if len(words) > 1:
        fitted_words: list[str] = []
        for word in words:
            candidate = " ".join(fitted_words + [word]) if fitted_words else word
            if stringWidth(candidate, font_name, font_size) <= max_width:
                fitted_words.append(word)
            else:
                break
        if fitted_words:
            return " ".join(fitted_words)

    chunk = ""
    for char in text:
        candidate = chunk + char
        if stringWidth(candidate, font_name, font_size) <= max_width:
            chunk = candidate
        else:
            break
    return chunk


def wrap_text_into_line_chunks(
    text: str,
    lines: tuple[TextLineSpec, ...],
    *,
    font_name: str,
    font_size: float,
) -> list[tuple[TextLineSpec, str]]:
    remaining = " ".join(text.split())
    rendered: list[tuple[TextLineSpec, str]] = []

    for line in lines:
        if not remaining:
            break
        chunk = fit_text_chunk(
            remaining,
            max_width=line.max_width,
            font_name=font_name,
            font_size=font_size,
        )
        if not chunk:
            break
        rendered.append((line, chunk))
        remaining = remaining[len(chunk) :].lstrip()

    return rendered

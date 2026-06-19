from app.pdf.eana_field_types import TextLinesFieldLayout, parse_field_layout
from app.pdf.text_wrap import TextLineSpec, fit_text_chunk, wrap_text_into_line_chunks


def test_parse_text_cells_field_layout():
    layout = parse_field_layout(
        {
            "type": "text_cells",
            "x": 100,
            "y": 200,
            "cell_width": 14,
            "max_chars": 7,
            "font_size": 11,
            "align": "center",
        }
    )

    from app.pdf.eana_field_types import TextCellsFieldLayout

    assert isinstance(layout, TextCellsFieldLayout)
    assert layout.x == 100
    assert layout.y == 200
    assert layout.cell_width == 14
    assert layout.max_chars == 7
    assert layout.font_size == 11
    assert layout.font_name == "Helvetica"
    assert layout.align == "center"


def test_parse_block_mark_field_layout():
    layout = parse_field_layout(
        {
            "type": "mark",
            "mark": "block",
            "x": 425,
            "y": 225,
            "width": 10,
            "height": 10,
        }
    )

    from app.pdf.eana_field_types import MarkFieldLayout

    assert isinstance(layout, MarkFieldLayout)
    assert layout.mark == "block"
    assert layout.width == 10
    assert layout.height == 10


def test_parse_text_lines_field_layout():
    layout = parse_field_layout(
        {
            "type": "text_lines",
            "font_size": 8,
            "lines": [
                {"x": 275, "y": 472, "max_width": 245},
                {"x": 50, "y": 460, "max_width": 470},
            ],
        }
    )

    assert isinstance(layout, TextLinesFieldLayout)
    assert layout.font_size == 8
    assert len(layout.lines) == 2
    assert layout.lines[0] == TextLineSpec(x=275, y=472, max_width=245)


def test_wrap_text_splits_across_lines_by_words():
    lines = (
        TextLineSpec(x=0, y=40, max_width=60),
        TextLineSpec(x=0, y=30, max_width=120),
        TextLineSpec(x=0, y=20, max_width=120),
    )

    chunks = wrap_text_into_line_chunks(
        "DCT GUALE DCT SANTU DCT",
        lines,
        font_name="Helvetica",
        font_size=8,
    )

    assert len(chunks) >= 2
    assert " ".join(chunk for _, chunk in chunks) == "DCT GUALE DCT SANTU DCT"


def test_fit_text_chunk_breaks_long_word_by_character():
    chunk = fit_text_chunk(
        "ABCDEFGHIJKLMNOP",
        max_width=30,
        font_name="Helvetica",
        font_size=8,
    )

    assert chunk
    assert len(chunk) < len("ABCDEFGHIJKLMNOP")

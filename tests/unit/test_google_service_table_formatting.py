from services.google_service import GoogleDocsService


def _cell(start: int, end: int) -> dict:
    return {"startIndex": start, "endIndex": end}


def _row(row_start: int, columns: int = 6) -> dict:
    return {
        "tableCells": [
            _cell(row_start + column * 10, row_start + column * 10 + 8)
            for column in range(columns)
        ]
    }


def test_standard_table_alignment_requests_format_document_rows():
    table = {
        "tableRows": [
            _row(100),  # header
            _row(200),
            _row(300),
            _row(400),  # footer, should be handled separately after merge
        ]
    }

    requests = GoogleDocsService._build_standard_table_alignment_requests(
        table,
        data_rows_count=3,
        has_footer=True,
    )

    by_start = {}
    for request in requests:
        paragraph_style = request["updateParagraphStyle"]
        by_start[paragraph_style["range"]["startIndex"]] = paragraph_style["paragraphStyle"]["alignment"]

    assert len(requests) == 12
    assert by_start[200] == "CENTER"
    assert by_start[210] == "START"
    assert by_start[220] == "CENTER"
    assert by_start[230] == "END"
    assert by_start[240] == "END"
    assert by_start[250] == "END"
    assert by_start[310] == "START"
    assert 410 not in by_start


def test_standard_table_alignment_requests_include_last_row_when_no_footer():
    table = {
        "tableRows": [
            _row(100),
            _row(200),
        ]
    }

    requests = GoogleDocsService._build_standard_table_alignment_requests(
        table,
        data_rows_count=1,
        has_footer=False,
    )

    starts = {
        request["updateParagraphStyle"]["range"]["startIndex"]
        for request in requests
    }

    assert len(requests) == 6
    assert {200, 210, 220, 230, 240, 250}.issubset(starts)


def test_standard_table_alignment_requests_skip_invalid_ranges():
    table = {
        "tableRows": [
            _row(100),
            {
                "tableCells": [
                    _cell(200, 208),
                    {"endIndex": 218},
                    _cell(220, 220),
                    _cell(230, 238),
                ]
            },
        ]
    }

    requests = GoogleDocsService._build_standard_table_alignment_requests(
        table,
        data_rows_count=1,
        has_footer=False,
    )

    starts = [
        request["updateParagraphStyle"]["range"]["startIndex"]
        for request in requests
    ]

    assert starts == [200, 230]


def test_footer_table_style_requests_align_first_and_last_cells():
    cells = [_cell(200 + column * 10, 208 + column * 10) for column in range(6)]

    requests = GoogleDocsService._build_footer_table_style_requests(cells)

    text_style_starts = [
        request["updateTextStyle"]["range"]["startIndex"]
        for request in requests
        if "updateTextStyle" in request
    ]
    paragraph_styles = {
        request["updateParagraphStyle"]["range"]["startIndex"]: (
            request["updateParagraphStyle"]["paragraphStyle"]["alignment"]
        )
        for request in requests
        if "updateParagraphStyle" in request
    }

    assert text_style_starts == [200, 250]
    assert paragraph_styles == {200: "END", 250: "END"}


def test_footer_table_style_requests_align_two_cell_footer():
    cells = [_cell(200, 208), _cell(250, 258)]

    requests = GoogleDocsService._build_footer_table_style_requests(cells)

    starts = [
        request["updateParagraphStyle"]["range"]["startIndex"]
        for request in requests
        if "updateParagraphStyle" in request
    ]

    assert starts == [200, 250]

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from services.xlsx_reader import read_xlsx_sheet


def _xlsx_with_workbook_xml(workbook_xml: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships" />
            """,
        )
    return buffer.getvalue()


def test_xlsx_reader_rejects_xml_entities():
    content = _xlsx_with_workbook_xml(
        """<?xml version="1.0"?>
        <!DOCTYPE workbook [<!ENTITY injected "unsafe">]>
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheets><sheet name="&injected;" /></sheets>
        </workbook>
        """
    )

    with pytest.raises(ValueError, match="unsafe or invalid"):
        read_xlsx_sheet(content, "Sheet1")


def test_xlsx_reader_rejects_invalid_zip():
    with pytest.raises(ValueError, match="valid ZIP"):
        read_xlsx_sheet(b"not-a-zip", "Sheet1")

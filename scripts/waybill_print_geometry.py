"""Extract only numeric grid geometry from an operator-provided XLSX reference."""

import json
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
BODY = {"tn2": ("ТН-2", 31), "ttn1": ("ТТН-1", 61)}
LAYOUT = (
    Path(__file__).resolve().parents[1] / "config/native_document_template_bundles/waybill-print-grid.json"
)


def read_grid(source, kind):
    sheet_name, end = BODY[kind]
    with ZipFile(source) as book:
        work = ET.fromstring(book.read("xl/workbook.xml"))
        tab = next(s for s in work.iter(MAIN + "sheet") if s.get("name") == sheet_name)
        rel = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next(item.get("Target") for item in rel if item.get("Id") == tab.get(OFFICE_REL + "id"))
        entry = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("xl", target))
        )
        root = ET.fromstring(book.read(entry))

    setup = root.find(MAIN + "pageSetup")
    if setup is None or (setup.get("paperSize"), setup.get("orientation")) != ("9", "portrait"):
        raise ValueError("Проверьте книжную ориентацию A4 на печатной вкладке")
    margins = root.find(MAIN + "pageMargins")
    if margins is None:
        raise ValueError("В исходном файле не записаны поля страницы")
    cols = [None] * 31
    for col in root.iter(MAIN + "col"):
        start, stop = int(col.get("min")), int(col.get("max"))
        for j in range(start - 1, min(stop, 31)):
            cols[j] = float(col.get("width"))
    if None in cols:
        raise ValueError("В исходном файле заданы не все 31 ширины столбцов")
    defaults = root.find(MAIN + "sheetFormatPr")
    heights = [float(defaults.get("defaultRowHeight", 15))] * end
    for row in root.iter(MAIN + "row"):
        idx = int(row.get("r")) - 1
        if 0 <= idx < end and row.get("ht"):
            heights[idx] = float(row.get("ht"))
    # Store only geometry. No cell text, formulas, properties, document identity or signatories.
    return {
        "widths": cols,
        "heights_pt": heights,
        "margins_mm": {
            side: round(float(margins.get(side)) * 25.4, 4) for side in ("left", "right", "top", "bottom")
        },
    }


def extract(source_dir, destination):
    collected = {kind: read_grid(source_dir / (kind + ".xlsx"), kind) for kind in BODY}
    destination.write_text(json.dumps(collected, indent=2) + "\n", encoding="utf-8")

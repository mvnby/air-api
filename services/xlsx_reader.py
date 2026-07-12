from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
MAX_XLSX_ARCHIVE_ENTRIES = 2_048
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 1_000


@dataclass(frozen=True)
class XlsxCell:
    value: str
    hyperlink: str | None = None


@dataclass(frozen=True)
class XlsxSheet:
    name: str
    rows: list[list[XlsxCell]]


def read_xlsx_sheet(content: bytes, sheet_name: str) -> XlsxSheet:
    try:
        archive_context = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise ValueError("XLSX file is not a valid ZIP archive") from exc

    with archive_context as archive:
        _validate_archive(archive)
        shared_strings = _read_shared_strings(archive)
        worksheet_path = _worksheet_path_for_name(archive, sheet_name)
        rels = _read_worksheet_rels(archive, worksheet_path)
        root = _parse_xml(archive.read(worksheet_path), worksheet_path)
        hyperlink_by_ref = _read_hyperlinks(root, rels)

        rows: list[list[XlsxCell]] = []
        for row_node in root.findall(".//a:sheetData/a:row", NS):
            cells_by_idx: dict[int, XlsxCell] = {}
            for cell_node in row_node.findall("a:c", NS):
                ref = str(cell_node.attrib.get("r") or "")
                col_idx = _cell_col_idx(ref)
                if col_idx < 0:
                    continue
                value = _read_cell_value(cell_node, shared_strings)
                hyperlink = _hyperlink_for_cell_ref(ref, hyperlink_by_ref)
                cells_by_idx[col_idx] = XlsxCell(value=value, hyperlink=hyperlink)
            if not cells_by_idx:
                rows.append([])
                continue
            width = max(cells_by_idx) + 1
            rows.append([cells_by_idx.get(idx, XlsxCell("")) for idx in range(width)])

    return XlsxSheet(name=sheet_name, rows=rows)


def _validate_archive(archive: ZipFile) -> None:
    members = archive.infolist()
    if len(members) > MAX_XLSX_ARCHIVE_ENTRIES:
        raise ValueError("XLSX archive contains too many entries")

    total_size = 0
    for member in members:
        file_size = max(0, int(member.file_size or 0))
        compressed_size = max(0, int(member.compress_size or 0))
        total_size += file_size
        if total_size > MAX_XLSX_UNCOMPRESSED_BYTES:
            raise ValueError("XLSX archive exceeds the uncompressed size limit")
        if file_size and (
            compressed_size == 0
            or file_size / compressed_size > MAX_XLSX_COMPRESSION_RATIO
        ):
            raise ValueError("XLSX archive contains a suspicious compression ratio")


def _parse_xml(raw: bytes, source_name: str) -> Element:
    try:
        return ET.fromstring(raw)
    except (ParseError, DefusedXmlException) as exc:
        raise ValueError(f"XLSX XML part is unsafe or invalid: {source_name}") from exc


def _read_shared_strings(archive: ZipFile) -> list[str]:
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = _parse_xml(raw, "xl/sharedStrings.xml")
    values: list[str] = []
    for item in root.findall("a:si", NS):
        texts = [node.text or "" for node in item.findall(".//a:t", NS)]
        values.append("".join(texts))
    return values


def _worksheet_path_for_name(archive: ZipFile, sheet_name: str) -> str:
    workbook = _parse_xml(archive.read("xl/workbook.xml"), "xl/workbook.xml")
    rels_root = _parse_xml(
        archive.read("xl/_rels/workbook.xml.rels"),
        "xl/_rels/workbook.xml.rels",
    )
    rel_targets = {
        rel.attrib.get("Id"): rel.attrib.get("Target")
        for rel in rels_root.findall("rel:Relationship", NS)
    }

    wanted = sheet_name.casefold()
    for sheet in workbook.findall(".//a:sheets/a:sheet", NS):
        name = str(sheet.attrib.get("name") or "")
        if name.casefold() != wanted:
            continue
        rel_id = sheet.attrib.get(f"{{{NS['r']}}}id")
        target = rel_targets.get(rel_id)
        if not target:
            break
        return _normalize_xl_path(target)

    available = [str(sheet.attrib.get("name") or "") for sheet in workbook.findall(".//a:sheets/a:sheet", NS)]
    raise ValueError(f"XLSX sheet '{sheet_name}' was not found. Available: {', '.join(available)}")


def _normalize_xl_path(target: str) -> str:
    value = target.lstrip("/")
    if value.startswith("xl/"):
        return value
    return f"xl/{value}"


def _read_worksheet_rels(archive: ZipFile, worksheet_path: str) -> dict[str, str]:
    rels_path = worksheet_path.replace("xl/worksheets/", "xl/worksheets/_rels/") + ".rels"
    try:
        raw = archive.read(rels_path)
    except KeyError:
        return {}
    root = _parse_xml(raw, rels_path)
    out: dict[str, str] = {}
    for rel in root.findall("rel:Relationship", NS):
        rel_id = str(rel.attrib.get("Id") or "")
        target = str(rel.attrib.get("Target") or "")
        if rel_id and target:
            out[rel_id] = target
    return out


def _read_hyperlinks(root: Element, rels: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for link in root.findall(".//a:hyperlinks/a:hyperlink", NS):
        ref = str(link.attrib.get("ref") or "").strip()
        if not ref:
            continue
        rel_id = link.attrib.get(f"{{{NS['r']}}}id")
        location = str(link.attrib.get("location") or "").strip()
        target = rels.get(str(rel_id or ""), "") or location
        if target:
            out[ref] = target
    return out


def _read_cell_value(cell_node: Element, shared_strings: list[str]) -> str:
    cell_type = cell_node.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell_node.findall(".//a:t", NS)).strip()

    raw_value = cell_node.findtext("a:v", default="", namespaces=NS)
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)].strip()
        except (ValueError, IndexError):
            return ""
    if cell_type == "b":
        return "TRUE" if raw_value == "1" else "FALSE"
    return str(raw_value or "").strip()


def _hyperlink_for_cell_ref(cell_ref: str, hyperlink_by_ref: dict[str, str]) -> str | None:
    if cell_ref in hyperlink_by_ref:
        return hyperlink_by_ref[cell_ref]
    for ref, hyperlink in hyperlink_by_ref.items():
        if ":" not in ref:
            continue
        start, end = ref.split(":", 1)
        if _cell_in_range(cell_ref, start, end):
            return hyperlink
    return None


def _cell_in_range(cell_ref: str, start: str, end: str) -> bool:
    col, row = _split_cell_ref(cell_ref)
    start_col, start_row = _split_cell_ref(start)
    end_col, end_row = _split_cell_ref(end)
    return start_col <= col <= end_col and start_row <= row <= end_row


def _cell_col_idx(cell_ref: str) -> int:
    col, _ = _split_cell_ref(cell_ref)
    return col


def _split_cell_ref(cell_ref: str) -> tuple[int, int]:
    match = re.match(r"^([A-Z]+)(\d+)$", str(cell_ref or "").upper())
    if not match:
        return -1, -1
    col = 0
    for ch in match.group(1):
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return col - 1, int(match.group(2))

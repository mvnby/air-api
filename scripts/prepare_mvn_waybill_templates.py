"""Build editable A4 paper waybills from a numeric grid; never ingest reference text."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import sys
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.waybill_print_geometry import LAYOUT, extract

ID = "mvn-paper-waybills-v1"
TITLES = {"tn2": "ТН-2", "ttn1": "ТТН-1"}
TARGET = {"tenant_slug": "mvn", "tenant_id": 1, "default_legal_entity_id": 1, "is_vat_payer": False}


def field(name):
    return "{{ " + name + " }}"


def text_of(names):
    return " ".join(field(name) for name in names.split())


def column_index(name):
    index = 0
    for c in name:
        index = index * 26 + ord(c) - ord("A") + 1
    return index - 1


class Page:
    def __init__(self, kind, geometry):
        self.kind, self.document = kind, Document()
        self.section = self.document.sections[0]
        self.section.page_width, self.section.page_height = Mm(210), Mm(297)
        self.margins = geometry["margins_mm"]
        for side, amount in self.margins.items():
            setattr(self.section, side + "_margin", Mm(amount))
        self.section.header_distance = self.section.footer_distance = Mm(0)
        pixels = [round(width * 8) - 1 for width in geometry["widths"]]
        available = 210 - self.margins["left"] - self.margins["right"]
        self.widths = [width * available / sum(pixels) for width in pixels]
        style = self.document.styles["Normal"]
        style.font.name, style.font.size = "Liberation Sans", Pt(6.5)
        style.paragraph_format.space_before = style.paragraph_format.space_after = Pt(0)
        self.new_table()

    def new_table(self):
        self.table = self.document.add_table(rows=0, cols=len(self.widths))
        self.table.autofit = False
        for col, width in zip(self.table.columns, self.widths, strict=True):
            col.width = Mm(width)
        margins = OxmlElement("w:tblCellMar")
        for side, width in (("top", 0), ("bottom", 0), ("left", 28), ("right", 28)):
            m = OxmlElement("w:" + side)
            m.set(qn("w:w"), str(width))
            m.set(qn("w:type"), "dxa")
            margins.append(m)
        self.table._tbl.tblPr.append(margins)

    def row(
        self,
        height,
        entries=(),
        *,
        size=6.5,
        bold=False,
        align="left",
        grid=False,
        center_y=False,
        alignments=None,
    ):
        """Entries start in XLSX columns. Every band may grow; text is never clipped."""
        row = self.table.add_row()
        row.height = Mm(height)
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        raw = list(row.cells)
        spans = [(column_index(col), val) for col, val in entries]
        if not spans or spans[0][0] > 0:
            spans.insert(0, (0, ""))
        for i, (start, value) in enumerate(spans):
            stop = spans[i + 1][0] if i + 1 < len(spans) else len(raw)
            cell = raw[start] if stop == start + 1 else raw[start].merge(raw[stop - 1])
            cell.width = Mm(sum(self.widths[start:stop]))
            cell.vertical_alignment = (
                WD_CELL_VERTICAL_ALIGNMENT.CENTER if center_y else WD_CELL_VERTICAL_ALIGNMENT.TOP
            )
            paragraph = cell.paragraphs[0]
            cell_align = align if alignments is None else alignments.get(start, align)
            paragraph.alignment = {
                "left": WD_ALIGN_PARAGRAPH.LEFT,
                "center": WD_ALIGN_PARAGRAPH.CENTER,
                "right": WD_ALIGN_PARAGRAPH.RIGHT,
            }[cell_align]
            paragraph.paragraph_format.space_before = paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = Pt(size * 1.18 if value else 1)
            run = paragraph.add_run(value)
            run.font.name, run.font.size, run.bold = "Liberation Sans", Pt(size if value else 1), bold
            if grid and start:
                borders = OxmlElement("w:tcBorders")
                for side in ("top", "bottom", "left", "right"):
                    b = OxmlElement("w:" + side)
                    b.set(qn("w:val"), "single")
                    b.set(qn("w:sz"), "3")
                    borders.append(b)
                cell._tc.get_or_add_tcPr().append(borders)
        return row


def party(role):
    return (
        field(role + (".legal_name" if role == "seller" else ".full_name"))
        + "  "
        + field(role + ".legal_address")
    )


def header(page):
    truck = page.kind == "ttn1"
    recipient = "R" if truck else "S"
    labels = [("N", "Грузоотправитель"), (recipient, "Грузополучатель")]
    numbers = [("L", "УНП"), ("N", field("seller.unp")), (recipient, field("customer.unp"))]
    if truck:
        labels.append(("T", "Заказчик автоперевозки"))
        numbers.append(("T", field("transport.freight_payer_unp")))
    labels.append(("W", ""))
    numbers.append(("W", ""))
    page.row(5.7, labels, size=5.8, align="center")
    page.row(3.4, numbers, size=6.8, align="center")
    # The upper band is occupied by the series, number and title of the physical stock.
    page.row(28.4 if truck else 32.5)
    page.row(7.3 if truck else 6.7, [("B", field("waybill.preprinted_a4") + field("document.issued_on"))], size=7)
    if truck:
        page.row(
            4.8,
            [
                ("B", "Автомобиль"),
                ("E", text_of("transport.car_model transport.car_number")),
                ("P", "Прицеп"),
                ("X", "К путевому листу №"),
                ("AB", field("transport.trip_sheet_number")),
            ],
        )
        page.row(4.8, [("B", "Водитель"), ("E", field("transport.driver_name"))])
        page.row(
            3.2,
            [
                ("B", "Заказчик автомобильной перевозки (плательщик)"),
                ("M", field("transport.freight_payer")),
            ],
        )
    page.row(3.2, [("B", "Грузоотправитель"), ("F", party("seller"))], size=6.8)
    page.row(6.0 if truck else 3.2, [("B", "Грузополучатель"), ("F", party("customer"))], size=6.8)
    basis = field("basis.type") + " № " + field("basis.number") + " от " + field("basis.date")
    if truck:
        page.row(
            13.7,
            [
                ("B", "Основание отпуска"),
                ("F", basis),
                ("L", "Пункт погрузки"),
                ("O", field("transport.loading_point")),
                ("V", "Пункт разгрузки"),
                ("Y", field("transport.unloading_point")),
            ],
            center_y=True,
        )
        page.row(5.7, [("B", "Переадресовка")])
    else:
        page.row(5.9, [("B", "Основание отпуска"), ("F", basis)])
    page.row(3.5, [("B", "I. ТОВАРНЫЙ РАЗДЕЛ")], bold=True, align="center")


def goods(page):
    truck = page.kind == "ttn1"
    columns = (
        ["B", "J", "K", "L", "N", "R", "S", "U", "W", "Y", "AA"]
        if truck
        else ["B", "J", "K", "L", "O", "S", "T", "W", "AA"]
    )
    captions = [
        "Наименование товара",
        "Ед. изм.",
        "Количество",
        "Цена",
        "Стоимость",
        "Ставка НДС",
        "Сумма НДС, руб.",
        "Стоимость с НДС, руб.",
    ]
    if truck:
        captions.extend(["Грузовых мест", "Масса груза, кг"])
    captions.append("Примечание")
    page.new_table()
    for height, values in ((8.7, captions), (2.8, [str(i + 1) for i in range(len(columns))])):
        row = page.row(
            height, list(zip(columns, values)), size=5.7, grid=True, align="center", center_y=True
        )
        row._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    # Country may be unknown; do not print a caption or invent an origin in that case.
    tokens = [
        field("lines") + field("line.title") + "\n" + field("line.country"),
        field("line.unit"),
        field("line.quantity"),
        field("line.unit_price"),
        field("line.amount"),
        field("line.vat_label"),
        "—",
        field("line.amount"),
    ]
    totals = [
        "ИТОГО",
        "",
        field("totals.quantity"),
        "",
        field("totals.amount"),
        "",
        "—",
        field("waybill.no_vat_total"),
    ]
    if truck:
        tokens.extend([field("line.seats"), field("line.mass")])
        totals.extend([field("totals.seats"), field("totals.weight")])
    tokens.append(field("line.note"))
    totals.append("")
    alignments = {column_index(c): "right" for c in columns[2:-1]}
    alignments.update({column_index(c): "center" for c in ("J", "R" if truck else "S", "AA")})
    page.row(8.05, list(zip(columns, tokens)), size=6.4, grid=True, center_y=True, alignments=alignments)
    alignments[column_index("B")] = "center"
    page.row(
        3.5,
        list(zip(columns, totals)),
        size=6.4,
        bold=True,
        grid=True,
        center_y=True,
        alignments=alignments,
    )
    page.new_table()


def footer(page):
    truck = page.kind == "ttn1"
    page.row(4.2)
    amount_col = "G" if truck else "I"
    page.row(4.5, [("B", "Всего сумма НДС"), (amount_col, "—")])
    page.row(
        5.3 if truck else 8.3,
        [("B", "Всего стоимость с НДС"), (amount_col, field("totals.amount_in_words"))],
        size=7,
    )
    if truck:
        page.row(
            6.5,
            [
                ("B", "Всего масса груза, кг"),
                ("G", field("totals.weight_in_words")),
                ("R", "Всего количество грузовых мест"),
                ("X", field("totals.seats_in_words")),
            ],
        )
    if not truck:
        for label in (
            "Отпуск разрешил",
            "Сдал грузоотправитель",
            "Товар к доставке принял",
            "Выданной",
            "Принял грузополучатель",
        ):
            entries = [("B", label), ("I", "_____________________")]
            if label == "Товар к доставке принял":
                entries.append(("S", "По доверенности"))
            page.row(8.25, entries)
        page.row(6, [("B", "С товаром переданы документы")])
        return
    for entries in (
        [
            ("B", "Отпуск разрешил"),
            ("G", "________________"),
            ("R", "Товар к перевозке принял"),
            ("X", "________________"),
        ],
        [
            ("B", "Сдал грузоотправитель"),
            ("G", "________________"),
            ("N", "№ пломбы"),
            ("R", "По доверенности"),
            ("X", "Выданной"),
        ],
        [("R", "Принял грузополучатель"), ("AB", "№ пломбы")],
        [("B", "Штамп (печать) грузоотправителя"), ("R", "Штамп (печать) грузополучателя")],
    ):
        page.row(5.0, entries, size=6.3)
    page.row(4.2, [("B", "II. ПОГРУЗОЧНО-РАЗГРУЗОЧНЫЕ ОПЕРАЦИИ")], bold=True, align="center")
    cols = ["B", "D", "I", "L", "M", "O", "R", "T", "V", "Y", "AA"]

    def cells(height, starts, captions, *, size=5.4):
        page.row(height, list(zip(starts, captions, strict=True)), size=size, grid=True, center_y=True)

    cells(
        4.0,
        ["B", "D", "I", "L", "M", "T", "Y", "AA"],
        [
            "Операция",
            "Исполнитель",
            "Способ погрузки",
            "Код",
            "Дата и время (ч, мин)",
            "Дополнительные операции",
            "Подпись",
            "Транспортные услуги",
        ],
    )
    cells(3.6, cols, ["", "", "", "", "прибытие", "убытие", "простой", "время", "наименование", "", ""])
    cells(2.6, cols, ["", "12", "13", "14", "15", "16", "17", "18", "19", "20", ""], size=5.1)
    for label, stage in (("Погрузка", "loading"), ("Разгрузка", "unloading")):
        values = [
            label,
            field(f"transport.{stage}.performer"),
            field(f"transport.{stage}.method"),
            "",
            field(f"waybill.{stage}.arrived_at"),
            field(f"waybill.{stage}.departed_at"),
            field(f"transport.{stage}.downtime"),
            "",
            "",
            "",
            "",
        ]
        cells(3.1, cols, values, size=5.3)
    page.row(3.0, [("AA", "Составленные акты (дата, номер)")], size=5.3)
    page.row(
        4.0, [("B", "III. ПРОЧИЕ СВЕДЕНИЯ (заполняются перевозчиком)")], bold=True, align="center", size=5.9
    )
    cells(
        4.0,
        ["B", "L", "O", "R", "W"],
        [
            "Расстояние перевозки по группам дорог, км",
            "Код экспедитора",
            "За транспортные услуги",
            "Поправочный коэффициент",
            "Штраф",
        ],
    )
    cells(
        3.8,
        ["B", "D", "F", "J", "K", "L", "O", "R", "U", "W"],
        ["всего", "в городе", "I", "II", "III", "", "", "расценки водителю", "основной тариф", ""],
    )
    cols = ["B", "D", "F", "J", "K", "L", "O", "R", "U", "W", "Y", "AA"]
    cells(3.0, cols, [*map(str, range(21, 32)), "Таксировка"])
    cells(4.5, cols, [""] * len(cols))
    cols = ["B", "D", "E", "J", "K", "L", "N", "Q", "S", "U", "X", "AA"]
    cells(
        4.5,
        ["B", "D", "E", "J", "K", "L", "N", "S", "U", "X"],
        [
            "Расчёт стоимости",
            "За тонны",
            "За расстояние перевозки",
            "За специальный транспорт",
            "За транспортные услуги",
            "Погрузочно-разгрузочные работы, т",
            "Сверхнормативный простой",
            "Прочие доплаты",
            "Дополнительные услуги (экспедирование)",
            "К оплате",
        ],
    )
    cells(
        3.8,
        cols,
        [
            "",
            "",
            "",
            "",
            "",
            "",
            "погрузка",
            "разгрузка",
            "",
            "",
            "итого",
            "в том числе транспортно-экспедиционному предприятию",
        ],
    )
    cells(2.8, cols, ["", *map(str, range(32, 43))])
    for label in ("По заказу", "Выполнено", "Расценка", "К оплате"):
        cells(2.8, cols, [label] + [""] * (len(cols) - 1))
    page.row(7, [("B", "С товаром переданы документы")])


def form_bytes(kind, geometry):
    page = Page(kind, geometry)
    header(page)
    goods(page)
    footer(page)
    meta = page.document.core_properties
    meta.title = TITLES[kind] + " · печать на бланке"
    meta.author = "Kitlane"
    meta.created = meta.modified = datetime(2000, 1, 1, tzinfo=timezone.utc)
    raw = BytesIO()
    page.document.save(raw)
    output = BytesIO()
    with ZipFile(raw) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            info = ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            target.writestr(info, source.read(name))
    return output.getvalue()


def prepare(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    geometry = json.loads(LAYOUT.read_text())
    entries = []
    for kind, title in TITLES.items():
        data = form_bytes(kind, geometry[kind])
        name = kind + "-paper-v1.docx"
        (directory / name).write_bytes(data)
        entries.append(
            {
                "key": kind,
                "name": title + " · печать на бланке",
                "doc_type": kind,
                "description": "Книжный A4, печать на бланке. Сверьте поля и количество страниц в предпросмотре.",
                "source_filename": name,
                "sha256": sha256(data).hexdigest(),
                "sort_order": 50,
            }
        )
    return {
        "bundle_id": ID,
        "target": TARGET,
        "description": "Две формы печати на бланке A4 для основного продавца MVN без НДС.",
        "templates": entries,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--extract-grid-from",
        type=Path,
        help="Каталог приватных tn2.xlsx и ttn1.xlsx для восстановления обезличенной геометрии",
    )
    args = parser.parse_args()
    if args.extract_grid_from:
        extract(args.extract_grid_from, LAYOUT)
    output = prepare(args.output_dir)
    if args.manifest:
        args.manifest.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

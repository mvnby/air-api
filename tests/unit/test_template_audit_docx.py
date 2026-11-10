from base64 import b64decode
from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Inches
from lxml import etree
import pytest

from modules.documents.infrastructure.template_audit_docx import (
    DocxAuditError,
    apply_docx_edits,
    inspect_docx,
)


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _save(document):
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _parts(source):
    with ZipFile(BytesIO(source)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _package(source, changes):
    output = BytesIO()
    with (
        ZipFile(BytesIO(source)) as original,
        ZipFile(output, "w", compression=ZIP_DEFLATED) as archive,
    ):
        archive.comment = b"retained package comment"
        for info in original.infolist():
            archive.writestr(info, changes.get(info.filename, original.read(info)))
        for part, content in changes.items():
            if part not in original.namelist():
                archive.writestr(part, content)
    return output.getvalue()


def _story(root, tag, text):
    paragraph = etree.SubElement(root, qn("w:p"))
    run = etree.SubElement(paragraph, qn("w:r"))
    etree.SubElement(run, qn("w:t")).text = text
    return paragraph


def _complex_docx():
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Старый ").bold = True
    paragraph.add_run("текст ").italic = True
    paragraph.add_run("{{ customer.")
    paragraph.add_run("full_name }}")
    document.add_paragraph("{{#if seller.is_company}}")
    document.add_paragraph("Условия договора")
    document.add_paragraph("{{/if seller.is_company}}")
    controlled = document.add_paragraph("Вложенный SDT")
    outer, outer_content = OxmlElement("w:sdt"), OxmlElement("w:sdtContent")
    inner, inner_content = OxmlElement("w:sdt"), OxmlElement("w:sdtContent")
    controlled._p.addprevious(outer)
    outer.append(outer_content)
    outer_content.append(inner)
    inner.append(inner_content)
    inner_content.append(controlled._p)
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Таблица {{ lines }} {{ line.title }}"
    nested = table.cell(0, 0).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "Вложенная таблица"
    document.sections[0].header.paragraphs[0].text = "Верх {{ seller.name }}"
    document.sections[0].footer.paragraphs[0].text = "Низ"
    source = _save(document)
    changes = {}
    for plural, singular, text in (
        ("footnotes", "footnote", "Сноска {{ customer.address }}"),
        ("endnotes", "endnote", "Концевая сноска"),
        ("comments", "comment", "Комментарий {{ customer.name }}"),
    ):
        root = etree.Element(qn(f"w:{plural}"), nsmap={"w": _W})
        entry = etree.SubElement(root, qn(f"w:{singular}"), {qn("w:id"): "1"})
        _story(entry, singular, text)
        changes[f"word/{plural}.xml"] = etree.tostring(root)
    types = etree.fromstring(_parts(source)["[Content_Types].xml"])
    for part in changes:
        etree.SubElement(
            types,
            f"{{{_CT}}}Override",
            PartName=f"/{part}",
            ContentType=f"application/vnd.openxmlformats-officedocument.wordprocessingml.{part.split('/')[-1][:-4]}+xml",
        )
    changes["[Content_Types].xml"] = etree.tostring(types)
    changes["custom/preserved.bin"] = b"unrelated\x00bytes\xff"
    return _package(source, changes)


def _block(report, text):
    return next(block for block in report["blocks"] if block["original_text"] == text)


def _edit(block, replacement):
    return {
        "block_id": block["block_id"],
        "expected_text": block["original_text"],
        "replacement_text": replacement,
    }


def test_inspects_every_story_nested_sdt_tables_and_complete_untruncated_text():
    source = _complex_docx()
    report = inspect_docx(source)
    assert report["coverage"] == {
        "complete": True,
        "reasons": [],
        "nontext_assets": 0,
        "requires_visual_review": False,
    }
    assert report["source_sha256"] == sha256(source).hexdigest()
    texts = {block["original_text"] for block in report["blocks"]}
    assert texts >= {
        "Вложенный SDT",
        "Вложенная таблица",
        "Таблица {{ lines }} {{ line.title }}",
        "Верх {{ seller.name }}",
        "Низ",
        "Сноска {{ customer.address }}",
        "Концевая сноска",
        "Комментарий {{ customer.name }}",
    }
    controlled = _block(report, "Вложенный SDT")
    assert [item["kind"] for item in controlled["context"]].count("sdt") == 2
    cell = _block(report, "Вложенная таблица")
    assert [item["kind"] for item in cell["context"]].count("tc") == 2
    conditional = _block(report, "{{#if seller.is_company}}")
    assert conditional["conditions"] == ["seller.is_company"]
    assert conditional["tokens"] == [
        {
            "kind": "condition_start",
            "name": "seller.is_company",
            "raw": "{{#if seller.is_company}}",
        }
    ]
    first = _block(report, "Старый текст {{ customer.full_name }}")
    assert first["variables"] == ["customer.full_name"]
    assert first["text_sha256"] == sha256(first["original_text"].encode()).hexdigest()
    assert inspect_docx(source) == report
    assert len({block["block_id"] for block in report["blocks"]}) == len(
        report["blocks"]
    )


def test_edits_exact_address_and_preserves_runs_and_unaffected_package_parts():
    source = _complex_docx()
    report = inspect_docx(source)
    selected = _block(report, "Старый текст {{ customer.full_name }}")
    note = _block(report, "Сноска {{ customer.address }}")
    result = apply_docx_edits(
        source,
        [
            _edit(selected, "Новый текст {{ customer.full_name }}"),
            _edit(note, "Примечание {{ customer.address }}"),
        ],
    )
    before, after = _parts(source), _parts(result)
    changed = {part for part in before if before[part] != after[part]}
    assert changed == {"word/document.xml", "word/footnotes.xml"}
    with ZipFile(BytesIO(source)) as old, ZipFile(BytesIO(result)) as new:
        assert new.comment == old.comment
        assert [
            (item.filename, item.compress_type, item.date_time, item.external_attr)
            for item in new.infolist()
        ] == [
            (item.filename, item.compress_type, item.date_time, item.external_attr)
            for item in old.infolist()
        ]
    old_xml, new_xml = (
        etree.fromstring(before["word/document.xml"]),
        etree.fromstring(after["word/document.xml"]),
    )
    assert [etree.tostring(node) for node in old_xml.iter(qn("w:rPr"))] == [
        etree.tostring(node) for node in new_xml.iter(qn("w:rPr"))
    ]
    assert len(list(old_xml.iter(qn("w:r")))) == len(list(new_xml.iter(qn("w:r"))))
    assert (
        _block(inspect_docx(result), "Новый текст {{ customer.full_name }}")["block_id"]
        == selected["block_id"]
    )
    assert apply_docx_edits(source, []) is source
    assert (
        apply_docx_edits(source, [_edit(selected, selected["original_text"])]) is source
    )


def test_identical_paragraph_text_is_not_an_ambiguous_document_wide_search():
    document = Document()
    document.add_paragraph("Одинаковый текст")
    document.add_paragraph("Одинаковый текст")
    source = _save(document)
    blocks = inspect_docx(source)["blocks"]
    result = apply_docx_edits(source, [_edit(blocks[1], "Изменённый текст")])
    assert [block["original_text"] for block in inspect_docx(result)["blocks"]] == [
        "Одинаковый текст",
        "Изменённый текст",
    ]


def test_standard_png_logo_hyperlink_styles_and_numbering_survive_a_point_edit():
    document = Document()
    document.add_paragraph("Старый текст")
    document.add_paragraph("Нумерованный пункт", style="List Number")
    image = b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlWQAAAAASUVORK5CYII="
    )
    document.add_picture(BytesIO(image))
    paragraph = document.add_paragraph("См. ")
    link = OxmlElement("w:hyperlink")
    link.set(
        qn("r:id"),
        document.part.relate_to(
            "https://example.com/terms", RT.HYPERLINK, is_external=True
        ),
    )
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "условия"
    run.append(text)
    link.append(run)
    paragraph._p.append(link)
    source = _save(document)
    report = inspect_docx(source)
    assert report["coverage"] == {
        "complete": True,
        "reasons": [],
        "nontext_assets": 1,
        "requires_visual_review": True,
    }
    selected = _block(report, "Старый текст")
    output = apply_docx_edits(source, [_edit(selected, "Новый текст")])
    before, after = _parts(source), _parts(output)
    assert {part for part in before if before[part] != after[part]} == {
        "word/document.xml"
    }
    for part in (
        "word/styles.xml",
        "word/numbering.xml",
        "word/_rels/document.xml.rels",
        "word/media/image1.png",
    ):
        assert before[part] == after[part]
    old_root = etree.fromstring(before["word/document.xml"])
    new_root = etree.fromstring(after["word/document.xml"])
    for tag in ("w:drawing", "w:hyperlink", "w:pPr"):
        assert [etree.tostring(node) for node in old_root.iter(qn(tag))] == [
            etree.tostring(node) for node in new_root.iter(qn(tag))
        ]
    assert _block(inspect_docx(output), "См. условия")


def test_declared_missing_or_unknown_xml_story_is_incomplete():
    source = _complex_docx()
    parts = _parts(source)
    relationships = etree.fromstring(parts["word/_rels/document.xml.rels"])
    etree.SubElement(
        relationships,
        "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
        Id="rMissing",
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header",
        Target="missing-header.xml",
    )
    source = _package(
        source,
        {
            "word/_rels/document.xml.rels": etree.tostring(relationships),
            "word/unknown.xml": b"<unknown>unparsed material</unknown>",
        },
    )
    report = inspect_docx(source)
    assert report["coverage"]["complete"] is False
    assert {reason["code"] for reason in report["coverage"]["reasons"]} >= {
        "missing_relationship_target",
        "unparsed_part",
    }


@pytest.mark.parametrize(
    "replacement",
    [
        "Старый текст",
        "Старый текст {{ customer.name }}",
        "Старый текст {{customer.full_name}}",
        "Старый текст {{ customer.full_name }} {{ customer.full_name }}",
        "Старый\nтекст {{ customer.full_name }}",
        "Старый\tтекст {{ customer.full_name }}",
    ],
)
def test_rejects_lost_changed_duplicated_tokens_and_new_structural_characters(
    replacement,
):
    source = _complex_docx()
    selected = _block(inspect_docx(source), "Старый текст {{ customer.full_name }}")
    with pytest.raises(DocxAuditError, match="protected"):
        apply_docx_edits(source, [_edit(selected, replacement)])


def test_rejects_condition_marker_reordering_even_with_identical_inventory():
    document = Document()
    document.add_paragraph("{{#if seller.is_company}}Текст{{/if seller.is_company}}")
    source = _save(document)
    block = inspect_docx(source)["blocks"][0]
    with pytest.raises(DocxAuditError, match="protected"):
        apply_docx_edits(
            source,
            [_edit(block, "{{/if seller.is_company}}Текст{{#if seller.is_company}}")],
        )


@pytest.mark.parametrize(
    "mutation,match",
    [
        ({"block_id": "unknown"}, "not found"),
        ({"expected_text": "stale"}, "does not match"),
        ({"replacement_text": None}, "strings"),
        ({"replacement_text": "bad\x00value {{ customer.full_name }}"}, "invalid XML"),
    ],
)
def test_rejects_stale_unknown_or_invalid_edits(mutation, match):
    source = _complex_docx()
    selected = _block(inspect_docx(source), "Старый текст {{ customer.full_name }}")
    edit = _edit(selected, "Новый текст {{ customer.full_name }}") | mutation
    with pytest.raises(DocxAuditError, match=match):
        apply_docx_edits(source, [edit])
    with pytest.raises(DocxAuditError, match="only be edited once"):
        apply_docx_edits(source, [_edit(selected, selected["original_text"])] * 2)


@pytest.mark.parametrize(
    "feature,code",
    [
        ("drawing", "drawing"),
        ("txbxContent", "textbox"),
        ("altChunk", "alt_chunk"),
        ("object", "embedded_object"),
        ("ins", "tracked_changes"),
        ("rPrChange", "tracked_changes"),
        ("dataBinding", "bound_content_control"),
        ("instrText", "field_instruction"),
    ],
)
def test_unsupported_features_explicitly_mark_coverage_incomplete_and_disable_edits(
    feature, code
):
    document = Document()
    paragraph = document.add_paragraph("Текст")
    paragraph._p.append(OxmlElement(f"w:{feature}"))
    source = _save(document)
    report = inspect_docx(source)
    assert report["coverage"]["complete"] is False
    assert code in {reason["code"] for reason in report["coverage"]["reasons"]}
    with pytest.raises(DocxAuditError, match="coverage is incomplete"):
        apply_docx_edits(source, [_edit(_block(report, "Текст"), "Новый текст")])


def test_unparsed_xml_unhandled_story_and_embedded_parts_never_report_complete():
    document = Document()
    document.add_paragraph("Текст")
    source = _package(
        _save(document),
        {
            "word/broken.xml": b"<broken",
            "word/unhandled.xml": f'<w:unknown xmlns:w="{_W}"><w:p><w:r><w:t>Скрыто</w:t></w:r></w:p></w:unknown>'.encode(),
            "word/embeddings/object.bin": b"opaque",
        },
    )
    reasons = inspect_docx(source)["coverage"]["reasons"]
    assert {item["code"] for item in reasons} >= {
        "unparsed_part",
        "unparsed_story",
        "embedded_part",
    }


def test_line_breaks_tabs_and_word_anchors_are_preserved_or_refused():
    document = Document()
    paragraph = document.add_paragraph("Первое")
    paragraph.add_run().add_tab()
    paragraph.add_run("Второе")
    paragraph.add_run().add_break()
    paragraph.add_run("Третье")
    source = _save(document)
    block = inspect_docx(source)["blocks"][0]
    assert block["original_text"] == "Первое\tВторое\nТретье"
    result = apply_docx_edits(source, [_edit(block, "Новое\tВторое\nИное")])
    assert inspect_docx(result)["blocks"][0]["original_text"] == "Новое\tВторое\nИное"
    anchored = Document()
    paragraph = anchored.add_paragraph("abc")
    paragraph._p.append(OxmlElement("w:bookmarkStart"))
    paragraph.add_run("def")
    anchor_source = _save(anchored)
    block = inspect_docx(anchor_source)["blocks"][0]
    with pytest.raises(DocxAuditError, match="anchor"):
        apply_docx_edits(anchor_source, [_edit(block, "XYZ")])


def test_tab_stop_formatting_is_not_a_tab_character_in_the_paragraph_text():
    document = Document()
    paragraph = document.add_paragraph("Старый текст")
    paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(1))
    source = _save(document)
    block = inspect_docx(source)["blocks"][0]
    assert block["original_text"] == "Старый текст"
    output = apply_docx_edits(source, [_edit(block, "Новый текст")])
    assert inspect_docx(output)["blocks"][0]["original_text"] == "Новый текст"
    before = etree.fromstring(_parts(source)["word/document.xml"])
    after = etree.fromstring(_parts(output)["word/document.xml"])
    assert [etree.tostring(node) for node in before.iter(qn("w:pPr"))] == [
        etree.tostring(node) for node in after.iter(qn("w:pPr"))
    ]


def test_long_paragraph_is_not_truncated():
    # Avoid highly compressible artificial fixtures triggering ZIP bomb defense.
    text = " ".join(sha256(str(index).encode()).hexdigest() for index in range(1800))
    document = Document()
    document.add_paragraph(text)
    report = inspect_docx(_save(document))
    assert report["coverage"]["complete"] is True
    assert report["blocks"][0]["original_text"] == text


def test_invalid_zip_duplicate_entries_zip_bomb_and_xml_entities_are_bounded():
    with pytest.raises(DocxAuditError, match="readable"):
        inspect_docx(b"not a zip")
    document = Document()
    document.add_paragraph("Text")
    source = _save(document)
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for part, content in _parts(source).items():
            archive.writestr(part, content)
        with pytest.warns(UserWarning):
            archive.writestr("word/document.xml", b"duplicate")
    with pytest.raises(DocxAuditError, match="duplicate"):
        inspect_docx(output.getvalue())
    bomb = _package(source, {"word/bomb.xml": b"a" * 1_000_000})
    with pytest.raises(DocxAuditError, match="compression ratio"):
        inspect_docx(bomb)
    entity = b'<!DOCTYPE document [<!ENTITY secret SYSTEM "file:///etc/passwd">]><document>&secret;</document>'
    report = inspect_docx(_package(source, {"word/entity.xml": entity}))
    assert report["coverage"]["complete"] is False
    assert any(
        reason["part"] == "word/entity.xml" and reason["code"] == "unparsed_part"
        for reason in report["coverage"]["reasons"]
    )

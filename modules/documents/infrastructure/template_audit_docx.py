"""Loss-aware DOCX text inspection and guarded edits, without rendering a document.

IDs address paragraphs by package part and canonical XML path. Callers bind them
and ``source_sha256`` to an immutable template revision and run the native template
preflight/contract validators before publishing. This codec does not replace them.
Edits require the complete paragraph as ``expected_text``; no substring search is
used. Existing runs, controls, anchors and unrelated package parts are retained.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from io import BytesIO
import posixpath
import re
from urllib.parse import unquote, urlsplit
import zlib
from typing import Mapping, Sequence
from zipfile import BadZipFile, ZipFile, ZipInfo

from lxml import etree


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_MAX_SOURCE = 5 * 1024 * 1024
_MAX_UNCOMPRESSED = 25 * 1024 * 1024
_MAX_ENTRIES = 1_000
_MAX_ELEMENTS = 200_000
_STORIES = {"document", "hdr", "ftr", "footnotes", "endnotes", "comments"}
_IDENTIFIER = r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*"
_VARIABLE = re.compile(rf"{{{{\s*({_IDENTIFIER})\s*}}}}")
_CONDITION = re.compile(rf"{{{{\s*(#if|/if)\s+({_IDENTIFIER})\s*}}}}")
# Unknown and malformed markers are protected as well; validation belongs to the
# native renderer's contract validator, never to the spelling/editing operation.
_TOKEN = re.compile(r"{{.*?}}|{{|}}", re.DOTALL)
_PROTECTED = re.compile(r"{{.*?}}|{{|}}|[\t\n\r\u00ad\u2011]", re.DOTALL)
_CHARACTERS = {
    "tab": "\t",
    "br": "\n",
    "cr": "\n",
    "noBreakHyphen": "\u2011",
    "softHyphen": "\u00ad",
}
_ANCHORS = {
    "bookmarkStart",
    "bookmarkEnd",
    "commentRangeStart",
    "commentRangeEnd",
    "commentReference",
    "footnoteReference",
    "endnoteReference",
    "permStart",
    "permEnd",
}
_UNSUPPORTED = {
    "drawing": "drawing",
    "pict": "drawing",
    "txbxContent": "textbox",
    "altChunk": "alt_chunk",
    "object": "embedded_object",
    "control": "embedded_object",
    "subDoc": "subdocument",
    "contentPart": "embedded_object",
    "dataBinding": "bound_content_control",
    "instrText": "field_instruction",
    "fldSimple": "field_instruction",
    "sym": "symbol",
    "ptab": "positioned_tab",
    "delText": "tracked_changes",
    "delInstrText": "tracked_changes",
    "ins": "tracked_changes",
    "del": "tracked_changes",
    "moveFrom": "tracked_changes",
    "moveTo": "tracked_changes",
    "moveFromRangeStart": "tracked_changes",
    "moveToRangeStart": "tracked_changes",
    "moveFromRangeEnd": "tracked_changes",
    "moveToRangeEnd": "tracked_changes",
}


class DocxAuditError(ValueError):
    """A document or edit cannot be processed safely; safe for an editor UI."""


@dataclass
class _Block:
    part: str
    paragraph: etree._Element
    text: str
    nodes: list[tuple[etree._Element, int, int]]
    anchors: set[int]
    public: dict[str, object]


@dataclass
class _Package:
    entries: list[tuple[ZipInfo, bytes]]
    roots: dict[str, etree._Element]
    blocks: dict[str, _Block]
    report: dict[str, object]
    comment: bytes


def inspect_docx(source: bytes) -> dict[str, object]:
    """Inspect every Word story, including nested controls/tables and annotations.

    ``coverage.complete`` means all story text is represented, not that native
    placeholders or legal content are valid. Unsupported features are explicit
    reasons for incomplete coverage. No paragraph text is truncated or chunked.
    """
    return _inspect(source).report


def apply_docx_edits(source: bytes, edits: Sequence[Mapping[str, object]]) -> bytes:
    """Apply exact, complete-paragraph replacements while retaining Word XML.

    Each edit has ``block_id``, ``expected_text`` and ``replacement_text`` strings.
    Tokens (including condition/table markers) must retain their exact spelling,
    multiplicity and order. New paragraphs, tabs, breaks, and edits across Word
    anchors are refused. Any incomplete source coverage refuses all edits.
    """
    package = _inspect(source)
    if not package.report["coverage"]["complete"]:
        raise DocxAuditError("DOCX audit coverage is incomplete; edits are disabled")
    if not isinstance(edits, (list, tuple)):
        raise DocxAuditError("DOCX edits must be a list")
    planned: list[tuple[_Block, str]] = []
    seen: set[str] = set()
    for edit in edits:
        if not isinstance(edit, Mapping):
            raise DocxAuditError("Each DOCX edit must be an object")
        block_id, expected, replacement = (
            edit.get(key) for key in ("block_id", "expected_text", "replacement_text")
        )
        if not all(
            isinstance(value, str) for value in (block_id, expected, replacement)
        ):
            raise DocxAuditError(
                "DOCX edits require block_id, expected_text and replacement_text strings"
            )
        if block_id in seen:
            raise DocxAuditError("A DOCX block may only be edited once")
        seen.add(block_id)
        block = package.blocks.get(block_id)
        if block is None:
            raise DocxAuditError("DOCX edit block was not found")
        if expected != block.text:
            raise DocxAuditError(
                "DOCX expected_text does not match the immutable source block"
            )
        if _PROTECTED.findall(expected) != _PROTECTED.findall(replacement):
            raise DocxAuditError(
                "DOCX edit changes protected template tokens or structural characters"
            )
        if re.search(
            r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", replacement
        ):
            raise DocxAuditError("DOCX edit contains invalid XML characters")
        planned.append((block, replacement))

    changed: set[str] = set()
    for block, replacement in planned:
        if replacement != block.text:
            _replace(block, replacement)
            changed.add(block.part)
    if not changed:
        return source
    output = BytesIO()
    try:
        with ZipFile(output, "w") as archive:
            archive.comment = package.comment
            for info, content in package.entries:
                if info.filename in changed:
                    content = etree.tostring(
                        package.roots[info.filename],
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    )
                archive.writestr(info, content)
    except (ValueError, TypeError, etree.LxmlError) as exc:
        raise DocxAuditError("DOCX edit cannot be encoded safely") from exc
    return output.getvalue()


def _inspect(source: bytes) -> _Package:
    entries, comment = _read_package(source)
    roots: dict[str, etree._Element] = {}
    blocks: dict[str, _Block] = {}
    reasons: list[dict[str, str]] = []
    reason_keys: set[tuple[str, str, str]] = set()

    def reason(code: str, part: str, location: str = "") -> None:
        key = (code, part, location)
        if key not in reason_keys:
            reason_keys.add(key)
            reasons.append(
                {
                    "code": code,
                    "part": part,
                    "location": location,
                    "message": f"Unsupported or unreadable DOCX content: {code}",
                }
            )

    total_elements = 0
    nontext_assets = 0
    content_types: dict[str, str] = {}
    default_types: dict[str, str] = {}
    names = {info.filename for info, _ in entries}
    for info, content in entries:
        if info.filename == "[Content_Types].xml":
            try:
                types = _parse_xml(content)
                if (
                    types.tag
                    != "{http://schemas.openxmlformats.org/package/2006/content-types}Types"
                ):
                    reason("unparsed_part", info.filename)
                default_types = {
                    node.get("Extension", ""): node.get("ContentType", "")
                    for node in types
                    if _local(node) == "Default"
                }
                content_types = {
                    node.get("PartName", "").lstrip("/"): node.get("ContentType", "")
                    for node in types
                    if _local(node) == "Override"
                }
            except (etree.LxmlError, DocxAuditError):
                reason("unparsed_part", info.filename)
    for info, content in sorted(entries, key=lambda item: item[0].filename):
        part = info.filename
        if (
            "/embeddings/" in part
            or "/activeX/" in part
            or part.endswith(("vbaProject.bin", ".docm"))
        ):
            reason("embedded_part", part)
        mime = content_types.get(part, default_types.get(part.rsplit(".", 1)[-1], ""))
        if not (part.endswith((".xml", ".rels")) or mime.endswith(("+xml", "/xml"))):
            if (
                "wordprocessingml" in mime
                or mime.startswith("text/")
                or mime == "application/rtf"
            ):
                reason("unparsed_part", part)
            continue
        try:
            root = _parse_xml(content)
        except (etree.LxmlError, DocxAuditError):
            reason("unparsed_part", part)
            continue
        if part.endswith(".rels"):
            base = posixpath.dirname(posixpath.dirname(part))
            for relationship in root:
                if relationship.get("TargetMode") == "External":
                    continue
                try:
                    target = urlsplit(relationship.get("Target", "")).path
                except ValueError:
                    reason("invalid_relationship_target", part)
                    continue
                if not target:
                    continue
                target = unquote(target)
                resolved = posixpath.normpath(
                    target.lstrip("/")
                    if target.startswith("/")
                    else posixpath.join(base, target)
                )
                if resolved not in names:
                    reason("missing_relationship_target", part, resolved)
        total_elements += sum(1 for _ in root.iter())
        if total_elements > _MAX_ELEMENTS:
            raise DocxAuditError("DOCX contains too many XML elements")
        namespace, local = _name(root)
        is_story = namespace == _W and local in _STORIES
        if part == "word/document.xml" and not (
            namespace == _W and local == "document"
        ):
            reason("unparsed_part", part)
        if (
            "wordprocessingml" in mime
            and mime.endswith(
                (
                    "document.main+xml",
                    "header+xml",
                    "footer+xml",
                    "footnotes+xml",
                    "endnotes+xml",
                    "comments+xml",
                )
            )
            and not is_story
        ):
            reason("unparsed_part", part)
        if is_story:
            roots[part] = root
            if local == "document" and root.find(f"{{{_W}}}body") is None:
                reason("unparsed_part", part)
        elif part.startswith("word/") and not part.endswith(".rels"):
            known_metadata = (
                namespace == _W
                and local in {"styles", "settings", "fonts", "numbering", "webSettings"}
            ) or (namespace == _A and local in {"theme", "themeOverride"})
            if not known_metadata:
                reason("unparsed_part", part)
        paths = _paths(root)
        accounted: set[etree._Element] = set()
        for node in root.iter():
            ns, name = _name(node)
            if ns == _W:
                if name == "drawing" and _is_picture_only(node):
                    nontext_assets += 1
                elif (
                    name in _UNSUPPORTED
                    or name.endswith("PrChange")
                    or name in {"cellIns", "cellDel", "cellMerge", "numberingChange"}
                ):
                    reason(_UNSUPPORTED.get(name, "tracked_changes"), part, paths[node])
                if name in {"p", "t"} and not is_story:
                    reason("unparsed_story", part, paths[node])
            elif ns == _MC and name == "AlternateContent":
                reason("alternate_content", part, paths[node])
            elif name == "t" and ns not in {"", _W}:
                reason("unparsed_text", part, paths[node])
            if is_story and ns == _W and name == "p":
                block = _paragraph(part, node, paths)
                block_id = block.public["block_id"]
                blocks[block_id] = block
                accounted.update(text_node for text_node, _, _ in block.nodes)
        if is_story:
            for node in root.iter(f"{{{_W}}}t"):
                if node not in accounted:
                    reason("unparsed_text", part, paths[node])
    report = {
        "source_sha256": sha256(source).hexdigest(),
        "blocks": [block.public for block in blocks.values()],
        "coverage": {
            "complete": not reasons,
            "reasons": reasons,
            "nontext_assets": nontext_assets,
            "requires_visual_review": bool(nontext_assets),
        },
    }
    return _Package(entries, roots, blocks, report, comment)


def _paragraph(part: str, paragraph: etree._Element, paths: dict) -> _Block:
    text: list[str] = []
    nodes: list[tuple[etree._Element, int, int]] = []
    anchors: set[int] = set()
    inline_ranges: dict[etree._Element, list[int]] = {}
    position = 0
    for node in paragraph.iter():
        # Textboxes can contain paragraphs inside paragraphs. Represent their
        # text exactly once; their unsupported coverage still disables editing.
        if (
            node is not paragraph
            and next(node.iterancestors(f"{{{_W}}}p"), None) is not paragraph
        ):
            continue
        ns, name = _name(node)
        if ns != _W:
            continue
        # w:pPr/w:tabs/w:tab defines a tab stop, not a text character. Only
        # run children carry the Word text/break characters represented here.
        if name in {"t", *_CHARACTERS} and _name(node.getparent()) != (_W, "r"):
            continue
        value = node.text or "" if name == "t" else _CHARACTERS.get(name, "")
        if name == "t":
            nodes.append((node, position, position + len(value)))
        if name == "t" or name in _CHARACTERS:
            for ancestor in node.iterancestors():
                if ancestor is paragraph:
                    break
                if _name(ancestor) in {(_W, "sdt"), (_W, "hyperlink")}:
                    inline_ranges.setdefault(ancestor, []).extend(
                        (position, position + len(value))
                    )
        elif name in _ANCHORS or name in {"fldChar", "sdt", "hyperlink", "drawing"}:
            anchors.add(position)
        text.append(value)
        position += len(value)
    for positions in inline_ranges.values():
        anchors.update((min(positions), max(positions)))
    original = "".join(text)
    location = paths[paragraph]
    raw_tokens = _TOKEN.findall(original)
    tokens = []
    for raw in raw_tokens:
        variable, condition = _VARIABLE.fullmatch(raw), _CONDITION.fullmatch(raw)
        tokens.append(
            {
                "raw": raw,
                "kind": "variable"
                if variable
                else "condition_start"
                if condition and condition.group(1) == "#if"
                else "condition_end"
                if condition
                else "opaque",
                "name": variable.group(1)
                if variable
                else condition.group(2)
                if condition
                else None,
            }
        )
    context = [
        {"kind": _local(node), "location": paths.get(node, "")}
        for node in reversed(list(paragraph.iterancestors()))
        if _name(node)[0] == _W
        and _local(node)
        in {
            "sdt",
            "tbl",
            "tr",
            "tc",
            "footnote",
            "endnote",
            "comment",
            "hdr",
            "ftr",
            "body",
        }
    ]
    public = {
        "block_id": "docx:" + sha256(f"{part}\0{location}".encode()).hexdigest(),
        "part": part,
        "location": location,
        "kind": "paragraph",
        "context": context,
        "original_text": original,
        "text_sha256": sha256(original.encode()).hexdigest(),
        "variables": sorted(
            {token["name"] for token in tokens if token["kind"] == "variable"}
        ),
        "conditions": sorted(
            {
                token["name"]
                for token in tokens
                if token["kind"].startswith("condition_")
            }
        ),
        "tokens": tokens,
        "token_inventory": dict(Counter(raw_tokens)),
    }
    return _Block(part, paragraph, original, nodes, anchors, public)


def _is_picture_only(drawing: etree._Element) -> bool:
    """Recognize standard raster picture markup without overlooking text boxes.

    The bitmap is retained byte-for-byte, never OCRed. Text inside an image needs
    visual review, reported separately from coverage of editable Word stories.
    """
    graphics = list(drawing.iter(f"{{{_A}}}graphicData"))
    pictures = list(drawing.iter(f"{{{_PIC}}}pic"))
    blips = list(drawing.iter(f"{{{_A}}}blip"))
    if len(graphics) != 1 or len(pictures) != 1 or not blips:
        return False
    if graphics[0].get("uri") != _PIC or list(graphics[0]) != pictures:
        return False
    if not all(node.get(f"{{{_R}}}embed") for node in blips):
        return False
    for node in drawing.iter():
        ns, name = _name(node)
        if node is drawing:
            continue
        if ns not in {_A, _PIC, _WP}:
            # A common Word image extension only stores a DPI preference.
            if not (
                ns == "http://schemas.microsoft.com/office/drawing/2010/main"
                and name == "useLocalDpi"
            ):
                return False
        if name in {"t", "txBody", "txSp", "txbx", "txbxContent"}:
            return False
        if (
            node.text
            and node.text.strip()
            and not (ns == _WP and name in {"align", "posOffset"})
        ):
            return False
    return True


def _replace(block: _Block, replacement: str) -> None:
    # Match between protected spans independently, so repeated placeholders are
    # never swallowed by a text-difference heuristic or moved across runs.
    old_matches, new_matches = (
        list(_PROTECTED.finditer(block.text)),
        list(_PROTECTED.finditer(replacement)),
    )
    changes: list[tuple[int, int, str]] = []
    old_start = new_start = 0
    for old_end, new_end, old_next, new_next in [
        (old.start(), new.start(), old.end(), new.end())
        for old, new in zip(old_matches, new_matches)
    ] + [(len(block.text), len(replacement), len(block.text), len(replacement))]:
        old_segment, new_segment = (
            block.text[old_start:old_end],
            replacement[new_start:new_end],
        )
        if old_segment != new_segment:
            # Keep diff work bounded for a very long paragraph. Its complete text
            # is still inspected; a large edit uses one safe replacement span.
            if len(old_segment) + len(new_segment) <= 20_000:
                opcodes = SequenceMatcher(
                    None, old_segment, new_segment, autojunk=True
                ).get_opcodes()
                changes.extend(
                    (old_start + a, old_start + b, new_segment[c:d])
                    for kind, a, b, c, d in opcodes
                    if kind != "equal"
                )
            else:
                prefix = 0
                while (
                    prefix < min(len(old_segment), len(new_segment))
                    and old_segment[prefix] == new_segment[prefix]
                ):
                    prefix += 1
                suffix = 0
                while (
                    suffix < min(len(old_segment), len(new_segment)) - prefix
                    and old_segment[-1 - suffix] == new_segment[-1 - suffix]
                ):
                    suffix += 1
                changes.append(
                    (
                        old_start + prefix,
                        old_end - suffix,
                        new_segment[
                            prefix : len(new_segment) - suffix if suffix else None
                        ],
                    )
                )
        old_start, new_start = old_next, new_next
    for start, end, value in reversed(changes):
        if any(start < position < end for position in block.anchors):
            raise DocxAuditError("DOCX edit crosses a Word anchor or content boundary")
        overlapping = [
            (node, a, b) for node, a, b in block.nodes if a < end and b > start
        ]
        if start == end:
            overlapping = [item for item in block.nodes if item[1] <= start < item[2]]
            if not overlapping:
                overlapping = [item for item in block.nodes if item[2] == start][-1:]
        if not overlapping:
            raise DocxAuditError("DOCX edit has no unambiguous editable text node")
        first = True
        for node, a, b in overlapping:
            current = node.text or ""
            left, right = max(0, start - a), min(b - a, end - a)
            node.text = current[:left] + (value if first else "") + current[right:]
            if node.text.startswith(" ") or node.text.endswith(" "):
                node.set(_XML_SPACE, "preserve")
            first = False
    if (
        _paragraph(block.part, block.paragraph, {block.paragraph: ""}).text
        != replacement
    ):
        raise DocxAuditError("DOCX edit cannot preserve the original text structure")


def _read_package(source: bytes) -> tuple[list[tuple[ZipInfo, bytes]], bytes]:
    # Local parser bounds are intentional even when the caller already ran the
    # native upload preflight. Never extract untrusted package paths to disk.
    if not isinstance(source, bytes) or not source or len(source) > _MAX_SOURCE:
        raise DocxAuditError("DOCX source is empty or exceeds the audit size limit")
    try:
        with ZipFile(BytesIO(source)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > _MAX_ENTRIES or len(names) != len(set(names)):
                raise DocxAuditError("DOCX has too many or duplicate package entries")
            if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                raise DocxAuditError("Source is not a DOCX package")
            if sum(info.file_size for info in infos) > _MAX_UNCOMPRESSED:
                raise DocxAuditError("DOCX exceeds the uncompressed audit size limit")
            entries = []
            for info in infos:
                path = info.filename.replace("\\", "/")
                if (
                    path.startswith("/")
                    or re.match(r"^[a-zA-Z]:", path)
                    or ".." in path.split("/")
                    or "\x00" in path
                    or info.flag_bits & 1
                ):
                    raise DocxAuditError("DOCX has unsafe or encrypted package entries")
                if info.file_size and (
                    not info.compress_size or info.file_size > info.compress_size * 100
                ):
                    raise DocxAuditError("DOCX has an unsafe compression ratio")
                with archive.open(info) as member:
                    content = member.read(
                        min(info.file_size + 1, _MAX_UNCOMPRESSED + 1)
                    )
                if len(content) != info.file_size:
                    raise DocxAuditError("DOCX package size is inconsistent")
                entries.append((info, content))
            return entries, archive.comment
    except (
        BadZipFile,
        RuntimeError,
        NotImplementedError,
        OSError,
        EOFError,
        zlib.error,
    ) as exc:
        raise DocxAuditError("Source is not a readable DOCX package") from exc


def _parse_xml(content: bytes) -> etree._Element:
    parser = etree.XMLPullParser(
        events=("start",),
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
        huge_tree=False,
    )
    element_count = 0
    for offset in range(0, len(content), 65_536):
        parser.feed(content[offset : offset + 65_536])
        for _event, _node in parser.read_events():
            element_count += 1
            if element_count > _MAX_ELEMENTS:
                raise DocxAuditError("DOCX contains too many XML elements")
    root = parser.close()
    if root.getroottree().docinfo.doctype or any(
        isinstance(node, etree._Entity) for node in root.iter()
    ):
        raise DocxAuditError("XML document types and entities are unsupported")
    return root


def _name(node: etree._Element) -> tuple[str, str]:
    if not isinstance(node.tag, str):
        return "", ""
    name = etree.QName(node)
    return name.namespace or "", name.localname


def _local(node: etree._Element) -> str:
    return _name(node)[1]


def _paths(root: etree._Element) -> dict[etree._Element, str]:
    def label(node):
        ns, name = _name(node)
        return f"w:{name}" if ns == _W else f"{{{ns}}}{name}" if ns else name

    paths = {root: f"/{label(root)}[1]"}
    for parent in root.iter():
        counters: Counter[str] = Counter()
        for child in parent:
            counters[child.tag] += 1
            paths[child] = f"{paths[parent]}/{label(child)}[{counters[child.tag]}]"
    return paths

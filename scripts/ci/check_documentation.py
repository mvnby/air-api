#!/usr/bin/env python3
"""Check changed Markdown links and basic formatting without network access."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


RUNBOOK_CONTRACT = (
    "helper is the source of truth for the host-local promotion mechanics",
    "cp docker-compose.primary.yml docker-compose.reserve.yml",
    "docker-compose.reserve.yml.pre-promote.$(date -u +%Y%m%d%H%M%S)",
)
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
FENCE_CLOSE = re.compile(r"^ {0,3}(`+|~+)[ \t]*$")
HTML_COMMENT = re.compile(r"<!--|-->")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)")
REFERENCE_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(\S+)")
REFERENCE_USE = re.compile(r"!?\[[^\]]*\]\[([^\]]*)\]")
HTML_ANCHOR = re.compile(r"<a\s+(?:[^>]*?\s)?(?:id|name)=['\"]([^'\"]+)['\"]", re.I)


def slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"!?(\[([^]]+)\])(?:\([^)]*\))?", r"\2", text)
    text = text.replace("`", "")
    text = text.lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text.strip())


def markdown_facts(text: str) -> tuple[set[str], dict[str, str], list[str], list[str]]:
    anchors: set[str] = set()
    references: dict[str, str] = {}
    errors: list[str] = []
    counts: dict[str, int] = {}
    lines = text.splitlines()
    active_fence: tuple[str, int] | None = None
    in_comment = False
    clean: list[str] = []
    for number, line in enumerate(lines, 1):
        if active_fence:
            clean.append("")
            closing = FENCE_CLOSE.match(line)
            if (
                closing
                and closing.group(1)[0] == active_fence[0]
                and len(closing.group(1)) >= active_fence[1]
            ):
                active_fence = None
            continue
        visible: list[str] = []
        cursor = 0
        for comment in HTML_COMMENT.finditer(line):
            if in_comment:
                if comment.group() == "-->":
                    in_comment = False
                    cursor = comment.end()
                continue
            if comment.group() == "<!--":
                visible.append(line[cursor:comment.start()])
                in_comment = True
                cursor = comment.end()
        if not in_comment:
            visible.append(line[cursor:])
        line = "".join(visible)
        if in_comment and not line:
            clean.append("")
            continue
        marker = FENCE.match(line)
        if marker:
            active_fence = (marker.group(1)[0], len(marker.group(1)))
            clean.append("")
            continue
        definition = REFERENCE_DEF.match(line)
        if definition:
            references[definition.group(1).strip().lower()] = definition.group(2).strip("<>")
            clean.append("")
            continue
        heading = HEADING.match(line)
        if heading:
            base = slug(heading.group(1))
            count = counts.get(base, 0)
            counts[base] = count + 1
            anchors.add(base if count == 0 else f"{base}-{count}")
        anchors.update(HTML_ANCHOR.findall(line))
        clean.append(line)
        trailing = re.search(r"([ \t]+)$", line)
        if trailing and ("\t" in trailing.group(1) or len(trailing.group(1)) == 1):
            errors.append(f"line {number}: trailing whitespace")
        if "\t" in line:
            errors.append(f"line {number}: tab character")
    if active_fence:
        errors.append("unclosed fenced code block")
    if text and not text.endswith("\n"):
        errors.append("missing final newline")
    return anchors, references, errors, clean


def links(text: str, references: dict[str, str], clean_lines: list[str]) -> tuple[list[tuple[int, str]], list[str]]:
    found: list[tuple[int, str]] = []
    errors: list[str] = []
    declared = set(references)
    for line_no, line in enumerate(clean_lines, 1):
        line = re.sub(r"`+[^`]*`+", "", line)
        for match in INLINE_LINK.finditer(line):
            found.append((line_no, match.group(1).strip("<>")))
        for match in REFERENCE_USE.finditer(line):
            label = (match.group(1) or match.group(0)[1:match.group(0).find("]")]).strip().lower()
            if label not in declared:
                errors.append(f"line {line_no}: unresolved reference link [{label}]")
            else:
                found.append((line_no, references[label]))
    return found, errors


def check_file(root: Path, relative: str) -> list[str]:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or not relative.lower().endswith(".md"):
        return [f"{relative}: unsafe or non-Markdown path"]
    path = root.joinpath(*posix.parts)
    try:
        path.resolve(strict=True).relative_to(root.resolve())
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        return [f"{relative}: cannot read changed Markdown ({exc})"]
    anchors, refs, errors, clean = markdown_facts(text)
    found_links, link_errors = links(text, refs, clean)
    errors.extend(link_errors)
    if relative == "docs/api-ha-runbook.md":
        errors.extend(f"missing required runbook wording: {required}" for required in RUNBOOK_CONTRACT if required not in text)
    for line_no, href in found_links:
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or href.startswith("//"):
            continue
        target_text = unquote(parsed.path)
        if target_text.startswith("/"):
            target_text = target_text.lstrip("/")
            target = (root / target_text).resolve()
        else:
            target = (path.parent / target_text).resolve() if target_text else path.resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            errors.append(f"line {line_no}: link escapes repository: {href}")
            continue
        if not target.exists():
            errors.append(f"line {line_no}: link target does not exist: {href}")
            continue
        if parsed.fragment:
            if target.is_dir():
                errors.append(f"line {line_no}: fragment link target is a directory: {href}")
                continue
            if target.suffix.lower() in {".md", ".markdown"}:
                try:
                    target_text_content = target.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    errors.append(f"line {line_no}: cannot read fragment target: {href}")
                    continue
                target_anchors, _, _, _ = markdown_facts(target_text_content)
                if unquote(parsed.fragment) not in target_anchors:
                    errors.append(f"line {line_no}: heading anchor does not exist: {href}")
    return [f"{relative}: {error}" for error in errors]


def check_changes(root: Path, data: dict) -> tuple[list[str], list[str]]:
    if (
        not isinstance(data, dict)
        or data.get("schema") != 1
        or not isinstance(data.get("markdown_paths"), list)
        or not isinstance(data.get("changes"), list)
    ):
        return [], ["invalid change-scope JSON schema"]
    paths = sorted(set(p for p in data["markdown_paths"] if isinstance(p, str)))
    deleted = {
        change["path"] for change in data["changes"]
        if isinstance(change, dict) and change.get("status") == "D" and isinstance(change.get("path"), str)
    }
    checked = [p for p in paths if p not in deleted]
    errors = [error for path in checked for error in check_file(root, path)]
    return checked, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changes-json", required=True)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.changes_json).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"documentation check failed: cannot load change list: {exc}", file=sys.stderr)
        return 2
    checked, errors = check_changes(Path.cwd(), data)
    for path in checked:
        print(f"checked {path}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not checked and not errors:
        print("no changed Markdown files to check")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

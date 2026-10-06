#!/usr/bin/env python3
"""Classify a Git diff for the lightweight documentation CI route."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import PurePosixPath
from pathlib import Path
from typing import Any


ROOT_MARKDOWN = {
    "AGENTS.md",
    "README.md",
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
}
ZERO_SHA = re.compile(r"^0+$")


def git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or f"git {' '.join(args[:2])} failed")
    return result.stdout


def resolve_commit(revision: str | None) -> str:
    if not revision or ZERO_SHA.fullmatch(revision):
        raise ValueError("missing or zero revision")
    resolved = git("rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}")
    return resolved.decode("ascii").strip()


def parse_name_status(data: bytes) -> list[tuple[str, str]]:
    fields = data.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    result: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        status = fields[i].decode("ascii", errors="strict")
        i += 1
        if status not in {"A", "M", "D", "T"}:
            raise ValueError(f"unexpected diff status {status!r}")
        if i >= len(fields):
            raise ValueError("truncated name-status diff")
        path = fields[i].decode("utf-8", errors="surrogateescape")
        i += 1
        result.append((status, path))
    return result


def tree_mode(revision: str, path: str) -> str | None:
    raw = git("ls-tree", "-z", revision, "--", f":(literal){path}")
    if not raw:
        return None
    entry = raw.rstrip(b"\0").split(b"\t", 1)[0]
    return entry.split(b" ", 1)[0].decode("ascii")


def is_repo_markdown(path: str) -> bool:
    relative = PurePosixPath(path)
    return (
        not relative.is_absolute()
        and "." not in relative.parts
        and ".." not in relative.parts
        and path.lower().endswith(".md")
    )


def is_markdown_path(path: str) -> bool:
    return is_repo_markdown(path) and (path in ROOT_MARKDOWN or path.startswith("docs/"))


def inspect_changes(base: str, head: str, merge_base: bool = False) -> dict[str, Any]:
    try:
        resolved_base = resolve_commit(base)
        resolved_head = resolve_commit(head)
        if merge_base:
            resolved_base = git("merge-base", resolved_base, resolved_head).decode("ascii").strip()
        entries = parse_name_status(
            git("diff", "--name-status", "--no-renames", "-z", resolved_base, resolved_head, "--")
        )
        if not entries:
            return {
                "schema": 1, "base": resolved_base, "head": resolved_head,
                "docs_only": False, "reason": "empty diff", "changes": [], "markdown_paths": [],
            }
        markdown_paths = sorted({path for _, path in entries if is_repo_markdown(path)})
        docs_only = True
        reason = "all changes are allowlisted Markdown files"
        for status, path in entries:
            if status not in {"A", "M"}:
                docs_only, reason = False, f"status {status} requires full CI"
                break
            if not is_markdown_path(path):
                docs_only, reason = False, "changed path is outside the Markdown allowlist"
                break
            if tree_mode(resolved_head, path) != "100644":
                docs_only, reason = False, "changed Markdown path is not a regular non-executable file"
                break
            if status == "M" and tree_mode(resolved_base, path) != "100644":
                docs_only, reason = False, "base Markdown path was not a regular non-executable file"
                break
        return {
            "schema": 1, "base": resolved_base, "head": resolved_head,
            "docs_only": docs_only, "reason": reason,
            "changes": [{"status": status, "path": path} for status, path in entries],
            "markdown_paths": markdown_paths,
        }
    except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
        return {
            "schema": 1, "base": None, "head": None, "docs_only": False,
            "reason": f"classification unavailable: {exc}", "changes": [], "markdown_paths": [],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--merge-base", action="store_true")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--github-output")
    args = parser.parse_args()
    result = inspect_changes(args.base, args.head, args.merge_base)
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as stream:
            stream.write(f"docs_only={'true' if result['docs_only'] else 'false'}\n")
    print(json.dumps({key: result[key] for key in ("docs_only", "reason")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

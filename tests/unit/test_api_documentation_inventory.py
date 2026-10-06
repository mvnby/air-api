"""Protect the reviewed HTTP inventory and links without asserting prose wording."""

import inspect
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from fastapi.routing import APIRoute

from main import app
from scripts.ci.check_documentation import markdown_facts


ROOT = Path(__file__).resolve().parents[2]
DOC_BASE = "https://github.com/mvnby/air-api/blob/main/"


def test_http_documentation_inventory_matches_routes_and_preserves_descriptions():
    inventory = json.loads((ROOT / "docs/api/operation-inventory.json").read_text())
    expected = {}
    for source, rows in inventory["operations"].items():
        for operation, operation_id, described_before, reviewed in rows:
            assert operation not in expected, f"Duplicate inventory operation: {operation}"
            expected[operation] = (source, operation_id, described_before or reviewed)

    schema = app.openapi()
    actual = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        if not route.path.startswith(("/api/", "/.well-known/oauth")):
            continue
        source = str(Path(inspect.getsourcefile(route.endpoint)).relative_to(ROOT))
        for method in route.methods:
            operation = f"{method} {route.path}"
            assert operation not in actual, f"Duplicate HTTP operation: {operation}"
            metadata = schema["paths"][route.path][method.lower()]
            actual[operation] = (source, metadata["operationId"])
            if operation in expected and expected[operation][2]:
                assert metadata.get("description", "").strip(), (
                    f"Description lost: {operation}; update route documentation"
                )

    assert actual == {key: value[:2] for key, value in expected.items()}, (
        "HTTP inventory drift: review added/removed routes and operation IDs, "
        "then update docs/api/operation-inventory.json and documentation-coverage.md"
    )


def test_openapi_documentation_links_resolve_in_the_repository():
    schema = app.openapi()
    prose = [schema["info"].get("description", "")]
    prose.extend(
        operation.get("description", "")
        for methods in schema["paths"].values()
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete", "head", "options"}
    )
    for description in prose:
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", description):
            if not target.startswith(DOC_BASE):
                continue
            parsed = urlsplit(target[len(DOC_BASE):])
            path = ROOT / unquote(parsed.path)
            assert path.is_file(), f"Broken OpenAPI documentation link: {target}"
            if parsed.fragment:
                anchors, _, _, _ = markdown_facts(path.read_text())
                assert unquote(parsed.fragment) in anchors, (
                    f"Broken OpenAPI documentation anchor: {target}"
                )

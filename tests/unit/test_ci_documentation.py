import json
from pathlib import Path

from scripts.ci.check_documentation import check_changes, markdown_facts


def test_checks_relative_links_anchors_references_and_formatting(tmp_path):
    (tmp_path / "guide.md").write_text("# Start\n\n## Detail\n")
    target = tmp_path / "changed.md"
    target.write_text(
        "# Intro\n\n[detail](guide.md#detail) and [guide][g].\n\n[g]: guide.md\n"
    )
    checked, errors = check_changes(
        tmp_path,
        {"schema": 1, "markdown_paths": ["changed.md"], "changes": [{"status": "M", "path": "changed.md"}]},
    )
    assert checked == ["changed.md"]
    assert errors == []

    target.write_text("# Intro \n\n[missing](absent.md)\n[bad][nope]\n")
    _, errors = check_changes(
        tmp_path,
        {"schema": 1, "markdown_paths": ["changed.md"], "changes": [{"status": "M", "path": "changed.md"}]},
    )
    assert any("trailing whitespace" in error for error in errors)
    assert any("link target does not exist" in error for error in errors)
    assert any("unresolved reference" in error for error in errors)


def test_ignores_fenced_code_and_external_links_without_network(tmp_path):
    target = tmp_path / "doc.md"
    target.write_text(
        "# Heading\n\n```md\n```python\n[broken](missing.md)\n```\n"
        "<!-- [comment](missing.md) with trailing space -->   \n\n[web](https://example.com)\n"
    )
    _, errors = check_changes(
        tmp_path,
        {"schema": 1, "markdown_paths": ["doc.md"], "changes": [{"status": "M", "path": "doc.md"}]},
    )
    assert errors == []


def test_two_space_markdown_hard_break_is_valid():
    text = "First line  \nSecond line\n"
    _, _, errors, _ = markdown_facts(text)
    assert errors == []


def test_preserves_ha_runbook_wording_contract(tmp_path):
    relative = "docs/api-ha-runbook.md"
    path = tmp_path / relative
    path.parent.mkdir()
    path.write_text("# Emergency\n")
    _, errors = check_changes(
        tmp_path,
        {"schema": 1, "markdown_paths": [relative], "changes": [{"status": "M", "path": relative}]},
    )
    assert sum("missing required runbook wording" in error for error in errors) == 3


def test_deleted_markdown_is_not_read_and_invalid_schema_fails(tmp_path):
    checked, errors = check_changes(
        tmp_path,
        {"schema": 1, "markdown_paths": ["docs/gone.md"], "changes": [{"status": "D", "path": "docs/gone.md"}]},
    )
    assert checked == []
    assert errors == []
    assert check_changes(tmp_path, json.loads("{}"))[1] == ["invalid change-scope JSON schema"]


def test_fence_and_heading_slug_rules():
    anchors, _, errors, _ = markdown_facts("# Same\n# Same\n```\n")
    assert anchors == {"same", "same-1"}
    assert errors == ["unclosed fenced code block"]

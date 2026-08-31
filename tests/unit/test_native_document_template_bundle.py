import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.manage_native_document_template_bundle import BundleError, load_bundle


def test_bundle_cli_is_directly_executable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/manage_native_document_template_bundle.py",
            "--help",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Plan or idempotently apply" in result.stdout


def _manifest(**overrides):
    template = {
        "key": "contract-supply",
        "name": "Договор поставки",
        "aliases": ["Старое название"],
        "doc_type": "contract",
        "contract_scenario": "supply",
        "source_filename": "supply.docx",
        "sha256": "a" * 64,
        "sort_order": 10,
    }
    template.update(overrides.pop("template", {}))
    return {
        "bundle_id": "test-v1",
        "templates": [template],
        **overrides,
    }


def test_bundle_manifest_parses_use_case_and_safe_source(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")

    bundle = load_bundle(path)

    assert bundle.bundle_id == "test-v1"
    assert bundle.templates[0].contract_scenario == "supply"
    assert bundle.templates[0].source_filename == "supply.docx"


@pytest.mark.parametrize(
    "template",
    (
        {"source_filename": "../supply.docx"},
        {"doc_type": "act", "contract_scenario": "supply"},
        {"sha256": "not-a-digest"},
    ),
)
def test_bundle_manifest_rejects_unsafe_or_mismatched_entries(
    tmp_path: Path,
    template: dict,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest(template=template)), encoding="utf-8")

    with pytest.raises(BundleError):
        load_bundle(path)

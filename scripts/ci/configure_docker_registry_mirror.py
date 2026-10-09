"""Add Google's Docker Hub cache to an ephemeral runner without replacing options."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MIRROR = "https://mirror.gcr.io"


def configure(path: Path) -> None:
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError("Docker daemon configuration must be an object")
    mirrors = data.get("registry-mirrors", [])
    if not isinstance(mirrors, list) or any(not isinstance(item, str) for item in mirrors):
        raise ValueError("registry-mirrors must be a list of strings")
    data["registry-mirrors"] = [MIRROR, *(item for item in mirrors if item != MIRROR)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("daemon_config", type=Path)
    configure(parser.parse_args().daemon_config)
    print("Docker Hub cache configured; existing daemon options preserved")

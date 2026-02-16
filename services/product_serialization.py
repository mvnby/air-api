"""Shared product serialization helpers used by API and service layers."""

from __future__ import annotations

from typing import Any, Dict, List
import ast


def sanitize_specs(specs: Any) -> Dict[str, Any]:
    value = specs
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except Exception:
            value = {}
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if not str(k).startswith("__")}


def parse_legacy_images(images: Any) -> List[str]:
    value = images
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except Exception:
            value = []
    if not isinstance(value, list):
        return []
    return value


def to_web_path(path: str) -> str:
    if path and not path.startswith("/"):
        return f"/{path}"
    return path

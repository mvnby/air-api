"""MDV model Wi-Fi states confirmed by the price and the catalog owner."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "config/catalog_repairs/mdv_price_2026_09_23.json"
CONFIRMED_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "config/catalog_repairs/mdv_wifi_confirmed_2026_09_23.json"


@lru_cache(maxsize=1)
def wifi_states_by_model_pair() -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for path in (MANIFEST_PATH, CONFIRMED_MANIFEST_PATH):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for entry in manifest["wifi"]:
            key = (entry["model_indoor"].upper(), (entry.get("model_outdoor") or "").upper())
            state = entry["new_state"]
            if state not in ("ready", "builtin") or key in result:
                raise ValueError(f"Invalid MDV Wi-Fi override for {key}")
            result[key] = state
    return result


def apply_mdv_price_wifi_override(specs: dict[str, Any]) -> dict[str, Any]:
    indoor = str(specs.get("model_indoor") or "").strip().upper()
    outdoor = str(specs.get("model_outdoor") or "").strip().upper()
    state = wifi_states_by_model_pair().get((indoor, outdoor))
    if state is None:
        return specs
    return {**specs, "wifi_ready": state}

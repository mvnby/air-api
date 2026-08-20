from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# BTU index → area (m²) and power_cooling (kW) ranges.
# Ranges include a small "dictionary gap" so partial catalogue data still
# matches (for example, products without specs.area_m2 rely on the title fallback).
# ---------------------------------------------------------------------------
BTU_MAPPING: Dict[str, Dict[str, Tuple[float, float]]] = {
    "7":  {"area": (15, 24),   "power": (2.0, 2.4)},
    "07": {"area": (15, 24),   "power": (2.0, 2.4)},
    "9":  {"area": (25, 32),   "power": (2.5, 3.0)},
    "09": {"area": (25, 32),   "power": (2.5, 3.0)},
    "12": {"area": (33, 42),   "power": (3.2, 4.0)},
    "18": {"area": (45, 60),   "power": (5.0, 5.8)},
    "24": {"area": (65, 80),   "power": (6.5, 8.0)},
    "36": {"area": (90, 110),  "power": (9.5, 11.0)},
    "42": {"area": (110, 130), "power": (11.0, 13.0)},
    "60": {"area": (150, 180), "power": (15.0, 18.0)},
}

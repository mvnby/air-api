#!/usr/bin/env python3
"""Preload rembg model files into the runtime cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.product_image_processing_provider import (
    rembg_preload_model_names,
    warmup_rembg_models,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated rembg model names. Defaults to BACKGROUND_REMOVAL_REMBG_PRELOAD_MODELS or the safe preload list.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit after the first failed model download/session creation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_names = rembg_preload_model_names(args.models) if args.models else None
    results = []
    for result in warmup_rembg_models(model_names):
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.fail_fast and result["status"] != "ready":
            return 1

    failed = [item for item in results if item["status"] != "ready"]
    print(
        json.dumps(
            {
                "status": "complete" if not failed else "partial",
                "ready": len(results) - len(failed),
                "failed": len(failed),
                "models": [item["model"] for item in results],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Plan reviewed feature media; execute only its exact unexpired digest."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.feature_media_publication import PublicationBlocked, run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reviewed-plan", type=Path)
    parser.add_argument("--execute-plan-digest", metavar="SHA256")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(manifest_path=args.manifest, execute=args.execute,
            reviewed_plan=args.reviewed_plan, execute_plan_digest=args.execute_plan_digest))
    except (PublicationBlocked, ValueError, KeyError) as exc:
        print(json.dumps({"ready": False, "blocked": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

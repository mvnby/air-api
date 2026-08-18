"""Validate storefront signing config without printing secret material."""

from __future__ import annotations

import sys

sys.path.append(".")

from core.config import settings  # noqa: E402
from core.storefront_signing_keyring import StorefrontSigningKeyring  # noqa: E402


def safe_inventory_lines(keyring: StorefrontSigningKeyring) -> list[str]:
    roles_by_host: dict[str, dict[str, str]] = {}
    for key in keyring.keys:
        for hostname, role in key.host_roles:
            roles_by_host.setdefault(hostname, {})[role] = key.key_id

    lines = [
        "storefront_signing_keyring status=ok "
        f"keys={len(keyring.keys)} hosts={len(roles_by_host)}"
    ]
    for hostname in sorted(roles_by_host):
        roles = roles_by_host[hostname]
        lines.append(
            "storefront_signing_host "
            f"hostname={hostname} "
            f"primary={roles.get('primary', '-')} "
            f"previous={roles.get('previous', '-')}"
        )
    return lines


def main() -> int:
    for line in safe_inventory_lines(
        settings.storefront_context_signing_keyring
    ):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

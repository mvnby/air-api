from core.storefront_signing_keyring import (
    StorefrontSigningKey,
    StorefrontSigningKeyring,
)
from scripts.validate_storefront_signing_keyring import safe_inventory_lines


def test_safe_inventory_never_prints_secret_material():
    secret = "inventory-secret-must-not-appear-at-least-32-bytes"
    keyring = StorefrontSigningKeyring(
        keys=(
            StorefrontSigningKey(
                key_id="polotsk-web-current",
                secret=secret,
                host_roles=(("polotsk.mvn.by", "primary"),),
            ),
        )
    )

    rendered = "\n".join(safe_inventory_lines(keyring))

    assert secret not in rendered
    assert "hostname=polotsk.mvn.by" in rendered
    assert "primary=polotsk-web-current" in rendered
    assert "previous=-" in rendered

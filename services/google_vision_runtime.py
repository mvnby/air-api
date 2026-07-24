import os
from pathlib import Path
from typing import Any

from google.oauth2 import service_account


def verify_google_vision_credentials_startup(current_settings: Any) -> None:
    """Fail production startup when configured OCR credentials are unusable."""
    if not current_settings.is_production:
        return

    configured_path = str(
        current_settings.GOOGLE_VISION_CREDENTIALS_FILE or ""
    ).strip()
    if not configured_path:
        return

    credentials_path = Path(configured_path)
    if not credentials_path.is_file() or not os.access(credentials_path, os.R_OK):
        raise RuntimeError(
            "Google Vision credentials file is not readable; "
            "check the container path and read-only secret mount"
        )

    try:
        service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/cloud-vision"],
        )
    except Exception as exc:
        raise RuntimeError(
            "Google Vision credentials startup validation failed "
            f"({type(exc).__name__}); check the mounted service account file"
        ) from None

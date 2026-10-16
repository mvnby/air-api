"""Links carry company/site and are validated again by the installer bootstrap."""

from urllib.parse import urlencode
from core.config import settings


def installer_work_url(assignment_id, *, tenant_id, storefront_slug):
    query = urlencode({"company": tenant_id, "site": storefront_slug})
    return f"{settings.MANAGER_BASE_URL.rstrip('/')}/my-work/{assignment_id}?{query}"

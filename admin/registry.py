from .calendar import CalendarAdmin
from .catalog import ProductAdmin, TagAdmin, TagGroupAdmin
from .catalog_bulk import BulkTagsView
from .config import GlobalConfigAdmin
from .content import ArticleAdmin
from .customers import CustomerAdmin
from .google_auth import GoogleAuthView
from .installation_rates import InstallationRateAdmin
from .installers import InstallerAdmin
from .kanban import KanbanView
from .orders import OrderAdmin, OrderProductLinkAdmin, OrderServiceLinkAdmin, ServiceAdmin

# Legacy compatibility note:
# Keep this registry focused on existing SQLAdmin capabilities.
# New feature development should target manager views/routes.

admin_views = [
    KanbanView,
    CalendarAdmin,
    OrderAdmin,
    ProductAdmin,
    ServiceAdmin,
    CustomerAdmin,
    ArticleAdmin,
    TagAdmin,
    TagGroupAdmin,
    OrderProductLinkAdmin,
    OrderServiceLinkAdmin,
    BulkTagsView,
    GoogleAuthView,
    InstallerAdmin,
    GlobalConfigAdmin,
    InstallationRateAdmin,
]

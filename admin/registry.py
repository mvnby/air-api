from .calendar import CalendarAdmin
from .catalog import BulkTagsView, InstallationRateAdmin, ProductAdmin, TagAdmin, TagGroupAdmin
from .config import GlobalConfigAdmin
from .content import ArticleAdmin
from .customers import CustomerAdmin
from .google_auth import GoogleAuthView
from .installers import InstallerAdmin
from .kanban import KanbanView
from .orders import OrderAdmin, OrderProductLinkAdmin, OrderServiceLinkAdmin, ServiceAdmin

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

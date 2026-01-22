from .catalog import ProductAdmin, TagAdmin, TagGroupAdmin, BulkTagsView
from .orders import OrderAdmin, ServiceAdmin, OrderProductLinkAdmin, OrderServiceLinkAdmin
from .customers import CustomerAdmin
from .installers import InstallerAdmin
from .content import ArticleAdmin

from .kanban import KanbanView
from .calendar import CalendarAdmin
from .google_auth import GoogleAuthView

from .config import GlobalConfigAdmin

# Export all views for easy registration in main.py
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
    GoogleAuthView, # Settings (Bottom)
    InstallerAdmin,
    GlobalConfigAdmin
]

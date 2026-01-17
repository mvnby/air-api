from .catalog import ProductAdmin, TagAdmin, TagGroupAdmin, BulkTagsView
from .orders import OrderAdmin, ServiceAdmin, OrderProductLinkAdmin, OrderServiceLinkAdmin
from .customers import CustomerAdmin
from .content import ArticleAdmin

from .kanban import KanbanView
from .google_auth import GoogleAuthView

# Export all views for easy registration in main.py
admin_views = [
    KanbanView,
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
    GoogleAuthView # Settings (Bottom)
]

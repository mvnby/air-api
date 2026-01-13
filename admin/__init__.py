from .catalog import ProductAdmin, TagAdmin, TagGroupAdmin, BulkTagsView
from .orders import OrderAdmin, ServiceAdmin, OrderProductLinkAdmin, OrderServiceLinkAdmin
from .content import ArticleAdmin

# Export all views for easy registration in main.py
admin_views = [
    ProductAdmin,
    TagAdmin,
    TagGroupAdmin,
    OrderAdmin,
    ServiceAdmin,
    OrderProductLinkAdmin,
    OrderServiceLinkAdmin,
    ArticleAdmin,
    BulkTagsView
]

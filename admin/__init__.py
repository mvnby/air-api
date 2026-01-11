from .catalog import ProductAdmin, TagAdmin, TagGroupAdmin
from .orders import OrderAdmin
from .content import ArticleAdmin

# Export all views for easy registration in main.py
admin_views = [
    ProductAdmin,
    TagAdmin,
    TagGroupAdmin,
    OrderAdmin,
    ArticleAdmin
]

from .catalog import ProductAdmin, TagAdmin, TagGroupAdmin
from .catalog_bulk import BulkTagsView
from .installation_rates import InstallationRateAdmin
from .orders import OrderAdmin, ServiceAdmin, OrderProductLinkAdmin, OrderServiceLinkAdmin
from .customers import CustomerAdmin
from .installers import InstallerAdmin
from .content import ArticleAdmin

from .kanban import KanbanView
from .calendar import CalendarAdmin
from .google_auth import GoogleAuthView

from .config import GlobalConfigAdmin
from .registry import admin_views

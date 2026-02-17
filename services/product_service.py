"""Compatibility facade for product service operations.

Read/filter methods are inherited from ProductReadService.
Write/mutation methods are inherited from ProductWriteService.
Manager-facing methods are inherited from ProductManagerService.
"""

from services.product_manager_service import ProductManagerService
from services.product_read_service import ProductReadService
from services.product_write_service import ProductWriteService


class ProductService(ProductReadService, ProductWriteService, ProductManagerService):
    """Backward-compatible facade that combines product service specializations."""

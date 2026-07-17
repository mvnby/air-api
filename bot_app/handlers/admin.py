"""Aggregated staff administration routers, split by use case."""

from aiogram import Router

from . import attachments, nameplates, product_admin, requisites
from .admin_common import *
from .attachments import *
from .nameplates import *
from .product_admin import *
from .requisites import *

router = Router()
router.include_router(requisites.router)
router.include_router(attachments.router)
router.include_router(nameplates.router)
router.include_router(product_admin.router)

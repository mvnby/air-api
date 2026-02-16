from typing import Any, Dict, List

from core.logger import logger
from models import Product
from services.manager_media_service import ManagerMediaService
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile


class ManagerMediaOrchestratorService:
    @staticmethod
    async def upload_image_from_url(
        session: AsyncSession,
        *,
        url: str,
        product_id: int,
        is_installation: bool,
    ) -> Dict[str, Any]:
        product = await session.get(Product, product_id)
        if not product:
            raise LookupError("Product not found")

        set_main = not is_installation
        return await ManagerMediaService.process_and_save_image(
            url=url,
            product_id=product_id,
            session=session,
            set_main=set_main,
            is_installation=is_installation,
        )

    @staticmethod
    async def upload_local_images(
        session: AsyncSession,
        *,
        product_id: int,
        files: List[UploadFile],
        is_installation: bool,
    ) -> Dict[str, Any]:
        product = await session.get(Product, product_id)
        if not product:
            raise LookupError("Product not found")

        uploaded_images: List[Dict[str, Any]] = []
        for file in files:
            try:
                content = await file.read()
                should_set_main = bool(
                    not product.main_image and not is_installation and len(uploaded_images) == 0
                )
                result = await ManagerMediaService.save_image_from_bytes(
                    image_content=content,
                    product_id=product_id,
                    session=session,
                    set_main=should_set_main,
                    is_installation=is_installation,
                )
                uploaded_images.append(result)
                if should_set_main:
                    product.main_image = result["url"]
            except Exception as exc:
                logger.error(f"Failed to upload file {file.filename}: {exc}")
                continue

        return {"uploaded": len(uploaded_images), "images": uploaded_images}

    @staticmethod
    async def link_search_result(
        session: AsyncSession,
        *,
        url: str,
        product_id: int,
    ) -> Dict[str, Any]:
        product = await session.get(Product, product_id)
        if not product:
            raise LookupError("Product not found")

        return await ManagerMediaService.process_and_save_image(
            url=url,
            product_id=product_id,
            session=session,
            set_main=False,
            is_installation=False,
        )

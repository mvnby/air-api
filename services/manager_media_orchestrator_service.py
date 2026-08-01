import json
from typing import Any, Dict, List

from core.logger import logger
from models import Product
from services.manager_media_service import ManagerMediaService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
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

        file_payloads: List[bytes] = []
        for file in files:
            try:
                content = await file.read()
                if content:
                    file_payloads.append(content)
            except Exception as exc:
                logger.error(f"Failed to upload file {file.filename}: {exc}")

        uploaded_images = await ManagerMediaService.save_images_from_bytes(
            file_payloads=file_payloads,
            product_id=product_id,
            session=session,
            set_main_if_missing=not bool(product.main_image),
            is_installation=is_installation,
        )

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

    @staticmethod
    async def bulk_upload_local_images(
        session: AsyncSession,
        *,
        product_ids_json: str,
        files: List[UploadFile],
        is_installation: bool,
        set_main: bool,
    ) -> Dict[str, Any]:
        try:
            product_ids = json.loads(product_ids_json)
            if not isinstance(product_ids, list):
                raise ValueError()
            unique_product_ids = list(dict.fromkeys(int(pid) for pid in product_ids))
        except Exception as exc:
            raise ValueError("Invalid product_ids_json") from exc

        if not unique_product_ids:
            raise ValueError("product_ids is required")
        if not files:
            raise ValueError("files is required")

        products_stmt = select(Product.id).where(Product.id.in_(unique_product_ids))
        existing_product_ids = set((await session.execute(products_stmt)).scalars().all())
        missing = sorted(set(unique_product_ids) - existing_product_ids)
        if missing:
            raise LookupError(f"Products not found: {missing}")

        file_payloads: List[bytes] = []
        for file in files:
            content = await file.read()
            if content:
                file_payloads.append(content)

        return await ManagerMediaService.bulk_upload_local_images(
            session=session,
            product_ids=unique_product_ids,
            file_payloads=file_payloads,
            is_installation=is_installation,
            set_main=set_main,
        )

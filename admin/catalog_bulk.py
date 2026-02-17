from sqladmin import BaseView, expose
from starlette.responses import RedirectResponse
from sqlmodel import select
from sqlalchemy.orm import selectinload

from core.database import async_session_maker
from models import Product, TagGroup
from services.product_service import ProductService


class BulkTagsView(BaseView):
    name = "Bulk Tags"
    icon = "fa-solid fa-tags"

    def is_visible(self, request):
        return False

    @staticmethod
    def _parse_selected_product_ids(request) -> list[int]:
        raw = request.query_params.get("pks", "")
        return [int(pk) for pk in raw.split(",") if pk]

    @staticmethod
    async def _apply_bulk_tags(request, product_ids: list[int]) -> int:
        form = await request.form()
        action_type = form.get("action_type")
        selected_tag_ids = [int(tag_id) for tag_id in form.getlist("tag_ids")]

        async with async_session_maker() as session:
            return await ProductService.bulk_update_tags(
                session=session,
                product_ids=product_ids,
                tag_ids=selected_tag_ids,
                action=action_type,
            )

    @staticmethod
    async def _load_bulk_form_data(product_ids: list[int]) -> tuple[list[TagGroup], list[Product]]:
        async with async_session_maker() as session:
            groups_stmt = select(TagGroup).options(selectinload(TagGroup.tags))
            groups = (await session.execute(groups_stmt)).scalars().all()

            products_stmt = select(Product).where(Product.id.in_(product_ids))
            products = (await session.execute(products_stmt)).scalars().all()

        return groups, products

    @expose("/bulk-tags", methods=["GET", "POST"])
    async def list(self, request):
        pks = self._parse_selected_product_ids(request)

        if request.method == "POST":
            num_updated = await self._apply_bulk_tags(request, pks)

            return RedirectResponse(
                url=f"{request.url_for('admin:list', identity='product')}?msg=Теги обновлены для {num_updated} товаров&type=success",
                status_code=303,
            )

        groups, products = await self._load_bulk_form_data(pks)

        return await self.templates.TemplateResponse(
            request,
            "sqladmin/bulk_tags.html",
            {
                "model_view": self,
                "groups": groups,
                "products": products,
                "pks": pks,
            },
        )

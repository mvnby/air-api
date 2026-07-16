from collections import defaultdict
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import OrderProductLink, SupplyRequestLine


class OrderProductLineService:
    @staticmethod
    async def reconcile(
        session: AsyncSession,
        *,
        order_id: int,
        proposal_id: int,
        lines: Sequence[dict[str, Any]],
    ) -> None:
        result = await session.execute(
            select(OrderProductLink)
            .where(
                OrderProductLink.order_id == order_id,
                OrderProductLink.proposal_id == proposal_id,
            )
            .order_by(OrderProductLink.id)
        )
        existing_links = list(result.scalars().all())
        existing_by_id = {int(link.id): link for link in existing_links if link.id is not None}
        existing_by_product: dict[int, list[OrderProductLink]] = defaultdict(list)
        for link in existing_links:
            if link.product_id is not None:
                existing_by_product[int(link.product_id)].append(link)

        claimed_ids: set[int] = set()
        reconciled: list[tuple[dict[str, Any], OrderProductLink | None]] = []
        for line in lines:
            link: OrderProductLink | None = None
            requested_link_id = line.get("link_id")
            if requested_link_id is not None:
                link = existing_by_id.get(int(requested_link_id))
                if link is None:
                    raise ValueError("Product line does not belong to the selected proposal")
                if int(link.id) in claimed_ids:
                    raise ValueError("Product line is duplicated in the request")
            else:
                candidates = existing_by_product.get(int(line["product_id"]), [])
                link = next(
                    (candidate for candidate in candidates if int(candidate.id) not in claimed_ids),
                    None,
                )

            if link is not None and link.id is not None:
                claimed_ids.add(int(link.id))
            reconciled.append((line, link))

        existing_ids = set(existing_by_id)
        removed_ids = existing_ids - claimed_ids
        referenced_ids: set[int] = set()
        if existing_ids:
            reference_result = await session.execute(
                select(SupplyRequestLine.order_product_link_id).where(
                    SupplyRequestLine.order_product_link_id.in_(existing_ids)
                )
            )
            referenced_ids = {
                int(link_id)
                for link_id in reference_result.scalars().all()
                if link_id is not None
            }

        if removed_ids & referenced_ids:
            raise ValueError(
                "Товар уже включен в поставку. Сначала удалите его из заявки поставщику."
            )

        for line, link in reconciled:
            if link is None:
                link = OrderProductLink(order_id=order_id, proposal_id=proposal_id)
            elif link.id is not None and int(link.id) in referenced_ids:
                if int(link.product_id or 0) != int(line["product_id"]):
                    raise ValueError(
                        "Нельзя заменить товар в строке, уже включенной в поставку."
                    )
                if int(link.quantity or 0) != int(line["quantity"]):
                    raise ValueError(
                        "Нельзя изменить количество товара, уже включенного в поставку."
                    )

            link.product_id = int(line["product_id"])
            link.quantity = int(line["quantity"])
            link.price = int(line["price"])
            link.cost = int(line["cost"])
            link.logistics_components = line.get("logistics_components")
            session.add(link)

        for link_id in removed_ids:
            await session.delete(existing_by_id[link_id])

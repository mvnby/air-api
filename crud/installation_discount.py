from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    GlobalConfig,
    InstallationDiscountPolicy,
    InstallationDiscountProductRule,
    Product,
)


class InstallationDiscountDAO:
    @staticmethod
    async def get_legacy_default_discount(
        session: AsyncSession,
    ) -> str | None:
        result = await session.execute(
            select(GlobalConfig.value).where(GlobalConfig.key == "install_discount")
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_legacy_discount_config(
        session: AsyncSession,
    ) -> GlobalConfig | None:
        result = await session.execute(
            select(GlobalConfig).where(GlobalConfig.key == "install_discount")
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_policy(
        session: AsyncSession,
    ) -> InstallationDiscountPolicy | None:
        return await session.get(InstallationDiscountPolicy, 1)

    @staticmethod
    async def get_rules_by_product_ids(
        session: AsyncSession,
        product_ids: set[int] | list[int] | tuple[int, ...],
    ) -> dict[int, InstallationDiscountProductRule]:
        ids = tuple(sorted({int(product_id) for product_id in product_ids}))
        if not ids:
            return {}
        result = await session.execute(
            select(InstallationDiscountProductRule).where(
                InstallationDiscountProductRule.product_id.in_(ids)
            )
        )
        return {int(rule.product_id): rule for rule in result.scalars().all()}

    @staticmethod
    async def list_rules(
        session: AsyncSession,
        *,
        search: str | None,
        page: int,
        limit: int,
    ) -> tuple[list[tuple[InstallationDiscountProductRule, Product]], int]:
        conditions = []
        normalized_search = (search or "").strip()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            conditions.append(
                or_(Product.title.ilike(pattern), Product.slug.ilike(pattern))
            )
        base = (
            select(InstallationDiscountProductRule, Product)
            .join(Product, Product.id == InstallationDiscountProductRule.product_id)
            .where(*conditions)
        )
        rows = list(
            (
                await session.execute(
                    base.order_by(
                        InstallationDiscountProductRule.updated_at.desc(),
                        InstallationDiscountProductRule.product_id.asc(),
                    )
                    .offset((page - 1) * limit)
                    .limit(limit)
                )
            ).all()
        )
        count_statement = (
            select(func.count())
            .select_from(InstallationDiscountProductRule)
            .join(Product, Product.id == InstallationDiscountProductRule.product_id)
            .where(*conditions)
        )
        total = int((await session.execute(count_statement)).scalar_one())
        return rows, total

    @staticmethod
    async def search_products(
        session: AsyncSession,
        *,
        search: str,
        limit: int,
    ) -> list[Product]:
        normalized_search = search.strip()
        conditions = [Product.is_published.is_(True)]
        if normalized_search:
            pattern = f"%{normalized_search}%"
            conditions.append(
                or_(Product.title.ilike(pattern), Product.slug.ilike(pattern))
            )
        result = await session.execute(
            select(Product)
            .where(*conditions)
            .order_by(Product.title.asc(), Product.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_product(
        session: AsyncSession,
        product_id: int,
    ) -> Product | None:
        return await session.get(Product, product_id)

    @staticmethod
    async def get_rule(
        session: AsyncSession,
        product_id: int,
    ) -> InstallationDiscountProductRule | None:
        return await session.get(InstallationDiscountProductRule, product_id)

    @staticmethod
    def add(
        session: AsyncSession,
        value: (
            GlobalConfig
            | InstallationDiscountPolicy
            | InstallationDiscountProductRule
        ),
    ) -> None:
        session.add(value)

    @staticmethod
    async def delete_rule(
        session: AsyncSession,
        rule: InstallationDiscountProductRule,
    ) -> None:
        await session.delete(rule)


__all__ = ["InstallationDiscountDAO"]

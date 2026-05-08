from typing import List
from fastapi import HTTPException
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select
from models import TagGroup, Tag
from schemas import (
    ManagerTagGroupCreatePayload,
    ManagerTagGroupUpdatePayload,
    ManagerTagCreatePayload,
    ManagerTagUpdatePayload,
)

class TagService:

    @staticmethod
    async def get_tag_groups(session: AsyncSession) -> List[TagGroup]:
        stmt = (
            select(TagGroup)
            .options(selectinload(TagGroup.tags))
            .order_by(TagGroup.sort_order, TagGroup.title)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_tag_group(session: AsyncSession, payload: ManagerTagGroupCreatePayload) -> TagGroup:
        slug = payload.slug
        if not slug:
            slug = slugify(payload.title)
        
        # Check slug uniqueness
        existing = await session.execute(select(TagGroup).where(TagGroup.slug == slug))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail=f"Группа с таким slug '{slug}' уже существует.")

        group = TagGroup(
            title=payload.title,
            slug=slug,
            is_public=payload.is_public,
            color=payload.color,
            allow_multiple=payload.allow_multiple
        )
        session.add(group)
        await session.commit()

        stmt = select(TagGroup).where(TagGroup.id == group.id).options(selectinload(TagGroup.tags))
        res = await session.execute(stmt)
        return res.scalars().one()

    @staticmethod
    async def update_tag_group(session: AsyncSession, group_id: int, payload: ManagerTagGroupUpdatePayload) -> TagGroup:
        group = await session.get(TagGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Группа тегов не найдена.")

        if payload.slug is not None and payload.slug != group.slug:
            existing = await session.execute(select(TagGroup).where(TagGroup.slug == payload.slug))
            if existing.scalars().first():
                raise HTTPException(status_code=400, detail=f"Группа с таким slug '{payload.slug}' уже существует.")
            group.slug = payload.slug

        if payload.title is not None:
            group.title = payload.title
        if payload.is_public is not None:
            group.is_public = payload.is_public
        if payload.color is not None:
            group.color = payload.color
        if payload.allow_multiple is not None:
            group.allow_multiple = payload.allow_multiple
        if payload.sort_order is not None:
            group.sort_order = payload.sort_order

        await session.commit()
        
        # Reload with tags
        stmt = select(TagGroup).where(TagGroup.id == group_id).options(selectinload(TagGroup.tags))
        res = await session.execute(stmt)
        return res.scalars().first()

    @staticmethod
    async def delete_tag_group(session: AsyncSession, group_id: int) -> None:
        group = await session.get(TagGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Группа тегов не найдена.")
            
        stmt = select(Tag).where(Tag.group_id == group_id)
        tags_res = await session.execute(stmt)
        tags = tags_res.scalars().all()
        
        if tags:
            raise HTTPException(status_code=400, detail=f"Невозможно удалить группу: к ней привязаны {len(tags)} тегов. Сначала удалите теги.")
            
        await session.delete(group)
        await session.commit()

    @staticmethod
    async def create_tag(session: AsyncSession, payload: ManagerTagCreatePayload) -> Tag:
        group = await session.get(TagGroup, payload.group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Указанная группа тегов не найдена.")

        slug = payload.slug
        if not slug:
            slug = slugify(payload.title)

        existing = await session.execute(select(Tag).where(Tag.slug == slug))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail=f"Тег с таким slug '{slug}' уже существует.")

        tag = Tag(
            group_id=payload.group_id,
            title=payload.title,
            slug=slug,
            is_public=payload.is_public,
            is_filter=payload.is_filter
        )
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
        return tag

    @staticmethod
    async def update_tag(session: AsyncSession, tag_id: int, payload: ManagerTagUpdatePayload) -> Tag:
        tag = await session.get(Tag, tag_id)
        if not tag:
            raise HTTPException(status_code=404, detail="Тег не найден.")

        if payload.slug is not None and payload.slug != tag.slug:
            existing = await session.execute(select(Tag).where(Tag.slug == payload.slug))
            if existing.scalars().first():
                raise HTTPException(status_code=400, detail=f"Тег с таким slug '{payload.slug}' уже существует.")
            tag.slug = payload.slug

        if payload.title is not None:
            tag.title = payload.title
        if payload.is_public is not None:
            tag.is_public = payload.is_public
        if payload.is_filter is not None:
            tag.is_filter = payload.is_filter
        if payload.sort_order is not None:
            tag.sort_order = payload.sort_order

        await session.commit()
        await session.refresh(tag)
        return tag

    @staticmethod
    async def delete_tag(session: AsyncSession, tag_id: int) -> None:
        tag = await session.get(Tag, tag_id)
        if not tag:
            raise HTTPException(status_code=404, detail="Тег не найден.")
            
        await session.delete(tag)
        await session.commit()

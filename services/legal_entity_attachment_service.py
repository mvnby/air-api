"""Private, immutable registration certificate storage and issuer validation."""

import asyncio
from hashlib import sha256
from io import BytesIO
import re
import unicodedata
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.order import OrderDocument
from models.tenancy import TenantScope
from models.document import DocumentLegalEntity
from models.legal_entity_attachment import LegalEntityAttachment
from services.private_attachment_storage_service import (
    get_private_attachment_storage,
    VariantScopedPrivateAttachmentStorage,
)

MAX_CERTIFICATE_BYTES = 10 * 1024 * 1024


def validate_certificate(content: bytes, filename: str | None) -> tuple[str, str, str]:
    if not content or len(content) > MAX_CERTIFICATE_BYTES:
        raise ValueError("Файл должен быть непустым и не больше 10 МБ")
    try:
        if content.startswith(b"%PDF-"):
            pdf = PdfReader(BytesIO(content), strict=True)
            if pdf.is_encrypted or not len(pdf.pages):
                raise ValueError()
            for page in pdf.pages:
                page.get_contents()
            mime, extension = "application/pdf", "pdf"
        else:
            with Image.open(BytesIO(content)) as image:
                if (
                    image.format not in {"JPEG", "PNG"}
                    or image.width * image.height > 20_000_000
                ):
                    raise ValueError()
                extension = "jpg" if image.format == "JPEG" else "png"
                mime = "image/jpeg" if extension == "jpg" else "image/png"
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
    except Exception as exc:
        raise ValueError(
            "Загрузите корректный PDF, JPEG или PNG (до 20 млн пикселей)"
        ) from exc
    name = str(filename or "certificate").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(
        "_" if unicodedata.category(char).startswith("C") else char for char in name
    )
    name = re.sub(r'[\x00-\x1f\x7f<>:"|?*]', "_", name).strip(" .")
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return mime, extension, f"{stem[:190] or 'certificate'}.{extension}"


class LegalEntityAttachmentService:
    @staticmethod
    async def entity(
        session: AsyncSession,
        tenant_id: int,
        entity_id: int | None,
        *,
        lock: bool = False,
    ) -> DocumentLegalEntity:
        query = select(DocumentLegalEntity).where(
            DocumentLegalEntity.id == entity_id,
            DocumentLegalEntity.tenant_id == tenant_id,
        )
        if lock:
            query = query.with_for_update()
        entity = (await session.execute(query)).scalar_one_or_none()
        if entity is None:
            raise ValueError("Юридическое лицо не найдено")
        return entity

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: int, attachment_id: str
    ) -> LegalEntityAttachment:
        row = (
            await session.execute(
                select(LegalEntityAttachment).where(
                    LegalEntityAttachment.id == attachment_id,
                    LegalEntityAttachment.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Свидетельство не найдено")
        return row

    @classmethod
    async def make_current(
        cls, session: AsyncSession, tenant_id: int, row: LegalEntityAttachment
    ) -> LegalEntityAttachment:
        await cls.entity(session, tenant_id, row.legal_entity_id, lock=True)
        await session.execute(
            update(LegalEntityAttachment)
            .where(
                LegalEntityAttachment.tenant_id == tenant_id,
                LegalEntityAttachment.legal_entity_id == row.legal_entity_id,
            )
            .values(is_current=False)
        )
        await session.flush()
        row.is_current = True
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    @classmethod
    async def upload(
        cls,
        session: AsyncSession,
        tenant_id: int,
        entity_id: int,
        content: bytes,
        filename: str | None,
    ) -> LegalEntityAttachment:
        mime, extension, name = await asyncio.to_thread(
            validate_certificate, content, filename
        )
        await cls.entity(session, tenant_id, entity_id, lock=True)
        storage = VariantScopedPrivateAttachmentStorage(
            get_private_attachment_storage(), variant_scope="registration-certificates"
        )
        stored = await storage.save(
            content=content,
            content_hash=sha256(content).hexdigest(),
            extension=extension,
            content_type=mime,
            variant=f"tenant-{tenant_id}-entity-{entity_id}",
        )
        row = LegalEntityAttachment(
            tenant_id=tenant_id,
            legal_entity_id=entity_id,
            filename=name,
            mime_type=mime,
            provider=stored.provider,
            storage_key=stored.storage_key,
            checksum_sha256=stored.content_hash,
            size_bytes=stored.size_bytes,
            is_current=False,
        )
        session.add(row)
        await session.flush()
        return await cls.make_current(session, tenant_id, row)

    @staticmethod
    async def read(row: LegalEntityAttachment) -> bytes:
        try:
            content = await get_private_attachment_storage(row.provider).read(
                row.storage_key
            )
        except FileNotFoundError as exc:
            raise ValueError("Сохранённое свидетельство недоступно") from exc
        if (
            len(content) != row.size_bytes
            or sha256(content).hexdigest() != row.checksum_sha256
        ):
            raise ValueError("Не удалось проверить сохранённое свидетельство")
        return content

    @classmethod
    async def resolve_for_mail(
        cls,
        session: AsyncSession,
        tenant_scope: TenantScope,
        attachment_id: str,
        documents: list[OrderDocument],
        legal_entity_id: int | None = None,
    ) -> LegalEntityAttachment:
        row = await cls.get(session, tenant_scope.tenant_id, attachment_id)
        issuers = {item.legal_entity_id for item in documents}
        if documents and (None in issuers or len(issuers) != 1):
            raise ValueError(
                "У выбранных документов должен быть один определённый отправитель"
            )
        if issuers:
            issuer = next(iter(issuers))
            if legal_entity_id is not None and legal_entity_id != issuer:
                raise ValueError("Отправитель не совпадает с выбранными документами")
        elif legal_entity_id is not None:
            issuer = legal_entity_id
        else:
            issuer = (
                await session.execute(
                    select(DocumentLegalEntity.id).where(
                        DocumentLegalEntity.tenant_id == tenant_scope.tenant_id,
                        DocumentLegalEntity.is_default.is_(True),
                        DocumentLegalEntity.status == "active",
                    )
                )
            ).scalar_one_or_none()
        entity = await cls.entity(session, tenant_scope.tenant_id, issuer)
        if entity.status != "active" or row.legal_entity_id != issuer:
            raise ValueError("Свидетельство не совпадает с отправителем документов")
        return row

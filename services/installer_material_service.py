"""Explicit technical materials: revalidate assignment before and after storage I/O."""

from datetime import datetime

from api_contracts.installer_workspace import InstallerMaterial, ManagerWorkerMaterial
from crud.installer_workspace import InstallerWorkspaceDAO as DAO
from models.installer_publication import InstallerMaterialPublication
from services.installer_collection_service import InstallerWorkspaceError
from services.private_attachment_storage_service import get_private_attachment_storage
from services.worker_assignment_access_service import (
    WorkerAssignmentAccessService as Access,
)


class InstallerMaterialService:
    MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    CATEGORIES = {
        "nameplate",
        "before_work",
        "after_work",
        "installation_result",
        "installation_indoor",
        "installation_outdoor",
        "installation_route",
        "installation_facade",
        "installation_power",
        "defect",
        "service",
    }

    @classmethod
    def allowed(cls, link, attachment, assignment=None):
        return bool(
            attachment.storage_key
            and attachment.mime_type in cls.MIME_TYPES
            and attachment.file_kind in {"image", "pdf"}
            and link.category in cls.CATEGORIES
            and link.origin_order_id is None
            and (
                assignment is None
                or assignment.work_stage_id is None
                or link.work_stage_id in {None, assignment.work_stage_id}
            )
        )

    @staticmethod
    def label(attachment):
        # Original filenames, captions and transcripts can contain procurement details.
        return f"{'Фото' if attachment.file_kind == 'image' else 'Технический материал'} №{attachment.id}"

    @classmethod
    async def manager_materials(cls, session, order_id):
        return [
            ManagerWorkerMaterial(
                link_id=link.id,
                label=cls.label(file),
                file_kind=file.file_kind,
                work_stage_id=link.work_stage_id,
            )
            for link, file in await DAO.materials(session, order_id)
            if cls.allowed(link, file)
        ]

    @classmethod
    async def visible(cls, session, assignment):
        available = {
            link.id: (link, file)
            for link, file in await DAO.materials(session, assignment.order_id)
            if cls.allowed(link, file, assignment)
        }
        result = []
        for publication in await DAO.publications(session, assignment.id):
            pair = available.get(publication.order_attachment_link_id)
            if publication.revoked_at is None and pair is not None:
                _, file = pair
                result.append(
                    InstallerMaterial(
                        id=publication.id,
                        label=cls.label(file),
                        file_kind=file.file_kind,
                        content_url=f"/api/installer/works/{assignment.id}/materials/{publication.id}/content",
                    )
                )
        return result

    @classmethod
    async def publish(cls, session, assignment, link_ids):
        available = {
            link.id
            for link, file in await DAO.materials(session, assignment.order_id)
            if cls.allowed(link, file, assignment)
        }
        selected = set(link_ids)
        if not selected <= available:
            raise InstallerWorkspaceError(
                "material_unavailable",
                "Выберите доступные технические материалы этой работы",
                400,
            )
        existing = {
            row.order_attachment_link_id: row
            for row in await DAO.publications(session, assignment.id)
        }
        for link_id, publication in existing.items():
            publication.revoked_at = (
                None
                if link_id in selected
                else publication.revoked_at or datetime.now()
            )
            session.add(publication)
        for link_id in selected - existing.keys():
            session.add(
                InstallerMaterialPublication(
                    tenant_id=assignment.tenant_id,
                    storefront_id=assignment.storefront_id,
                    order_id=assignment.order_id,
                    assignment_id=assignment.id,
                    order_attachment_link_id=link_id,
                )
            )
        await session.flush()

    @classmethod
    async def _content_grant(cls, session, auth, assignment_id, material_id):
        assignment = await Access.get_for_actor(session, auth, assignment_id)
        if assignment is None:
            raise InstallerWorkspaceError("work_not_found", "Работа не найдена", 404)
        publication = next(
            (
                p
                for p in await DAO.publications(session, assignment.id)
                if p.id == material_id and p.revoked_at is None
            ),
            None,
        )
        if publication:
            for link, file in await DAO.materials(session, assignment.order_id):
                if link.id == publication.order_attachment_link_id and cls.allowed(
                    link, file, assignment
                ):
                    return file
        raise InstallerWorkspaceError("material_not_found", "Материал не найден", 404)

    @classmethod
    async def read_content(
        cls, session, *, auth, assignment_id, material_id, storage=None
    ):
        file = await cls._content_grant(session, auth, assignment_id, material_id)
        key, provider, mime, kind = (
            file.storage_key,
            file.storage_provider,
            file.mime_type,
            file.file_kind,
        )
        try:
            content = await (storage or get_private_attachment_storage(provider)).read(
                key
            )
        except FileNotFoundError:
            raise InstallerWorkspaceError(
                "material_not_found", "Материал не найден", 404
            ) from None
        # No presigned URL or cache validation bypass may retain revoked access.
        current = await cls._content_grant(session, auth, assignment_id, material_id)
        if (current.storage_key, current.mime_type) != (key, mime):
            raise InstallerWorkspaceError(
                "material_changed", "Материал изменён. Обновите работу"
            )
        extension = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "application/pdf": "pdf",
        }[mime]
        return content, mime, f"material-{material_id}.{extension}", kind

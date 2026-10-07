"""Resolve only explicitly selected immutable revisions into separate factual blocks."""
from sqlmodel import select

from models import Order, CustomerBranch, MaintenanceActPreparation, MaintenanceActSource, MaintenanceContinuation, MaintenanceObservationRevision
from services.maintenance_observation_service import MaintenanceObservationService
from .context_builder import DocumentContextError


async def extend_maintenance_snapshot(session, *, selection, scope, snapshot):
    preparation = await session.get(MaintenanceActPreparation, selection.maintenance_preparation_id)
    continuation = await session.get(MaintenanceContinuation, preparation.continuation_id) if preparation else None
    if not continuation or continuation.order_id != selection.order_id or (continuation.tenant_id, continuation.storefront_id) != (scope.tenant_id, scope.storefront_id):
        raise DocumentContextError("Подготовьте дефектный акт через выбранные замечания ТО")
    revisions = (await session.execute(select(MaintenanceObservationRevision)
        .join(MaintenanceActSource, MaintenanceActSource.revision_id == MaintenanceObservationRevision.id)
        .where(MaintenanceActSource.preparation_id == preparation.id)
        .order_by(MaintenanceObservationRevision.observation_id))).scalars().all()
    rows, sources = [], []
    for revision in revisions:
        observation = await MaintenanceObservationService.get(session, revision.observation_id, scope, lock=True)
        if observation.version != revision.version:
            raise DocumentContextError("Замечание изменено. Выберите актуальную версию.")
        detail = await MaintenanceObservationService.detail(session, observation, scope)
        content = revision.snapshot
        photos = [{"attachment_id": photo.id, "filename": photo.filename,
                   "access_path": f"/api/manager/service-attachments/{photo.id}/access"} for photo in detail.photos]
        sources.append({"observation_id": observation.id, "revision_id": revision.id, "version": revision.version,
                        "source_order_id": observation.source_order_id, "observed_at": observation.observed_at.isoformat(),
                        "created_by": observation.created_by, "revision_actor": revision.actor,
                        "original_comment": observation.original_comment, "content": content, "photos": photos})
        rows.append({"observation.equipment": content['equipment_description'],
                     "observation.provenance": f"Обнаружено {observation.observed_at:%d.%m.%Y %H:%M} UTC · {observation.created_by}; версия {revision.version}, уточнил {revision.actor}",
                     "observation.facts": content['facts'], "observation.recommendation": content['recommendation'],
                     "observation.sources": f"ТО #{observation.source_order_id}; замечание #{observation.id}, версия {revision.version}; /api/manager/maintenance-observations/{observation.id}",
                     "observation.photos": '\n'.join(f"{photo['filename']} · #{photo['attachment_id']} · {photo['access_path']}" for photo in photos) or "Не приложены"})
    if not rows:
        raise DocumentContextError("Выберите сохранённые замечания ТО")
    values = snapshot['values']
    source_order = await session.get(Order, continuation.source_order_id)
    branch = await session.get(CustomerBranch, continuation.customer_branch_id) if continuation.customer_branch_id else None
    values['order.object_title'] = str(getattr(branch, 'name', '') or '')
    values['order.object_address'] = str(source_order.delivery_address or getattr(branch, 'delivery_address', '') or '')
    if not values['order.object_title']:
        values['order.object_title'] = values['order.object_address']
    for field, label in (("seller.legal_name", "Наименование исполнителя"), ("customer.full_name", "Наименование клиента"),
                         ("order.object_address", "Адрес объекта")):
        if not str(values.get(field, '')).strip():
            raise DocumentContextError(f"Для дефектного акта требуется: {label}. Уточните реквизиты/объект.")
    values['maintenance.source_order'] = f"#{continuation.source_order_id}"
    # Never inherit completed-work assertions or repair diagnoses from a repair template.
    values['customer.signer_position'] = ''
    snapshot['meta']['maintenance'] = {"schema_version": 1, "preparation_id": preparation.id, "continuation_id": continuation.id,
                                       "source_order_id": continuation.source_order_id, "sources": sources}
    snapshot['table_rows'] = {"observations": rows}
    return snapshot

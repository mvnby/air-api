"""Explicit maintenance commercial workflow; ordinary order pricing remains authoritative."""
from decimal import Decimal
from copy import deepcopy
from sqlmodel import select, func
from models import (Order, OrderStatus, OrderProposal, OrderProductLink, OrderServiceLink,
    MaintenanceContinuation, MaintenanceObservationRevision, MaintenanceOffer, MaintenanceOfferSource,
    MaintenanceOfferEvent, MaintenanceResolution, EquipmentServiceHistory, EquipmentServiceEventType)
from services.command_transaction import command_transaction
from services.maintenance_observation_service import MaintenanceObservationService as Observations, ObservationConflict, ObservationNotFound, command_hash
from services.tenant_entity_access_service import TenantEntityAccessService as Access


class MaintenanceOfferService:
    @staticmethod
    async def context(session, source_order_id, scope, *, lock=False, create=False, actor=''):
        source = await Access.get_order(session, source_order_id, tenant_scope=scope, for_update=lock, populate_existing=True)
        if source is None:
            raise ObservationNotFound('Исходное ТО не найдено')
        if source.workflow_type != 'maintenance' or source.customer_id is None:
            raise ValueError('Требуется исходное ТО с клиентом')
        await Observations.validate_context(session, customer_id=source.customer_id, branch_id=source.customer_branch_id,
                                           equipment_id=None, scope=scope, allow_archived=True)
        continuation = await session.scalar(select(MaintenanceContinuation).where(MaintenanceContinuation.source_order_id == source.id))
        if continuation is None and create:
            order = Order(tenant_id=source.tenant_id, storefront_id=source.storefront_id, customer_id=source.customer_id,
                customer_branch_id=source.customer_branch_id, delivery_address=source.delivery_address,
                status=OrderStatus.NEGOTIATION, workflow_type='repair', title=f'Замечания по ТО #{source.id}',
                technical_meta={'maintenance_source_order_id': source.id})
            session.add(order); await session.flush()
            continuation = MaintenanceContinuation(source_order_id=source.id, order_id=order.id, tenant_id=source.tenant_id,
                storefront_id=source.storefront_id, customer_id=source.customer_id, customer_branch_id=source.customer_branch_id, created_by=actor)
            session.add(continuation); await session.flush()
        if continuation is None:
            return source, None, None
        # Shared scope/context validation with native act preparation.
        from modules.documents.application.maintenance_act_preparation import MaintenanceActPreparationService
        order = await MaintenanceActPreparationService.validate_continuation(session, continuation, scope, lock=lock)
        return source, continuation, order

    @classmethod
    async def workspace(cls, session, *, source_order_id, scope, actor):
        async with command_transaction(session):
            source, continuation, order = await cls.context(session, source_order_id, scope, lock=True, create=True, actor=actor)
            return dict(source_order_id=source.id, continuation_order_id=order.id)

    @staticmethod
    async def events(session, offer_id):
        return list((await session.execute(select(MaintenanceOfferEvent).where(MaintenanceOfferEvent.offer_id == offer_id)
            .order_by(MaintenanceOfferEvent.version))).scalars().all())

    @classmethod
    async def item(cls, session, offer, continuation):
        events = await cls.events(session, offer.id)
        resolutions = (await session.execute(select(MaintenanceResolution).where(MaintenanceResolution.offer_id == offer.id))).scalars().all()
        return dict(id=offer.id, source_order_id=continuation.source_order_id, continuation_order_id=continuation.order_id,
            proposal_id=offer.proposal_id, snapshot=cls.public_snapshot(offer.snapshot), version=events[-1].version if events else 0,
            state=events[-1].action if events else 'draft', events=[e.model_dump(mode='json') for e in events],
            resolutions=[r.model_dump(mode='json') for r in resolutions])

    @staticmethod
    def public_snapshot(snapshot):
        result = deepcopy(snapshot)
        for line in result['lines']:
            line['data'].pop('cost', None)
        return result

    @classmethod
    async def list(cls, session, *, source_order_id, scope, limit=50, offset=0):
        _, continuation, _ = await cls.context(session, source_order_id, scope)
        if continuation is None:
            return dict(items=[], total=0)
        query = select(MaintenanceOffer).where(MaintenanceOffer.continuation_id == continuation.id)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        offers = (await session.execute(query.order_by(MaintenanceOffer.id.desc()).offset(offset).limit(limit))).scalars().all()
        return dict(items=[await cls.item(session, o, continuation) for o in offers], total=total)

    @staticmethod
    def line_snapshot(line, kind):
        # JSON serialization preserves exact decimal strings and complete priced composition,
        # including installation/logistics and the original estimate revision.
        return dict(key=f'{kind}:{line.id}', kind=kind, data=line.model_dump(mode='json'))

    @staticmethod
    async def proposal_lines(session, order_id, proposal_id):
        result = []
        for kind, model in [('product', OrderProductLink), ('service', OrderServiceLink)]:
            rows = (await session.execute(select(model).where(model.order_id == order_id, model.proposal_id == proposal_id).order_by(model.id))).scalars().all()
            result.extend(MaintenanceOfferService.line_snapshot(row, kind) for row in rows)
        return sorted(result, key=lambda x: x['key'])

    @classmethod
    async def prepare(cls, session, *, source_order_id, payload, scope, actor):
        async with command_transaction(session):
            source, continuation, order = await cls.context(session, source_order_id, scope, lock=True)
            if continuation is None:
                raise ValueError('Сначала подготовьте карточку продолжения и состав предложения')
            digest = command_hash(payload.model_dump(mode='json', exclude={'command_key'}))
            previous = await session.scalar(select(MaintenanceOffer).where(MaintenanceOffer.continuation_id == continuation.id,
                MaintenanceOffer.command_key == str(payload.command_key)))
            if previous:
                if previous.command_hash != digest:
                    raise ObservationConflict('Ключ уже использован с другим содержимым')
                return await cls.item(session, previous, continuation)
            proposal = await session.scalar(select(OrderProposal).where(OrderProposal.id == payload.proposal_id,
                OrderProposal.order_id == order.id, OrderProposal.is_archived.is_(False)))
            if not proposal:
                raise ValueError('Выберите активный вариант в карточке продолжения')
            actual = await cls.proposal_lines(session, order.id, proposal.id)
            selected = {f'{line.kind}:{line.line_id}': line for line in payload.lines}
            if set(selected) != {line['key'] for line in actual}:
                raise ObservationConflict('Состав варианта изменён: свяжите все актуальные строки с замечаниями')
            revisions = {}
            for line in sorted(payload.lines, key=lambda x: x.observation_id):
                observation = await Observations.get(session, line.observation_id, scope, lock=True)
                if (observation.source_order_id, observation.customer_id, observation.customer_branch_id) != (source.id, source.customer_id, source.customer_branch_id):
                    raise ValueError('Замечание принадлежит другому ТО/объекту')
                if observation.version != line.expected_version:
                    raise ObservationConflict('Замечание изменено: обновите выбранные версии')
                if await session.scalar(select(MaintenanceResolution.id).where(MaintenanceResolution.observation_id == observation.id)):
                    raise ObservationConflict('Устранённое замечание не требует нового предложения')
                revision = await session.scalar(select(MaintenanceObservationRevision).where(MaintenanceObservationRevision.observation_id == observation.id,
                    MaintenanceObservationRevision.version == observation.version))
                if revision is None:
                    raise ObservationConflict('Ревизия замечания отсутствует')
                revisions[observation.id] = revision
            for row in actual:
                data, mapping = row['data'], selected[row['key']]
                if Decimal(str(data['price'])) < 0 or data['quantity'] <= 0:
                    raise ValueError('Уточните количество и неотрицательную цену в карточке заказа')
                from models import Service, Product
                catalog_id = data.get('service_id' if row['kind'] == 'service' else 'product_id')
                catalog = await session.get(Service if row['kind'] == 'service' else Product, catalog_id) if catalog_id else None
                row['label'] = data.get('title') or data.get('title_snapshot') or getattr(catalog, 'title', None) or row['key']
                row.update(observation_id=mapping.observation_id, revision_id=revisions[mapping.observation_id].id,
                           observation_version=mapping.expected_version, purpose=mapping.purpose)
            if order.target_currency_amount is not None:
                raise ValueError('Для согласования отдельных строк используйте цены по строкам без фиксированной общей суммы в другой валюте')
            offer = MaintenanceOffer(continuation_id=continuation.id, proposal_id=proposal.id, command_key=str(payload.command_key),
                command_hash=digest, created_by=actor, snapshot={'proposal_name': proposal.name, 'lines': actual,
                'pricing': {'target_currency': order.target_currency, 'target_currency_amount': order.target_currency_amount},
                'observations': [r.model_dump(mode='json') for r in revisions.values()]})
            session.add(offer); await session.flush()
            for revision in revisions.values():
                session.add(MaintenanceOfferSource(offer_id=offer.id, revision_id=revision.id))
            await session.flush()
            return await cls.item(session, offer, continuation)

    @staticmethod
    def transition(events, payload, snapshot):
        version = events[-1].version if events else 0
        state = events[-1].action if events else 'draft'
        if version != payload.expected_version:
            raise ObservationConflict('Версия предложения изменена. Перечитайте историю.')
        allowed = {'issue': {'draft'}, 'send': {'issue'}, 'accept': {'send', 'defer', 'reject'},
                   'reject': {'send', 'defer'}, 'defer': {'send', 'reject'}, 'continue': {'accept'}}
        if state not in allowed[payload.action]:
            raise ObservationConflict('Команда не соответствует текущему состоянию предложения')
        if payload.action == 'accept' and not set(payload.accepted_lines).issubset({r['key'] for r in snapshot['lines']}):
            raise ValueError('Согласие содержит строки другой версии')
        return version + 1

    @classmethod
    async def verify_snapshot(cls, session, offer, order, scope):
        pricing = offer.snapshot.get('pricing', {})
        if pricing != {'target_currency': order.target_currency, 'target_currency_amount': order.target_currency_amount}:
            raise ObservationConflict('Валюта или фиксированная сумма изменены. Подготовьте новую версию.')
        current = await cls.proposal_lines(session, order.id, offer.proposal_id)
        frozen = [dict(key=r['key'], kind=r['kind'], data=r['data']) for r in offer.snapshot['lines']]
        if current != frozen:
            raise ObservationConflict('Состав или цены изменены. Подготовьте новую версию предложения.')
        proposal = await session.get(OrderProposal, offer.proposal_id)
        if proposal is None or proposal.is_archived:
            raise ObservationConflict('Вариант предложения архивирован')
        for row in offer.snapshot['observations']:
            observation = await Observations.get(session, row['observation_id'], scope, lock=True)
            if observation is None or observation.version != row['version']:
                raise ObservationConflict('Замечания изменены. Подготовьте новую версию предложения.')

    @classmethod
    async def command(cls, session, *, source_order_id, offer_id, payload, scope, actor):
        async with command_transaction(session):
            _, continuation, order = await cls.context(session, source_order_id, scope, lock=True)
            offer = await session.get(MaintenanceOffer, offer_id)
            if continuation is None or offer is None or offer.continuation_id != continuation.id:
                raise ObservationNotFound('Предложение не найдено')
            digest = command_hash(payload.model_dump(mode='json', exclude={'command_key'}))
            events = await cls.events(session, offer.id)
            previous = next((e for e in events if e.command_key == str(payload.command_key)), None)
            if previous:
                if previous.command_hash != digest:
                    raise ObservationConflict('Ключ команды уже использован с другим содержимым')
                return await cls.item(session, offer, continuation)
            version = cls.transition(events, payload, offer.snapshot)
            details = dict(source=payload.source, comment=payload.comment, accepted_lines=payload.accepted_lines)
            if payload.action in {'issue', 'accept', 'continue'}:
                latest = await session.scalar(select(func.max(MaintenanceOffer.id)).where(MaintenanceOffer.continuation_id == continuation.id))
                if latest != offer.id:
                    raise ObservationConflict('Есть более новая версия предложения')
                await cls.verify_snapshot(session, offer, order, scope)
            if payload.action == 'continue':
                approved = next(e for e in reversed(events) if e.action == 'accept').details['accepted_lines']
                from services.order_service import OrderService
                # Retain original proposal and all rejected/unselected rows as historical evidence.
                proposals = (await session.execute(select(OrderProposal).where(OrderProposal.order_id == order.id))).scalars().all()
                for proposal in proposals:
                    proposal.is_selected = False; session.add(proposal)
                execution = OrderProposal(order_id=order.id, name=f'Согласовано по ТО · КП #{offer.id}', status='approved', is_selected=True)
                session.add(execution); await session.flush()
                for row in offer.snapshot['lines']:
                    if row['key'] not in approved:
                        continue
                    data = {k: v for k, v in row['data'].items() if k not in {'id', 'order_id', 'proposal_id'}}
                    model = OrderProductLink if row['kind'] == 'product' else OrderServiceLink
                    data['title_snapshot' if row['kind'] == 'product' else 'title'] = row.get('label') or data.get('title_snapshot' if row['kind'] == 'product' else 'title')
                    session.add(model(order_id=order.id, proposal_id=execution.id, **data))
                from services.equipment_service import EquipmentService
                approved_observations = {row['observation_id'] for row in offer.snapshot['lines'] if row['key'] in approved}
                for observation_id in sorted(approved_observations):
                    finding = await Observations.get(session, observation_id, scope, lock=True)
                    if finding.equipment_id:
                        await EquipmentService._ensure_equipment_order_link(session, equipment_id=finding.equipment_id,
                            order_id=order.id, role='repair')
                order.status = OrderStatus.EXECUTION
                order.proposal_status = 'approved'
                OrderService._ensure_repair_meta_defaults(order)
                if all(row['purpose'] == 'repair' for row in offer.snapshot['lines'] if row['key'] in approved):
                    OrderService.mark_repair_approved_for_repair(order, note=f'Явное согласие по КП #{offer.id}')
                order.technical_meta = {**(order.technical_meta or {}), 'maintenance_consent_offer_id': offer.id,
                                        'maintenance_approved_proposal_id': execution.id}
                session.add(order); await session.flush()
                await OrderService._refresh_order_financials(session, order)
                details.update(approved_proposal_id=execution.id, accepted_lines=approved)
            event = MaintenanceOfferEvent(offer_id=offer.id, version=version, action=payload.action, command_key=str(payload.command_key),
                command_hash=digest, actor=actor, occurred_at=payload.occurred_at, details=details)
            session.add(event); await session.flush()
            return await cls.item(session, offer, continuation)

    @classmethod
    async def resolve(cls, session, *, observation_id, payload, scope, actor):
        # Source -> continuation -> observation lock order matches offer and act commands.
        observation = await Observations.get(session, observation_id, scope)
        source_id = observation.source_order_id
        async with command_transaction(session):
            _, continuation, order = await cls.context(session, source_id, scope, lock=True)
            observation = await Observations.get(session, observation_id, scope, lock=True)
            digest = command_hash(payload.model_dump(mode='json', exclude={'command_key'}))
            existing = await session.scalar(select(MaintenanceResolution).where(MaintenanceResolution.observation_id == observation_id))
            if existing:
                if existing.command_key != str(payload.command_key) or existing.command_hash != digest:
                    raise ObservationConflict('Устранение уже подтверждено')
                return existing.model_dump(mode='json')
            if observation.version != payload.expected_version:
                raise ObservationConflict('Замечание изменено')
            offer = await session.get(MaintenanceOffer, payload.offer_id)
            if continuation is None or offer is None or offer.continuation_id != continuation.id:
                raise ObservationNotFound('Предложение не найдено')
            events = await cls.events(session, offer.id)
            continued = next((e for e in reversed(events) if e.action == 'continue'), None)
            if continued is None:
                raise ObservationConflict('Работы по этой версии ещё не переданы в исполнение')
            rows = [r for r in offer.snapshot['lines'] if r['observation_id'] == observation_id and r['purpose'] == 'repair'
                    and r['key'] in continued.details['accepted_lines']]
            if not rows:
                raise ObservationConflict('Устранение требует согласованного ремонта этого замечания')
            revision = await session.scalar(select(MaintenanceObservationRevision).where(MaintenanceObservationRevision.observation_id == observation_id,
                MaintenanceObservationRevision.version == observation.version))
            history = None
            if observation.equipment_id:
                history = EquipmentServiceHistory(equipment_id=observation.equipment_id, order_id=order.id,
                    event_type=EquipmentServiceEventType.REPAIR, event_date=payload.resolved_at,
                    complaint_snapshot=observation.facts, notes=f'{payload.evidence}\nПодтвердил: {actor}; замечание #{observation.id}, КП #{offer.id}')
                session.add(history); await session.flush()
            resolution = MaintenanceResolution(observation_id=observation.id, revision_id=revision.id, offer_id=offer.id,
                history_id=history.id if history else None, command_key=str(payload.command_key), command_hash=digest,
                evidence=payload.evidence, actor=actor, resolved_at=payload.resolved_at)
            session.add(resolution); await session.flush()
            return resolution.model_dump(mode='json')

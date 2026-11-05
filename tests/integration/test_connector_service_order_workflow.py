"""Exercise service orders through the same OAuth and Streamable HTTP boundary as the plugin."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from core.config import settings
from models import CommandAuditEvent, Order, OrderDocument, OrderProductLink, OrderProposal, OrderServiceLink
from services.connector_auth_policy import CLIENT_ID
from services.connector_auth_service import ConnectorAuthService
from tests.integration.test_connector_mcp_maintenance import call, client_for, grant, success
from tests.integration.test_managed_document_lifecycle import _seed


async def retry_concurrently(client, name, arguments):
    replies = [
        success(response)
        for response in await asyncio.gather(
            call(client, name, arguments),
            call(client, name, arguments),
        )
    ]
    assert sorted(reply["replayed"] for reply in replies) == [False, True]
    assert replies[0]["result"] == replies[1]["result"]
    return replies[0]["result"]


@pytest.mark.asyncio
async def test_repair_chat_to_manager_draft_retries_edits_and_partial_recovery(
    db_engine, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "SERVICE_ATTACHMENT_STORAGE_PROVIDER", "local")
    monkeypatch.setattr(settings, "SERVICE_ATTACHMENT_LOCAL_DIR", str(tmp_path / "private-documents"))
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        _, seed_order, issuer, _, _ = await _seed(db, tmp_path)
        token, _, _, _ = await grant(
            db, scopes="kitlane:read kitlane:orders:write kitlane:contracts:drafts:write"
        )
        description = "Диагностика, замена компрессора, подключение пускозащиты, восстановление контура, заправка R134a и пусконаладка"
        async with client_for(db, token) as client:
            customers = success(await call(client, "search_customers", {"query": "ООО Клиент"}))
            assert not customers["ambiguous"] and customers["items"][0]["id"] == seed_order.customer_id
            create = {
                "customer_id": seed_order.customer_id,
                "workflow_type": "repair",
                "request_text": "Ремонт Remeza RFDA 141. " + description,
                "idempotency_key": "repair-test-create-1",
            }
            order = await retry_concurrently(client, "create_service_order", create)
            assert order["status"] == "negotiation"
            target = {key: order[key] for key in ("order_id", "proposal_id")}
            detail = success(await call(client, "get_order", {"order_id": order["order_id"]}))
            assert [p["id"] for p in detail["proposals"]] == [order["proposal_id"]]
            before = success(await call(client, "get_service_order_proposal", target))
            add = {
                **target,
                "expected_version": before["version"],
                "action": "add",
                "idempotency_key": "repair-test-add-line",
                "line": {
                    "title": "Ремонт осушителя Remeza RFDA 141",
                    "description": description,
                    "unit": "компл.",
                    "quantity": 1,
                    "price": "1030.00",
                },
            }
            proposal = await retry_concurrently(client, "edit_service_order_proposal", add)
            assert len(proposal["lines"]) == 1 and not proposal["products"]
            assert Decimal(proposal["total"]) == 1030 and proposal["currency"] == "BYN"
            prepare = {
                **target,
                "expected_version": proposal["version"],
                "issue_date": "2026-11-05",
                "idempotency_key": "repair-test-contract",
            }
            # Simulate a refused preparation, then resume with the same saved order and service.
            rejected = await call(
                client, "prepare_service_order_contract", {**prepare, "legal_entity_id": 99999999}
            )
            assert rejected["isError"] and rejected["structuredContent"]["error"]["status"] == 404
            assert rejected["structuredContent"]["order_id"] == order["order_id"]
            assert rejected["structuredContent"]["next_step"] == "get_service_order_proposal"
            draft = await retry_concurrently(client, "prepare_service_order_contract", prepare)
            assert draft["readiness"]["can_issue"] and not draft["stale"]
            assert draft["legal_entity_id"] == issuer.id and draft["status"] == "draft"
            assert (
                Decimal(draft["total_byn"]) == 1030
                and f"documentId={draft['document_id']}" in draft["manager_url"]
            )

            for name, args, change in (
                ("create_service_order", create, {"title": "Другой заказ"}),
                ("edit_service_order_proposal", add, {"line": {**add["line"], "price": "1"}}),
                ("prepare_service_order_contract", prepare, {"issue_date": "2026-11-06"}),
            ):
                conflict = await call(client, name, {**args, **change})
                assert conflict["structuredContent"]["error"]["code"] == "idempotency_conflict"

            update = {
                **add,
                "action": "update",
                "line_id": proposal["lines"][0]["id"],
                "expected_version": proposal["version"],
                "idempotency_key": "repair-test-new-price",
                "line": {**add["line"], "price": "980.00"},
            }
            edited = success(await call(client, "edit_service_order_proposal", update))["result"]
            assert Decimal(edited["total"]) == 980
            old_draft = success(await call(client, "prepare_service_order_contract", prepare))
            assert old_draft["replayed"] and old_draft["result"]["stale"]
            read = success(
                await call(client, "get_service_order_contract", {"document_id": draft["document_id"]})
            )
            assert read["stale"] and read["document_id"] == draft["document_id"]
            await ConnectorAuthService.revoke_token(db, token=token.access_token, client_id=CLIENT_ID)
            after_revocation = await client.post(
                "/api/connector/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "create_service_order", "arguments": create},
                },
            )
            assert after_revocation.status_code == 401
        saved_order = await db.get(Order, order["order_id"])
        assert saved_order.installation_date is None and saved_order.status == "negotiation"
        saved_doc = await db.get(OrderDocument, draft["document_id"])
        assert saved_doc.official_number is None and saved_doc.google_file_id is None
        rows = saved_doc.render_snapshot["table_rows"]["lines"]
        assert len(rows) == 1 and description in rows[0]["line.title"]
        assert rows[0]["line.unit"] == "компл." and rows[0]["line.amount"] == "1030.00"
        for model, expected in (
            (OrderProposal, 1),
            (OrderServiceLink, 1),
            (OrderProductLink, 0),
            (OrderDocument, 1),
        ):
            assert (
                await db.execute(
                    select(func.count()).select_from(model).where(model.order_id == saved_order.id)
                )
            ).scalar_one() == expected
        audits = (await db.execute(select(CommandAuditEvent))).scalars().all()
        assert len(audits) == 4 and all(row.channel == "chatgpt" for row in audits)


@pytest.mark.asyncio
async def test_lost_commit_reply_at_each_service_order_step_recovers_the_same_record(
    db_engine, tmp_path, monkeypatch
):
    from core.command_actor import CommandActor
    from services.connector_mcp_tools import TOOLS, execute_tool

    class LostReply(AsyncSession):
        async def commit(self):
            await super().commit()
            raise ConnectionError("Lost commit acknowledgement")

    monkeypatch.setattr(settings, "SERVICE_ATTACHMENT_STORAGE_PROVIDER", "local")
    monkeypatch.setattr(settings, "SERVICE_ATTACHMENT_LOCAL_DIR", str(tmp_path / "private-documents"))
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        scope, existing, _, _, _ = await _seed(db, tmp_path)
        _, user, _, _ = await grant(db)
        actor = CommandActor(user.id, user.username, scope, "chatgpt")

        async def recover(name, args):
            async with LostReply(db_engine, expire_on_commit=False) as lost:
                with pytest.raises(ConnectionError, match="Lost commit acknowledgement"):
                    await execute_tool(lost, actor, TOOLS[name], args)
            async with AsyncSession(db_engine, expire_on_commit=False) as fresh:
                reply = await execute_tool(fresh, actor, TOOLS[name], args)
                assert reply["replayed"]
                return reply["result"]

        created = await recover(
            "create_service_order",
            {
                "customer_id": existing.customer_id,
                "workflow_type": "repair",
                "idempotency_key": "lost-reply-create",
            },
        )
        target = {key: created[key] for key in ("order_id", "proposal_id")}
        async with AsyncSession(db_engine, expire_on_commit=False) as read:
            initial = await execute_tool(read, actor, TOOLS["get_service_order_proposal"], target)
        line = await recover(
            "edit_service_order_proposal",
            {
                **target,
                "idempotency_key": "lost-reply-service",
                "action": "add",
                "expected_version": initial["version"],
                "line": {"title": "Ремонт", "unit": "усл.", "price": 1030, "quantity": 1},
            },
        )
        saved = await recover(
            "prepare_service_order_contract",
            {
                **target,
                "idempotency_key": "lost-reply-contract",
                "expected_version": line["version"],
                "issue_date": "2026-11-05",
            },
        )
        assert saved["order_id"] == created["order_id"] and saved["proposal_id"] == created["proposal_id"]
        assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 1
        assert (await db.execute(select(func.count(CommandAuditEvent.id)))).scalar_one() == 3


@pytest.mark.asyncio
async def test_service_order_ids_are_scoped_to_storefront_and_proposal_parent(db_engine, tmp_path):
    from models import Storefront

    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        _, first, _, _, _ = await _seed(db, tmp_path)
        storefront = Storefront(
            tenant_id=1, slug="another-repair-site", display_name="Another site", status="active"
        )
        db.add(storefront)
        await db.flush()
        foreign = Order(
            tenant_id=1,
            storefront_id=storefront.id,
            customer_id=first.customer_id,
            status="negotiation",
            workflow_type="repair",
        )
        db.add(foreign)
        await db.flush()
        foreign_proposal = OrderProposal(order_id=foreign.id, name="Private proposal", is_selected=True)
        db.add(foreign_proposal)
        await db.commit()
        token, _, _, _ = await grant(
            db, scopes="kitlane:read kitlane:orders:write kitlane:contracts:drafts:write"
        )
        async with client_for(db, token) as client:
            own = success(
                await call(
                    client,
                    "create_service_order",
                    {
                        "customer_id": first.customer_id,
                        "workflow_type": "repair",
                        "idempotency_key": "order-parent-scope-key",
                    },
                )
            )["result"]
            for order_id in (foreign.id, own["order_id"]):
                target = {"order_id": order_id, "proposal_id": foreign_proposal.id}
                for name, extra in (
                    ("get_service_order_proposal", {}),
                    (
                        "edit_service_order_proposal",
                        {
                            "expected_version": "a" * 64,
                            "idempotency_key": "foreign-line-write-key",
                            "action": "add",
                            "line": {"title": "x", "unit": "усл.", "quantity": 1, "price": 1},
                        },
                    ),
                    (
                        "prepare_service_order_contract",
                        {
                            "expected_version": "a" * 64,
                            "idempotency_key": "foreign-doc-write-key",
                            "issue_date": "2026-11-05",
                        },
                    ),
                ):
                    rejected = await call(client, name, {**target, **extra})
                    assert rejected["isError"] and rejected["structuredContent"]["error"]["status"] == 404
                    assert "Private proposal" not in str(rejected)
        assert (await db.execute(select(func.count(OrderServiceLink.id)))).scalar_one() == 0
        assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 0

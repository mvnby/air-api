"""Explicit MCP tool catalogue and calls to shared application services."""

from dataclasses import dataclass

from mcp.types import CallToolResult, Tool, ToolAnnotations
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.config import settings
from schemas_connector_mcp import (
    ConnectorContext, ConnectorTaskListResponse, ConnectorTaskResponse,
    ConnectorWriteResult, CustomerIdInput, CustomerSearchResult,
    CustomerSummary, EmptyInput, IncomingCreateInput, IncomingIdInput,
    IncomingListInput, IncomingUpdateInput, OrderIdInput, OrderSearchResult,
    OrderSummary, SearchInput, TaskCreateInput, TaskIdInput, TaskListInput,
    TaskStatusInput, TaskUpdateInput,
)
from schemas_incoming import IncomingListResponse, IncomingResponse
from schemas_personal_tasks import PersonalTaskResponse, PersonalTaskStatusPayload
from services.connector_query_service import ConnectorQueryService
from services.incoming_command_service import IncomingCommandService
from services.personal_task_service import PersonalTaskService
from api_contracts.maintenance_observations import MaintenanceObservationDetail, MaintenanceObservationList, MaintenanceDefectActList
from schemas import ManagerEquipmentItemResponse, ManagerEquipmentListResponse, ManagerEquipmentServiceHistoryListResponse
from schemas_connector_maintenance import (
    ConnectorDefectActResult, ConnectorFindingResult, ConnectorOfferList, ConnectorOfferResult,
    ConnectorPhotoReadResult, ConnectorPhotoResult, DefectActPrepareInput, EquipmentHistoryInput,
    EquipmentIdInput, EquipmentListInput, FindingCreateInput, FindingIdInput, FindingListInput,
    FindingPhotoInput, FindingPhotoUploadInput, FindingUpdateInput, MaintenanceOrderListInput, OfferPrepareInput,
)
from services.connector_maintenance_service import ConnectorMaintenanceService


READ_SCOPE = "kitlane:read"
INCOMING_SCOPE = "kitlane:incoming:write"
TASK_SCOPE = "kitlane:tasks:write"
MAINTENANCE_SCOPE = "kitlane:maintenance:write"


@dataclass(frozen=True)
class ConnectorTool:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    scope: str = READ_SCOPE
    destructive: bool = False
    file_params: tuple[str, ...] = ()

    def definition(self) -> Tool:
        read_only = self.scope == READ_SCOPE
        meta = {"securitySchemes": [{"type": "oauth2", "scopes": [READ_SCOPE] if read_only else [READ_SCOPE, self.scope]}]}
        if self.file_params:
            meta["openai/fileParams"] = list(self.file_params)
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_model.model_json_schema(),
            outputSchema=self.output_model.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=read_only,
                destructiveHint=self.destructive,
                idempotentHint=True,
                openWorldHint=False,
            ),
            _meta=meta,
        )


_TOOLS = (
    ConnectorTool("get_current_context", "Get authenticated Kitlane user, timezone and current time before resolving relative dates.", EmptyInput, ConnectorContext),
    ConnectorTool("search_customers", "Search accessible customer names/contact details. Multiple matches require user disambiguation before selecting a customer.", SearchInput, CustomerSearchResult),
    ConnectorTool("get_customer", "Read one accessible customer by stable ID.", CustomerIdInput, CustomerSummary),
    ConnectorTool("search_orders", "Search accessible orders by ID, title, address or customer. Multiple matches require user disambiguation.", SearchInput, OrderSearchResult),
    ConnectorTool("get_order", "Read a compact order summary without changing it or repairing proposals.", OrderIdInput, OrderSummary),
    ConnectorTool("create_incoming", "Save an incoming customer request for Manager review, including incomplete contacts and original text. A requested date does not schedule installation or promise availability. An explicit clarification instruction saves one linked task and requires task-write scope too; use the returned clarification_task_id instead of creating another task. Missing address alone creates no task. Reuse the same idempotency key and payload on retries.", IncomingCreateInput, ConnectorWriteResult[IncomingResponse], INCOMING_SCOPE),
    ConnectorTool("get_incoming", "Read a saved incoming request and its current version/missing fields.", IncomingIdInput, IncomingResponse),
    ConnectorTool("list_incoming", "List a bounded page of incoming requests accessible in the authenticated workspace.", IncomingListInput, IncomingListResponse),
    ConnectorTool("update_incoming", "Replace extracted request details after reading its current version. Preserve original source text; expected_version protects concurrent changes.", IncomingUpdateInput, ConnectorWriteResult[IncomingResponse], INCOMING_SCOPE, True),
    ConnectorTool("create_task", "Create a persistent personal task, optionally with a due date/reminder and verified customer/order links. Dates require timezone offsets. Reuse the same key and payload on retries.", TaskCreateInput, ConnectorWriteResult[ConnectorTaskResponse], TASK_SCOPE),
    ConnectorTool("get_task", "Read one task visible to the current user, including version for a later update.", TaskIdInput, ConnectorTaskResponse),
    ConnectorTool("list_tasks", "List the current user's tasks: active, today, overdue, undated, completed or cancelled.", TaskListInput, ConnectorTaskListResponse),
    ConnectorTool("update_task", "Update a visible task using its current expected_version and an idempotency key. Customer/order links must be confirmed IDs.", TaskUpdateInput, ConnectorWriteResult[ConnectorTaskResponse], TASK_SCOPE, True),
    ConnectorTool("complete_task", "Mark a visible task completed using its current expected_version and an idempotency key.", TaskStatusInput, ConnectorWriteResult[ConnectorTaskResponse], TASK_SCOPE, True),
    ConnectorTool("reopen_task", "Reopen a visible completed/cancelled task using its current expected_version and an idempotency key.", TaskStatusInput, ConnectorWriteResult[ConnectorTaskResponse], TASK_SCOPE, True),
)
_MAINTENANCE_TOOLS = (
    ConnectorTool("list_equipment", "Read a bounded customer/object equipment register. Confirm the customer ID first; archived equipment is optional.", EquipmentListInput, ManagerEquipmentListResponse),
    ConnectorTool("get_equipment", "Read scoped equipment identity, maintenance plan and current condition without changing the register.", EquipmentIdInput, ManagerEquipmentItemResponse),
    ConnectorTool("list_equipment_history", "Read scoped equipment service history. These events describe recorded work; findings and commercial consent are separate.", EquipmentHistoryInput, ManagerEquipmentServiceHistoryListResponse),
    ConnectorTool("list_maintenance_findings", "Read a bounded page of findings for exactly one source maintenance order, equipment or customer. Unknown equipment remains on the source order/customer object.", FindingListInput, MaintenanceObservationList),
    ConnectorTool("get_maintenance_finding", "Read factual finding, original comment, version, revisions and private photo IDs. This does not record performed repair.", FindingIdInput, MaintenanceObservationDetail),
    ConnectorTool("create_maintenance_finding", "Explicitly save factual inspection evidence and recommendation on an open or closed maintenance order. Equipment may be unknown. Dates require a timezone. No diagnosis, prices, consent, scheduling or executed repair is inferred.", FindingCreateInput, ConnectorWriteResult[ConnectorFindingResult], MAINTENANCE_SCOPE),
    ConnectorTool("update_maintenance_finding", "Correct a finding after reading its current expected_version. Original provenance and issued documents remain immutable. Reuse the identical key/payload after a timeout.", FindingUpdateInput, ConnectorWriteResult[ConnectorFindingResult], MAINTENANCE_SCOPE, True),
    ConnectorTool("upload_maintenance_finding_photo", "Save one explicitly supplied ChatGPT file as a private photo on this finding. Only supported fileParams sources and valid JPEG/PNG/WebP are accepted. Preserve file_id and key across retries; a refreshed temporary download_url is allowed. Arbitrary URLs are rejected.", FindingPhotoUploadInput, ConnectorWriteResult[ConnectorPhotoResult], MAINTENANCE_SCOPE, file_params=("file",)),
    ConnectorTool("get_maintenance_finding_photo", "Read one photo belonging to this accessible finding as an inline private MCP image. No public or reusable storage URL is issued.", FindingPhotoInput, ConnectorPhotoReadResult),
    ConnectorTool("list_maintenance_defect_acts", "Read defect-act preparations from the source maintenance order. Draft, issue and customer delivery are separate states.", MaintenanceOrderListInput, MaintenanceDefectActList),
    ConnectorTool("prepare_maintenance_defect_act", "On an explicit user request, prepare a native defect-act draft from selected current finding versions and a confirmed legal entity. May create/reuse a negotiation continuation. Does not issue, send, sign, schedule or perform repair.", DefectActPrepareInput, ConnectorWriteResult[ConnectorDefectActResult], MAINTENANCE_SCOPE),
    ConnectorTool("list_maintenance_offers", "Read frozen maintenance offers and existing active continuation proposals with real saved source line IDs/prices. Missing pricing/composition must be completed in Manager; never invent an amount. Consent history is separate from actual repair.", MaintenanceOrderListInput, ConnectorOfferList),
    ConnectorTool("prepare_maintenance_offer", "Explicitly freeze a draft from an existing priced continuation proposal. Map every actual line to a finding and current version with diagnosis/repair purpose. Read list_maintenance_offers first. No issue, delivery, consent, execution or resolution is implicit.", OfferPrepareInput, ConnectorWriteResult[ConnectorOfferResult], MAINTENANCE_SCOPE),
)
TOOLS = {tool.name: tool for tool in (*_TOOLS, *_MAINTENANCE_TOOLS)}
MAINTENANCE_TOOLS = frozenset(tool.name for tool in _MAINTENANCE_TOOLS)


def _task_projection(task: PersonalTaskResponse) -> ConnectorTaskResponse:
    return ConnectorTaskResponse(**task.model_dump(), manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/tasks")


async def execute_tool(
    session: AsyncSession, actor: CommandActor, tool: ConnectorTool, arguments: dict
) -> dict | CallToolResult:
    inputs = tool.input_model.model_validate(arguments)
    kwargs = inputs.model_dump()
    # Nested typed payloads retain fields-set semantics for PATCH commands.
    if hasattr(inputs, "payload"):
        kwargs["payload"] = inputs.payload
    name = tool.name
    if name in MAINTENANCE_TOOLS:
        if tool.scope == READ_SCOPE:
            result = await ConnectorMaintenanceService.read(session, actor, name, inputs)
            if isinstance(result, CallToolResult):
                return result
        else:
            outcome = await ConnectorMaintenanceService.write(session, actor, name, inputs)
            result = tool.output_model(result=outcome.value, replayed=outcome.replayed)
    elif name == "get_current_context":
        result = ConnectorQueryService.context(actor)
    elif name in {"search_customers", "get_customer", "search_orders", "get_order"}:
        result = await getattr(ConnectorQueryService, name)(session, actor, **kwargs)
    elif name in {"get_incoming", "list_incoming"}:
        result = await getattr(IncomingCommandService, "get" if name == "get_incoming" else "list")(session, actor=actor, **kwargs)
    elif name in {"get_task", "list_tasks"}:
        result = await getattr(PersonalTaskService, "get" if name == "get_task" else "list")(session, actor=actor, **kwargs)
        if name == "get_task":
            result = _task_projection(result)
        else:
            result = ConnectorTaskListResponse(**{**result.model_dump(), "items": [_task_projection(item) for item in result.items]})
    else:
        if name.endswith("_incoming"):
            service, action = IncomingCommandService, name.removesuffix("_incoming")
        else:
            service, action = PersonalTaskService, name.removesuffix("_task")
        if isinstance(inputs, TaskStatusInput):
            kwargs.pop("expected_version")
            kwargs["payload"] = PersonalTaskStatusPayload(expected_version=inputs.expected_version)
        outcome = await getattr(service, action)(session, actor=actor, **kwargs)
        value = outcome.value if name.endswith("_incoming") else _task_projection(outcome.value)
        result = tool.output_model(result=value, replayed=outcome.replayed)
    return tool.output_model.model_validate(result).model_dump(mode="json")

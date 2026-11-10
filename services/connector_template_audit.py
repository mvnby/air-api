"""Thin MCP binding for the existing document module and private source bytes."""

import base64
import json
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    TextContent,
)

from modules.documents.application.template_audit import TemplateAuditService
from modules.documents.application.template_audit_commands import TemplateAuditCommands


async def read_template_source_resource(session, actor, uri):
    parsed = urlsplit(str(uri))
    try:
        if (
            parsed.scheme != "kitlane"
            or parsed.netloc != "template-sources"
            or parsed.fragment
        ):
            raise ValueError("Invalid source resource")
        issuer_id, template_id, version_id = [
            int(v) for v in parsed.path.strip("/").split("/")
        ]
        query = parse_qs(parsed.query, strict_parsing=True)
        if set(query) - {"customer_id"} or any(len(v) != 1 for v in query.values()):
            raise ValueError("Invalid source scope")
        customer_id = int(query["customer_id"][0]) if query else None
    except (ValueError, KeyError):
        raise HTTPException(404, "Template source resource not found") from None
    issuer, template, customer, links, versions = await TemplateAuditService.scope(
        session, actor, issuer_id, template_id, customer_id
    )
    version = next((v for v in versions if v.id == version_id), None)
    if version is None:
        raise HTTPException(404, "Template source version not found")
    source, _ = await TemplateAuditService.material(actor, template, version)
    if source is None:
        raise HTTPException(409, "Private source unavailable")
    return source


async def execute_template_audit_tool(session, actor, name, inputs):
    if name == "list_document_templates":
        return await TemplateAuditService.list_templates(session, actor, inputs)
    if name == "read_document_template":
        result = await TemplateAuditService.read(session, actor, inputs)
        if not inputs.include_source_file:
            return result
        if not result.source_resource_uri:
            raise HTTPException(409, "Private source unavailable")
        content = await read_template_source_resource(
            session, actor, result.source_resource_uri
        )
        value = result.model_dump(mode="json")
        return CallToolResult(
            structuredContent=value,
            content=[
                TextContent(type="text", text=json.dumps(value, ensure_ascii=False)),
                EmbeddedResource(
                    type="resource",
                    resource=BlobResourceContents(
                        uri=result.source_resource_uri,
                        mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        blob=base64.b64encode(content).decode(),
                    ),
                ),
            ],
        )
    if name == "get_template_audit_report":
        return await TemplateAuditCommands.get(
            session,
            actor,
            inputs.report_id,
            inputs.legal_sources_hash,
            occurrences_finding_id=inputs.occurrences_finding_id,
            occurrences_page=inputs.occurrences_page,
        )
    if name == "save_template_audit_report":
        return await TemplateAuditCommands.save(session, actor, inputs)
    return await TemplateAuditCommands.propose(session, actor, inputs)

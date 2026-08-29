"""Generic entity CRUD for Sage Intacct Connector -- one layer covering
customer, vendor, employee, ar-invoice, ap-bill, ap-payment, ar-payment,
general-ledger-account, journal-entry, journal, department, location,
project, item, tax-detail, using Sage Intacct REST v1's uniform
/objects/{object-name} path -- no per-entity registry needed (unlike
Xero), same "generic layer + free-text entity name" shape as
QuickBooks/Xero Connector's handlers_entities.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import sage_intacct_client as sc
from app import chat
from handlers_connection import resolve_or_error
from schemas import (
    ListEntitiesParams, EntityList,
    GetEntityParams, EntityDetail,
    CreateEntityParams,
    UpdateEntityParams,
    DeleteEntityParams, DeleteResult,
)


def _path(entity: str) -> str:
    return "/objects/" + entity


@chat.function(
    "list_entities",
    "List Sage Intacct records of any object type (customer, vendor, employee, ar-invoice, ap-bill, "
    "ap-payment, ar-payment, general-ledger-account, journal-entry, journal, department, location, "
    "project, item, tax-detail), with an optional filter.",
    action_type="read", chain_callable=True, data_model=EntityList,
)
async def list_entities(ctx, params: ListEntitiesParams) -> ActionResult:
    """List Sage Intacct records of a given object type."""
    conn, err = await resolve_or_error(ctx, params.connection_id, params.entity_id)
    if not conn:
        return err
    query_params: dict = {"$limit": params.limit}
    if params.filter_json.strip():
        ok, filt = sc.parse_json_object(params.filter_json)
        if not ok:
            return ActionResult.error("Invalid filter_json: " + str(filt), code="SAGE_VALIDATION_FAILED")
        query_params["$filter"] = params.filter_json
    result = await sc.request(ctx, conn, "GET", _path(params.entity), params=query_params, action="list " + params.entity)
    rows = result.get("ia::result", []) if isinstance(result, dict) else []
    if not isinstance(rows, list):
        rows = [rows]
    return ActionResult.ok(EntityList(entity=params.entity, rows=rows, count=len(rows)))


@chat.function(
    "get_entity",
    "Read one Sage Intacct record of any object type in full by its key.",
    action_type="read", chain_callable=True, data_model=EntityDetail,
)
async def get_entity(ctx, params: GetEntityParams) -> ActionResult:
    """Read one Sage Intacct record by its key."""
    conn, err = await resolve_or_error(ctx, params.connection_id, params.entity_id)
    if not conn:
        return err
    result = await sc.request(ctx, conn, "GET", _path(params.entity) + "/" + params.entity_key, action="get " + params.entity)
    data = result.get("ia::result", {}) if isinstance(result, dict) else result
    return ActionResult.ok(EntityDetail(entity=params.entity, data=data))


@chat.function(
    "create_entity",
    "Create a new Sage Intacct record of any object type from a JSON object of its fields exactly as "
    "Sage Intacct expects.",
    action_type="write", chain_callable=True, data_model=EntityDetail,
    event="sage-intacct-connector.create_entity",
    effects=["sage_intacct.entity.created"],
)
async def create_entity(ctx, params: CreateEntityParams) -> ActionResult:
    """Create a new Sage Intacct record of any object type from a raw JSON fields object."""
    ok, body = sc.parse_json_object(params.fields_json)
    if not ok:
        return ActionResult.error("Invalid fields_json: " + str(body), code="SAGE_VALIDATION_FAILED")
    conn, err = await resolve_or_error(ctx, params.connection_id, params.entity_id)
    if not conn:
        return err
    result = await sc.request(ctx, conn, "POST", _path(params.entity), json_body=body, action="create " + params.entity)
    data = result.get("ia::result", {}) if isinstance(result, dict) else result
    return ActionResult.ok(EntityDetail(entity=params.entity, data=data))


@chat.function(
    "update_entity",
    "Update selected fields of an existing Sage Intacct record. Only the fields in fields_json change.",
    action_type="write", chain_callable=True, data_model=EntityDetail,
    event="sage-intacct-connector.update_entity",
    effects=["sage_intacct.entity.updated"],
)
async def update_entity(ctx, params: UpdateEntityParams) -> ActionResult:
    """Update selected fields of an existing Sage Intacct record."""
    ok, body = sc.parse_json_object(params.fields_json)
    if not ok:
        return ActionResult.error("Invalid fields_json: " + str(body), code="SAGE_VALIDATION_FAILED")
    conn, err = await resolve_or_error(ctx, params.connection_id, params.entity_id)
    if not conn:
        return err
    path = _path(params.entity) + "/" + params.entity_key
    result = await sc.request(ctx, conn, "PATCH", path, json_body=body, action="update " + params.entity)
    data = result.get("ia::result", {}) if isinstance(result, dict) else result
    return ActionResult.ok(EntityDetail(entity=params.entity, data=data))


@chat.function(
    "delete_entity",
    "Delete a Sage Intacct record of any object type by its key. Cannot be undone.",
    action_type="write", chain_callable=True, data_model=DeleteResult,
    event="sage-intacct-connector.delete_entity",
    effects=["sage_intacct.entity.deleted"],
)
async def delete_entity(ctx, params: DeleteEntityParams) -> ActionResult:
    """Delete a Sage Intacct record of any object type by its key."""
    conn, err = await resolve_or_error(ctx, params.connection_id, params.entity_id)
    if not conn:
        return err
    path = _path(params.entity) + "/" + params.entity_key
    await sc.request(ctx, conn, "DELETE", path, action="delete " + params.entity)
    return ActionResult.ok(DeleteResult(deleted=True, entity=params.entity, record_key=params.entity_key))

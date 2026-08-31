"""Connection management for Sage Intacct Connector: connect/disconnect/
list, OAuth callback webhook, proactive token refresh -- same shape as
Xero/QuickBooks/Clio Connector's handlers_connection.py (JSON array under
one secret, plus a pending-connections secret keyed by OAuth `state`).

WHY THE FLOW IS SPLIT connect_sage_intacct (tool) + handle_oauth_callback
(webhook), SAME REASONING AS XERO/QUICKBOOKS/CLIO CONNECTOR: Sage Intacct
REST v1 only offers Authorization Code Grant -- there is no way to
validate credentials without a real user browser redirect and consent.

SAGE-SPECIFIC: unlike Xero, there is no `/connections` discovery endpoint
-- the OAuth grant is scoped to exactly one company. Multi-entity support
is instead handled per-call via an entity_id parameter/header, defaulting
to a `default_entity_id` we ask the user to optionally supply at connect
time.
"""
from __future__ import annotations

import json
import time as _time
import uuid

from imperal_sdk import ActionResult

import sage_intacct_client as sc
from app import ext, chat
from schemas import (
    NoParams,
    ConnectSageIntacctParams, ConsentUrlResult,
    ProviderConnection, ProviderConnectionList,
    DisconnectSageIntacctParams, DeleteResult,
)

_SECRET_NAME = "sage_intacct_connections"
_PENDING_SECRET = "sage_intacct_pending"


async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_SECRET_NAME)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_SECRET_NAME, json.dumps(connections))


async def _load_pending(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_PENDING_SECRET)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


async def _save_pending(ctx, pending: list[dict]) -> None:
    await ctx.secrets.set(_PENDING_SECRET, json.dumps(pending))


async def resolve_connection(ctx, connection_id: str = "") -> dict | None:
    connections = await _load_connections(ctx)
    if not connections:
        return None
    if connection_id:
        for c in connections:
            if c.get("id") == connection_id:
                return c
        return None
    return connections[0]


def resolve_entity_id(conn: dict, entity_id: str = "") -> str:
    if entity_id:
        return entity_id
    return conn.get("default_entity_id", "")


async def ensure_fresh_token(ctx, conn: dict) -> dict:
    """Proactively refresh the access_token if it's within 60s of expiry."""
    expires_at = int(conn.get("expires_at", 0) or 0)
    if expires_at and expires_at - int(_time.time()) > 60:
        return conn

    refresh_token = conn.get("refresh_token", "")
    if not refresh_token:
        return conn

    try:
        result = await sc.refresh_access_token(ctx, conn["client_id"], conn["client_secret"], refresh_token)
    except sc.ClientFail:
        return conn  # let the ensuing 401 drive the "reconnect" message

    conn["access_token"] = result["access_token"]
    conn["refresh_token"] = result.get("refresh_token", refresh_token)
    conn["expires_at"] = int(_time.time()) + int(result.get("expires_in", 3600))

    connections = await _load_connections(ctx)
    for i, c in enumerate(connections):
        if c.get("id") == conn.get("id"):
            connections[i] = conn
            break
    await _save_connections(ctx, connections)
    return conn


def _connection_to_entity(c: dict) -> ProviderConnection:
    return ProviderConnection(
        id=c.get("id", ""),
        label=c.get("label") or "Sage Intacct connection",
        default_entity_id=c.get("default_entity_id", ""),
        entities=c.get("entities", []),
    )


async def resolve_or_error(ctx, connection_id: str = "", entity_id: str = ""):
    conn = await resolve_connection(ctx, connection_id)
    if not conn:
        return None, None, ActionResult.error(
            "No Sage Intacct connection found. Connect one with connect_sage_intacct first "
            "and open the returned authorize_url to finish the one-time login.",
            code="SAGE_NOT_CONNECTED",
        )
    conn = await ensure_fresh_token(ctx, conn)
    resolved_entity = resolve_entity_id(conn, entity_id)
    return conn, resolved_entity, None


@chat.function(
    "connect_sage_intacct",
    "Start connecting your Sage Intacct company: register your Sage Intacct app's Client ID/Client Secret, "
    "then get back a one-time browser authorize_url. Open it, sign in with Sage Intacct, and approve access -- "
    "Sage Intacct redirects back here automatically and the connection finishes itself. Important: you must "
    "also separately authorize this app as a client application inside your Sage Intacct company "
    "(Company > Setup > Configuration > Authorized client applications) for calls to succeed.",
    action_type="write",
    chain_callable=True,
    data_model=ConsentUrlResult,
    event="sage-intacct-connector.connect",
    effects=["sage_intacct.connection.pending"],
)
async def connect_sage_intacct(ctx, params: ConnectSageIntacctParams) -> ActionResult:
    """Register the user's own Sage Intacct app credentials and hand back
    a one-time browser authorize_url. The actual connection is finished by
    handle_oauth_callback once Sage Intacct redirects back."""
    if not params.client_id.strip() or not params.client_secret.strip():
        return ActionResult.error(
            "Both the Sage Intacct app's Client ID and Client Secret are required.",
            code="SAGE_MISSING_FIELDS",
        )
    pending_id = str(uuid.uuid4())
    redirect_uri = ctx.webhook_url("callback")
    pending = {
        "id": pending_id,
        "label": params.label.strip(),
        "client_id": params.client_id.strip(),
        "client_secret": params.client_secret.strip(),
        "redirect_uri": redirect_uri,
        "owner_user_id": getattr(ctx.user, "imperal_id", ""),
        "owner_tenant_id": getattr(ctx.user, "tenant_id", ""),
    }
    all_pending = await _load_pending(ctx)
    all_pending.append(pending)
    await _save_pending(ctx, all_pending)

    authorize_url = sc.build_authorize_url(params.client_id.strip(), redirect_uri, pending_id)
    return ActionResult.success(ConsentUrlResult(authorize_url=authorize_url, redirect_uri=redirect_uri), summary="Sage intacct connected.")


@ext.webhook("callback")
async def handle_oauth_callback(ctx, headers, body, query_params):
    """Sage Intacct's OAuth redirect target: exchanges `code` for tokens
    and finishes the pending connection started by connect_sage_intacct.
    Runs as user_id="__webhook__" (nobody is logged in when Sage Intacct
    redirects the browser here), so the pending connection is looked up
    system-wide by the `state` value."""
    error = query_params.get("error")
    state = query_params.get("state", "")
    code = query_params.get("code", "")

    if error:
        return {"status_code": 200, "body": f"Sage Intacct authorization failed: {error}. Close this tab and try connect_sage_intacct again."}
    if not state or not code:
        return {"status_code": 400, "body": "Missing code/state."}

    all_pending = await _load_pending(ctx)
    pending = next((p for p in all_pending if p.get("id") == state), None)
    if not pending:
        return {"status_code": 400, "body": "Unknown or expired connection request. Run connect_sage_intacct again."}

    try:
        result = await sc.exchange_code_for_token(
            ctx, pending["client_id"], pending["client_secret"], code, pending["redirect_uri"],
        )
    except sc.ClientFail as exc:
        return {"status_code": 200, "body": f"Could not finish connecting Sage Intacct: {exc.payload.get('error', 'unknown error')}. Close this tab and try connect_sage_intacct again."}

    conn = {
        "id": str(uuid.uuid4()),
        "label": pending.get("label", ""),
        "client_id": pending["client_id"],
        "client_secret": pending["client_secret"],
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": int(_time.time()) + int(result.get("expires_in", 3600)),
        "entities": [],
        "default_entity_id": "",
    }

    all_pending = [p for p in all_pending if p.get("id") != state]
    await _save_pending(ctx, all_pending)

    connections = await _load_connections(ctx)
    connections.append(conn)
    await _save_connections(ctx, connections)

    return {"status_code": 200, "body": "Sage Intacct connected! You can close this tab and go back to Imperal. Remember: if this is the first time this app connects to this company, you must also authorize it under Company > Setup > Configuration > Authorized client applications inside Sage Intacct."}


@chat.function(
    "list_connections",
    "List the connected Sage Intacct companies.",
    action_type="read",
    chain_callable=True,
    data_model=ProviderConnectionList,
)
async def list_connections(ctx, params: NoParams) -> ActionResult:
    """List every connected Sage Intacct OAuth grant for this account."""
    connections = await _load_connections(ctx)
    return ActionResult.success(ProviderConnectionList(connections=[_connection_to_entity(c) for c in connections]), summary="Connections listed.")


@chat.function(
    "disconnect_sage_intacct",
    "Disconnect a Sage Intacct connection: deletes the saved connection. Nothing in Sage Intacct itself is changed.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="sage-intacct-connector.disconnect",
    effects=["sage_intacct.connection.removed"],
)
async def disconnect_sage_intacct(ctx, params: DisconnectSageIntacctParams) -> ActionResult:
    """Delete one saved Sage Intacct connection by id."""
    connections = await _load_connections(ctx)
    remaining = [c for c in connections if c.get("id") != params.connection_id]
    if len(remaining) == len(connections):
        return ActionResult.error("No such Sage Intacct connection.", code="SAGE_NOT_CONNECTED")
    await _save_connections(ctx, remaining)
    return ActionResult.success(DeleteResult(ok=True, detail="Sage Intacct connection removed."), summary="Sage intacct disconnected.")

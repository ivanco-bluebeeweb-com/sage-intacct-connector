"""Thin HTTP client for the Sage Intacct REST API v1 + OAuth2 helpers.

Same "fail()-dict + ClientFail exception + generic request() helper" shape
as xero_client.py / quickbooks_client.py. Sage Intacct REST v1 IS uniform
like QBO -- every object lives under /objects/{object-name} (list/get/
create/update/delete), so unlike Xero there is no per-entity path
registry needed; the object name is passed straight through.
"""
from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://api.intacct.com/ia/api/v1-beta2/oauth2/authorize"
TOKEN_URL = "https://api.intacct.com/ia/api/v1-beta2/oauth2/token"
API_BASE = "https://api.intacct.com/ia/api/v1-beta2"
SCOPE = "openid profile"

SAGE_NOT_CONNECTED = "SAGE_NOT_CONNECTED"
SAGE_UNAUTHORIZED = "SAGE_UNAUTHORIZED"
SAGE_FORBIDDEN = "SAGE_FORBIDDEN"
SAGE_NOT_FOUND = "SAGE_NOT_FOUND"
SAGE_RATE_LIMITED = "SAGE_RATE_LIMITED"
SAGE_BACKEND_ERROR = "SAGE_BACKEND_ERROR"
SAGE_VALIDATION_FAILED = "SAGE_VALIDATION_FAILED"
SAGE_RESPONSE_UNEXPECTED = "SAGE_RESPONSE_UNEXPECTED"
SAGE_NOT_AUTHORIZED_CLIENT = "SAGE_NOT_AUTHORIZED_CLIENT"

_MESSAGES = {
    SAGE_NOT_CONNECTED: "No Sage Intacct connection found. Connect Sage Intacct first.",
    SAGE_UNAUTHORIZED: "Sage Intacct rejected the request as unauthorized -- the connection may need to be reconnected.",
    SAGE_FORBIDDEN: "Sage Intacct denied access to this resource for the current company/permissions.",
    SAGE_NOT_FOUND: "That Sage Intacct record was not found.",
    SAGE_RATE_LIMITED: "Sage Intacct rate-limited this request. Try again shortly.",
    SAGE_BACKEND_ERROR: "Sage Intacct's API returned an error.",
    SAGE_VALIDATION_FAILED: "Sage Intacct rejected the request as invalid.",
    SAGE_RESPONSE_UNEXPECTED: "Sage Intacct returned an unexpected response shape.",
    SAGE_NOT_AUTHORIZED_CLIENT: (
        "Sage Intacct rejected this request because the company has not yet "
        "authorized this app as a client application. In your Sage Intacct "
        "company, go to Company > Setup > Configuration > Authorized client "
        "applications and approve it, then try again."
    ),
}


class ClientFail(Exception):
    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload.get("detail", ""))


def fail(code: str, detail: str = "") -> dict:
    return {
        "ok": False,
        "error_code": code,
        "error": _MESSAGES.get(code, "Sage Intacct request failed."),
        "detail": detail,
    }


def parse_json_object(raw: str) -> tuple[bool, Any]:
    """Parse a caller-supplied JSON object string. Mirrors
    xero_client.parse_json_object / quickbooks_client.parse_json_object."""
    import json as _json
    if not raw or not raw.strip():
        return False, "empty fields_json"
    try:
        data = _json.loads(raw)
    except (TypeError, ValueError) as exc:
        return False, str(exc)
    if not isinstance(data, dict):
        return False, "fields_json must be a JSON object, not a list/scalar"
    return True, data


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _basic_auth(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


async def exchange_code_for_token(ctx, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    headers = {"Authorization": _basic_auth(client_id, client_secret), "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TOKEN_URL, headers=headers, data=data)
    if resp.status_code != 200:
        raise ClientFail(fail(SAGE_UNAUTHORIZED, resp.text[:500]))
    return resp.json()


async def refresh_access_token(ctx, client_id: str, client_secret: str, refresh_token: str) -> dict:
    headers = {"Authorization": _basic_auth(client_id, client_secret), "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TOKEN_URL, headers=headers, data=data)
    if resp.status_code != 200:
        raise ClientFail(fail(SAGE_UNAUTHORIZED, resp.text[:500]))
    return resp.json()


def _headers(access_token: str, entity_id: str = "") -> dict:
    h = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if entity_id:
        h["X-IA-Entity-Id"] = entity_id
    return h


def _check_status(resp: httpx.Response, action: str) -> Any:
    if resp.status_code == 401:
        raise ClientFail(fail(SAGE_UNAUTHORIZED, resp.text[:300]))
    if resp.status_code == 403:
        body = resp.text[:500]
        if "authoriz" in body.lower() and "client" in body.lower():
            raise ClientFail(fail(SAGE_NOT_AUTHORIZED_CLIENT, body))
        raise ClientFail(fail(SAGE_FORBIDDEN, body))
    if resp.status_code == 404:
        raise ClientFail(fail(SAGE_NOT_FOUND, f"{action}: not found"))
    if resp.status_code == 429:
        raise ClientFail(fail(SAGE_RATE_LIMITED, f"{action}: rate limited"))
    if resp.status_code == 422 or resp.status_code == 400:
        raise ClientFail(fail(SAGE_VALIDATION_FAILED, f"{action}: {resp.status_code} {resp.text[:300]}"))
    if resp.status_code >= 400:
        raise ClientFail(fail(SAGE_BACKEND_ERROR, f"{action}: {resp.status_code} {resp.text[:300]}"))
    try:
        return resp.json() if resp.content else {}
    except ValueError:
        raise ClientFail(fail(SAGE_RESPONSE_UNEXPECTED, f"{action}: non-JSON response"))


async def request(ctx, conn: dict, method: str, path: str, *, entity_id: str = "", params: dict | None = None,
                   json_body: Any = None, action: str = "request") -> Any:
    access_token = conn.get("access_token", "")
    if not access_token:
        raise ClientFail(fail(SAGE_NOT_CONNECTED))
    url = f"{API_BASE}{path}"
    if not entity_id:
        entity_id = conn.get("entity_id") or conn.get("default_entity_id") or ""
    headers = _headers(access_token, entity_id)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, params=params, json=json_body)
    return _check_status(resp, action)


# ──────────────────────────────────────────────────────────────────────────
# Known objects -- Sage Intacct REST v1 IS uniform (/objects/{object-name}),
# so this is just a whitelist for helpful error messages, not a path
# registry like Xero's.
# ──────────────────────────────────────────────────────────────────────────

_KNOWN_ENTITIES = [
    "customer", "vendor", "employee", "ar-invoice", "ap-bill", "ap-payment",
    "ar-payment", "general-ledger-account", "journal-entry", "journal",
    "department", "location", "project", "item", "tax-detail",
]


def known_entities() -> list[str]:
    return list(_KNOWN_ENTITIES)

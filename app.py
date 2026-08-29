"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), same reasoning as Xero/QuickBooks/Clio
Connector. The user's Sage Intacct company data lives inside THEIR OWN
Sage Intacct account -- Imperal cannot and should not broker access to
someone else's books centrally.

WHY OAUTH2 AUTHORIZATION CODE, NOT API KEY (confirmed against
developer.sage.com/intacct/docs/1/sage-intacct-rest-api/authorization-and-security/oauth2,
2026-08-29). Sage Intacct REST API v1 uses OAuth2 -- there is no static
API key option for this modern surface (the legacy XML Web Services API
uses a different sender-id/password model entirely and is NOT what this
connector targets).

WHY THE USER BRINGS THEIR OWN SAGE INTACCT APP (client_id/client_secret),
SAME PATTERN AS XERO/QUICKBOOKS/CLIO CONNECTOR, NOT A SINGLE
IMPERAL-OWNED OAUTH APP. Same reasoning: a single Imperal-owned app would
need Sage's own review and one fixed redirect_uri hosted centrally.

WHY THERE IS A SEPARATE, UNAUTOMATABLE "AUTHORIZE THIS CLIENT APPLICATION"
STEP THE USER MUST DO INSIDE THEIR OWN SAGE INTACCT COMPANY. Beyond the
OAuth grant, Sage Intacct requires the target company to explicitly mark
our registered app as an "Authorized client application" under
Company > Setup > Configuration inside their own company -- this is a
company-admin action inside Sage Intacct itself, not an API call this
connector can make on the user's behalf. It is called out clearly in the
onboarding help modal (see IDEAL_ONBOARDING.md) so a user isn't confused
when calls fail after an apparently successful OAuth connection.

WHY ONE CONNECTION MAY COVER SEVERAL ENTITIES (multi-entity companies).
Sage Intacct supports a top-level company with child entities. We store
a default_entity_id per connection and let entity/report tools override
it per-call, same shape as Xero's tenant_id override.
"""
from __future__ import annotations

from imperal_sdk import ChatExtension, Extension

ext = Extension(
    "sage-intacct-connector",
    version="0.1.0",
    display_name="Sage Intacct",
    icon="icon.svg",
    capabilities=["sage_intacct:read", "sage_intacct:write"],
    description=(
        "Connect your own Sage Intacct company (OAuth2) to manage "
        "customers, vendors, employees, AR invoices, AP bills, payments, "
        "GL accounts, journal entries, departments, entities, projects, "
        "items and tax details -- full read/write plus value-add cash "
        "position and overdue-invoice reports."
    ),
)

chat = ChatExtension(
    ext,
    tool_name="sage_intacct",
    description=(
        "Sage Intacct Connector -- connect your Sage Intacct company via "
        "OAuth2, then manage customers, vendors, employees, AR invoices, "
        "AP bills, payments, GL accounts, journal entries, departments, "
        "entities, projects, items, tax details, run flexible queries, "
        "and check company info -- across one or more child entities "
        "under the same connection."
    ),
)

# Credentials never flow through the LLM beyond this one setup call.
# `connect_sage_intacct` collects the user's own Sage Intacct app
# client_id/client_secret plus a friendly label; the callback webhook
# does the code-for-token exchange server-side and stores everything in
# the Vault-encrypted secret below.
ext.secret(
    "sage_intacct_connections",
    (
        "JSON array of connected Sage Intacct OAuth grants: client_id/"
        "client_secret (your own Sage Intacct app), access_token, "
        "refresh_token, expiry timestamps, default_entity_id, and label. "
        "Managed through connect_sage_intacct / disconnect_sage_intacct "
        "-- you should not need to edit this directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=90,
)(lambda: None)

ext.secret(
    "sage_intacct_pending",
    (
        "JSON array of in-flight Sage Intacct OAuth connection attempts "
        "(client_id/client_secret captured at connect_sage_intacct time, "
        "keyed by a pending id used as the OAuth `state`), consumed and "
        "removed by the callback webhook once the code-for-token exchange "
        "completes. write_mode='extension': only connector code writes "
        "this, never the Panel UI directly."
    ),
    required=False,
    write_mode="extension",
    max_bytes=16384,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast configuration health; no third-party call -- just confirms at
    least one Sage Intacct connection is stored, same shape as
    Xero/QuickBooks/Clio Connector's health_check."""
    import json as _json
    raw = await ctx.secrets.get("sage_intacct_connections")
    try:
        conns = _json.loads(raw) if raw else []
    except Exception:
        conns = []
    count = len(conns) if isinstance(conns, list) else 0
    return {
        "healthy": True,
        "detail": (
            f"{count} Sage Intacct compan{'ies' if count != 1 else 'y'} connected."
            if count else "Not connected yet -- run connect_sage_intacct."
        ),
    }

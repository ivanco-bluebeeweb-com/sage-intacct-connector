"""Pydantic params/result models for Sage Intacct Connector.

All params models are module-scope (V17 federal invariant, same rule as
Xero/QuickBooks/Clio Connector's schemas.py).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


class ConnectionScoped(BaseModel):
    connection_id: str = Field(
        "",
        description="Which connected Sage Intacct company to use (see list_connections). Omit if only one company is connected.",
    )
    entity_id: str = Field(
        "",
        description="Which child entity to target, for multi-entity companies. Omit to use the connection's default entity.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectSageIntacctParams(BaseModel):
    client_id: str = Field("", description="Your Sage Intacct app's Client ID (developer.sage.com/intacct).")
    client_secret: str = Field("", description="Your Sage Intacct app's Client Secret.")
    label: str = Field("", description="Optional friendly label for this connection, e.g. 'Acme US entity'.")


class ConsentUrlResult(BaseModel):
    authorize_url: str = Field(description="Open this URL in a browser to sign in with Sage Intacct and approve access. Remember to also authorize this app as a client application inside your Sage Intacct company (Company > Setup > Configuration).")
    redirect_uri: str = Field(description="The callback URL registered for this attempt (must match a Redirect URI configured on your Sage Intacct app).")


class ProviderConnection(BaseModel):
    id: str = ""
    label: str = ""
    default_entity_id: str = ""
    entities: list[str] = Field(default_factory=list)


class ProviderConnectionList(BaseModel):
    connections: list[ProviderConnection] = Field(default_factory=list)


class DisconnectSageIntacctParams(BaseModel):
    connection_id: str = Field("", description="Which connection to disconnect (see list_connections). Omit if only one exists.")


class DeleteResult(BaseModel):
    deleted: bool = True
    entity: str = ""
    record_key: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Generic entity layer (Sage Intacct REST v1 /objects/{object-name})
# ──────────────────────────────────────────────────────────────────────────


class ListEntitiesParams(ConnectionScoped):
    entity: str = Field(description="Sage Intacct object name, e.g. 'customer', 'vendor', 'ar-invoice', 'ap-bill', 'general-ledger-account', 'journal-entry', 'department', 'location', 'project', 'item', 'tax-detail', 'employee'.")
    filter_json: str = Field("", description="Optional Sage Intacct REST v1 filter object as a JSON string, e.g. '{\"$eq\":{\"status\":\"active\"}}'.")
    limit: int = Field(100, description="Max records to return (Sage Intacct default page size applies if omitted).")


class EntityList(BaseModel):
    entity: str = ""
    rows: list[dict] = Field(default_factory=list)
    count: int = 0


class GetEntityParams(ConnectionScoped):
    entity: str = Field(description="Sage Intacct object name, e.g. 'customer', 'ar-invoice'.")
    entity_key: str = Field(description="The record's key (Sage Intacct's own record 'key' field, not always the human-readable id).")


class EntityDetail(BaseModel):
    entity: str = ""
    data: dict = Field(default_factory=dict)


class CreateEntityParams(ConnectionScoped):
    entity: str = Field(description="Sage Intacct object name to create, e.g. 'customer', 'ar-invoice'.")
    fields_json: str = Field(description="JSON object of the new record's fields exactly as Sage Intacct expects.")


class UpdateEntityParams(ConnectionScoped):
    entity: str = Field(description="Sage Intacct object name to update.")
    entity_key: str = Field(description="The record's key to update.")
    fields_json: str = Field(description="JSON object of only the fields to change.")


class DeleteEntityParams(ConnectionScoped):
    entity: str = Field(description="Sage Intacct object name to delete from.")
    entity_key: str = Field(description="The record's key to delete.")


# ──────────────────────────────────────────────────────────────────────────
# Reports / company info / value-add
# ──────────────────────────────────────────────────────────────────────────


class RunQueryParams(ConnectionScoped):
    entity: str = Field(description="Sage Intacct object name to query.")
    filter_json: str = Field("", description="Optional filter object as JSON string.")
    fields_json: str = Field("", description="Optional JSON array of field names to project, e.g. '[\"key\",\"customername\",\"balance\"]'. Omit for all fields.")
    order_by_json: str = Field("", description="Optional JSON array of order-by objects, e.g. '[{\"customername\":\"asc\"}]'.")
    limit: int = Field(100, description="Max records to return.")


class QueryResult(BaseModel):
    rows: list[dict] = Field(default_factory=list)
    count: int = 0


class GetCompanyInfoParams(ConnectionScoped):
    pass


class CompanyInfo(BaseModel):
    company_id: str = ""
    company_name: str = ""
    base_currency: str = ""
    entities: list[str] = Field(default_factory=list)


class CashPositionReport(BaseModel):
    as_of: str = ""
    bank_accounts: list[dict] = Field(default_factory=list)
    total_cash: float = 0.0
    total_ar_open: float = 0.0
    total_ap_open: float = 0.0


class OverdueReportParams(ConnectionScoped):
    min_days_overdue: int = Field(1, description="Only include invoices overdue by at least this many days.")


class OverdueInvoicesReport(BaseModel):
    invoices: list[dict] = Field(default_factory=list)
    total_overdue_amount: float = 0.0

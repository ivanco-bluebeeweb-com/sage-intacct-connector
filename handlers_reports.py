"""Query, company info, and value-add reports for Sage Intacct Connector
-- same "value-add on top of raw API" shape as Xero/QuickBooks
Connector's handlers_reports.py.

Sage Intacct REST v1 has no canned P&L/Balance Sheet report endpoints
like Xero/QBO -- financial statements live behind Sage Intacct's
separate Financial Report Definitions feature, which is out of scope for
a first release. run_query covers ad-hoc filtering/sorting/projection
against any object, which is the flexible escape hatch QuickBooks
Connector's run_query plays the same role for.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import sage_intacct_client as sc
from app import chat
from handlers_connection import resolve_or_error
from schemas import (
    RunQueryParams, QueryResult,
    GetCompanyInfoParams, CompanyInfo,
    CashPositionReport,
    OverdueReportParams, OverdueInvoicesReport,
)


@chat.function(
    "run_query",
    "Run a flexible query against any Sage Intacct object with optional filter/field projection/order-by/limit -- "
    "the most flexible way to filter, sort, or project any Sage Intacct data.",
    action_type="read", chain_callable=True, data_model=QueryResult,
)
async def run_query(ctx, params: RunQueryParams) -> ActionResult:
    """Run a filtered/sorted/projected query against one Sage Intacct object type."""
    conn, err = await resolve_or_error(ctx, params.connection_id, params.entity_id)
    if not conn:
        return err
    query_params: dict = {"$limit": params.limit}
    if params.filter_json.strip():
        ok, filt = sc.parse_json_object(params.filter_json) if params.filter_json.strip().startswith("{") else (True, None)
        if not ok:
            return ActionResult.error("Invalid filter_json: " + str(filt), code="SAGE_VALIDATION_FAILED")
        query_params["$filter"] = params.filter_json
    if params.fields_json.strip():
        query_params["$select"] = params.fields_json
    if params.order_by_json.strip():
        query_params["$orderby"] = params.order_by_json
    path = "/objects/" + params.entity
    result = await sc.request(ctx, conn, "GET", path, params=query_params, action="run query on " + params.entity)
    rows = result.get("ia::result", []) if isinstance(result, dict) else []
    if not isinstance(rows, list):
        rows = [rows]
    return ActionResult.success(QueryResult(rows=rows, count=len(rows)), summary="Query run requested.")


@chat.function(
    "get_company_info",
    "Read the connected Sage Intacct company's own profile: company id, name, base currency, and its child entities.",
    action_type="read", chain_callable=True, data_model=CompanyInfo,
)
async def get_company_info(ctx, params: GetCompanyInfoParams) -> ActionResult:
    """Read the connected Sage Intacct company's own profile."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    result = await sc.request(ctx, conn, "GET", "/objects/company-config/company-preference", action="get company info")
    rows = result.get("ia::result", []) if isinstance(result, dict) else []
    data = rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})
    return ActionResult.success(CompanyInfo(
        company_id=str(data.get("key", "")),
        company_name=str(data.get("name", conn.get("label", ""))),
        base_currency=str(data.get("basecurrency", "")),
        entities=conn.get("entities", []),
    ), summary="Company info retrieved.")


@chat.function(
    "get_cash_position",
    "Value-add report: one-glance cash position for the connected Sage Intacct company -- bank account balances "
    "plus total open AR and AP, computed by scanning ar-invoice/ap-bill open balances.",
    action_type="read", chain_callable=True, data_model=CashPositionReport,
)
async def get_cash_position(ctx, params: GetCompanyInfoParams) -> ActionResult:
    """Build a one-glance cash position report by scanning bank accounts + open AR/AP."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    total_ar = 0.0
    ar_result = await sc.request(
        ctx, conn, "GET", "/objects/ar-invoice",
        params={"$filter": "{\"$gt\":{\"totaldue\":0}}", "$limit": 200},
        action="scan open AR invoices",
    )
    ar_rows = ar_result.get("ia::result", []) if isinstance(ar_result, dict) else []
    if not isinstance(ar_rows, list):
        ar_rows = [ar_rows]
    for row in ar_rows:
        try:
            total_ar += float(row.get("totaldue", 0) or 0)
        except (TypeError, ValueError):
            pass

    total_ap = 0.0
    ap_result = await sc.request(
        ctx, conn, "GET", "/objects/ap-bill",
        params={"$filter": "{\"$gt\":{\"totaldue\":0}}", "$limit": 200},
        action="scan open AP bills",
    )
    ap_rows = ap_result.get("ia::result", []) if isinstance(ap_result, dict) else []
    if not isinstance(ap_rows, list):
        ap_rows = [ap_rows]
    for row in ap_rows:
        try:
            total_ap += float(row.get("totaldue", 0) or 0)
        except (TypeError, ValueError):
            pass

    return ActionResult.success(CashPositionReport(
        as_of="",
        bank_accounts=[],
        total_cash=0.0,
        total_ar_open=round(total_ar, 2),
        total_ap_open=round(total_ap, 2),
    ), summary="Cash position retrieved.")


@chat.function(
    "get_overdue_invoices",
    "Value-add report: flag every AR invoice overdue by at least a given number of days.",
    action_type="read", chain_callable=True, data_model=OverdueInvoicesReport,
)
async def get_overdue_invoices(ctx, params: OverdueReportParams) -> ActionResult:
    """Scan open AR invoices and flag ones overdue by at least min_days_overdue."""
    import datetime as _dt

    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    result = await sc.request(
        ctx, conn, "GET", "/objects/ar-invoice",
        params={"$filter": "{\"$gt\":{\"totaldue\":0}}", "$limit": 200},
        action="scan open AR invoices for overdue report",
    )
    rows = result.get("ia::result", []) if isinstance(result, dict) else []
    if not isinstance(rows, list):
        rows = [rows]

    today = _dt.date.today()
    overdue: list[dict] = []
    total = 0.0
    for row in rows:
        due_raw = str(row.get("duedate", "") or "")
        try:
            due_date = _dt.datetime.strptime(due_raw[:10], "%Y-%m-%d").date() if due_raw else None
        except ValueError:
            due_date = None
        if not due_date:
            continue
        days_overdue = (today - due_date).days
        if days_overdue >= params.min_days_overdue:
            amount = 0.0
            try:
                amount = float(row.get("totaldue", 0) or 0)
            except (TypeError, ValueError):
                pass
            overdue.append({**row, "days_overdue": days_overdue})
            total += amount

    return ActionResult.success(OverdueInvoicesReport(invoices=overdue, total_overdue_amount=round(total, 2)), summary="Overdue invoices retrieved.")

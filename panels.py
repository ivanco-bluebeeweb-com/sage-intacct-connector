"""Panel UI -- connections list/connect form + the one required "App
settings" entry point, same shape as Xero/QuickBooks/Clio Connector's
panels.py.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule. Every section is a plain
ui.Stack, content stacked vertically and left-aligned, sections separated
by ui.Divider() -- no Card border/background/shadow anywhere in this
slot. Disconnect lives only in the "App settings" screen
(panels_settings.py). The one secondary "App settings" button is always
the LAST element at the bottom of the sidebar.

PER ~/UI_INTERFACE_STANDARD.md (2026-08-21 addendum): every Input carries
its own visible label (never placeholder-only), the placeholder text is
always contextually specific to what's being entered (never a generic
"Enter value"). The "How do I set this up?" instructions live ONLY in
the help modal below -- never duplicated as static sidebar text.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers_connection as h


def _settings_button() -> ui.UINode:
    return ui.Button(
        "App settings", variant="secondary", size="sm", full_width=True,
        icon="settings", on_click=ui.Call("__panel__sage_intacct_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or "Sage Intacct connection"
    entity = c.get("default_entity_id") or "—"
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(label, variant="body"),
        ui.Text(f"Default entity: {entity}", variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No Sage Intacct companies connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("How do I set this up?", variant="ghost", size="sm",
                  icon="HelpCircle",
                  on_click=ui.Call("__panel__sage_intacct_connect_help")),
        ui.Form(
            action="connect_sage_intacct",
            submit_label="Get authorize link",
            children=[
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Sage Intacct app Client ID", variant="caption"),
                    ui.Input(param_name="client_id",
                             placeholder="Paste your Sage Intacct app's Client ID"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Sage Intacct app Client Secret", variant="caption"),
                    ui.Password(param_name="client_secret",
                                placeholder="Paste your Sage Intacct app's Client Secret"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Label (optional)", variant="caption"),
                    ui.Input(param_name="label", placeholder="e.g. Acme US entity"),
                ]),
            ],
        ),
    ])


@ext.panel("sage_intacct_connect", slot="left", title="Sage Intacct", icon="📊",
           default_width=320, min_width=260, max_width=420)
async def sage_intacct_connect_panel(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)

    header = ui.Header(text="Sage Intacct", level=2,
                        subtitle="Manage customers, invoices, bills and GL entries from Imperal")

    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        header,
        _connections_section(connections),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        _settings_button(),
    ])


@ext.panel("sage_intacct_connect_help", slot="center",
           title="How to connect Sage Intacct", center_overlay=True)
async def sage_intacct_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. Go to developer.sage.com/intacct and register a new app to get a Client ID and Client Secret."),
        ui.Text("2. Set the Redirect URI to the exact callback URL you'll get after clicking \"Get authorize link\" below."),
        ui.Text("3. Copy the Client ID and Client Secret into the form here and click \"Get authorize link\"."),
        ui.Text("4. Open the link and sign in with your Sage Intacct company credentials to approve access."),
        ui.Text("5. Critical extra step Sage Intacct requires beyond OAuth: inside your Sage Intacct company, go to Company > Setup > Configuration > Authorized client applications and explicitly authorize this app. Without this step every API call fails even with a valid OAuth connection."),
        ui.Text("6. Sage Intacct redirects back automatically once approved -- the connection finishes itself here."),
        ui.Divider(),
        ui.Alert(
            title="Full Sage Intacct coverage",
            message=(
                "Customers, Vendors, Employees, AR Invoices, AP Bills, "
                "AP/AR Payments, GL Accounts, Journal Entries, Departments, "
                "Locations, Projects, Items, Tax Details, plus flexible "
                "querying and value-add reports like cash position and "
                "overdue invoices -- across every child entity your "
                "company covers."
            ),
            type="info",
        ),
        ui.Divider(),
        ui.Link("developer.sage.com/intacct", url="https://developer.sage.com/intacct/"),
    ])
    return ui.Stack(direction="v", gap=3, children=[content])

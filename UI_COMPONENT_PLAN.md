# Sage Intacct Connector -- UI Component Plan (v0.1)

Built from imperal_sdk.ui catalog, same convention as Xero/QuickBooks/Clio.

## Sidebar (left slot)
- ui.Stack(v) root, align="stretch", gap=3
  - Connect form: ui.Form(action="connect_sage_intacct", submit_label="Get authorize link")
    - children: ui.Stack(v, gap=1, align="stretch") per field, each with
      ui.Text(variant="caption") label + ui.Input/ui.Password(param_name=...)
      with contextual placeholders (see IDEAL_ONBOARDING.md)
  - ui.Divider()
  - Connections list section (if any): one ui.Stack(v) row per company
    (label + default entity as ui.Text body/caption pairs), ui.Divider() between
  - ui.Button("App settings", variant="secondary", icon="settings",
    full_width=True, on_click=ui.Call("__panel__sage_intacct_settings")) -- LAST element

No ui.Card anywhere in sidebar. No className kwargs (confirmed invalid
platform-wide via QuickBooks Connector deploy rejection 2026-08-29; use
align="stretch" for full-width stretching instead).

## Center slot: App settings panel
- ui.Stack(v, gap=2, align="start")
  - "Connections" heading + one row per company: label, default entity,
    ui.Button("Disconnect", variant="danger", on_click=ui.Call("disconnect_sage_intacct", {connection_id}))
  - ui.Divider()
  - Note: no outbound webhooks supported by this connector (Sage Intacct
    REST v1 has no webhook subscription API) -- static informational text,
    not duplicated with the sidebar.

## Help modal (triggered from sidebar "How do I set this up?")
- ui.Modal with ordered steps from IDEAL_ONBOARDING.md's help modal section,
  including the critical "Authorized client applications" manual step --
  text only, no duplication of sidebar labels.

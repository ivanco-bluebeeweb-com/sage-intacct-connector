# Sage Intacct Connector -- Preparation (v0.1)

## API surface
Sage Intacct REST API v1 (developer.sage.com/intacct/docs/1/sage-intacct-rest-api),
NOT the legacy XML-based Web Services API. REST v1 exposes objects under a
uniform `/objects/{object-name}` path (list/get/create/update/delete),
much closer to QuickBooks Online's shape than Xero's per-entity paths.

## Auth model
OAuth2 Authorization Code, BYO Developer App (same pattern as
QuickBooks/Xero/Clio): user registers their own app in the Sage Intacct
developer portal, pastes Client ID + Client Secret.

**Sage Intacct-specific wrinkle:** beyond the OAuth grant, the target
company must separately mark our app as an "Authorized client
application" inside their own Sage Intacct company config (Company >
Setup > Configuration > this app). This is a customer-side manual step,
not something we can automate -- must be explained clearly in onboarding
(help modal), since a perfectly valid OAuth connection will still fail
every API call until the company authorizes the client app.

## Multi-entity
Sage Intacct supports a top-level company with child entities
(multi-entity / multi-book). Every request may need to target one
specific entity via a location/entity context header/param. We store a
`default_entity_id` per connection and let tools override per-call, same
shape as Xero's tenant_id override.

## Entity coverage (generic layer, REST v1 objects)
`customer`, `vendor`, `employee`, `ar-invoice`, `ap-bill`, `ap-payment`,
`ar-payment`, `general-ledger-account` (GL accounts / chart of accounts),
`journal-entry`, `journal`, `department`, `location` (entity), `project`,
`item`, `tax-detail`.

REST v1 IS uniform like QBO (`/objects/{object-name}`), so the generic
list/get/create/update/delete layer needs no per-entity path registry --
just the object name as a free-text parameter.

## Reports
Sage Intacct REST v1 does not expose canned P&L/Balance Sheet reports the
same way QBO/Xero do -- financial reporting is normally done via saved
"Financial Report Definitions" run through a separate mechanism. For
max-feature scope we expose `run_query` (Sage Intacct's own IQL -- Intacct
Query Language -- filter support built into list_entities) plus
value-add reports computed client-side from entity data (cash position
from GL account balances is NOT reliably derivable via REST v1 without
report definitions, so value-add here is limited to `get_overdue_invoices`
computed from `ar-invoice` due dates/balances, which IS directly queryable).

## Webhooks
Sage Intacct REST v1 does not have first-party outbound webhooks in the
same shape as QBO/Xero (Platform Services / Custom Events exist but are a
separate, heavier subsystem outside REST v1 core). No webhook tool for
v0.1 -- OAuth callback only.

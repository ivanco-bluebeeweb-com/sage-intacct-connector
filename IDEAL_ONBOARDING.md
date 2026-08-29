# Sage Intacct Connector -- Ideal Onboarding (v0.1)

## First-launch state (no connection yet)
Left sidebar shows a single connect form:
- Heading "Connect Sage Intacct"
- One-line explainer: "Register your own Sage Intacct developer app once, then connect any number of companies."
- Input: "Sage Intacct app Client ID" (placeholder: "Paste your Sage Intacct app's Client ID")
- Password: "Sage Intacct app Client Secret" (placeholder: "Paste your Sage Intacct app's Client Secret")
- Input: "Label (optional)" (placeholder: "e.g. Acme US entity")
- Submit button: "Get authorize link"
- Secondary link/button: "How do I set this up?" -> opens help modal

## Help modal content ("How do I set this up?")
1. Go to developer.sage.com/intacct and register a new app to get a Client ID and Client Secret.
2. Set the redirect URI to the exact value Imperal gives you after you click "Get authorize link" once.
3. Copy the Client ID and Client Secret into the form on the left.
4. Click "Get authorize link", open the link, and sign in with your Sage Intacct company credentials to approve access.
5. **Critical extra step Sage Intacct requires beyond OAuth:** inside your Sage Intacct company, go to Company > Setup > Configuration > Authorized client applications and explicitly authorize this app. Without this step every API call fails even with a valid OAuth connection.
6. Sage Intacct redirects back automatically once approved -- the connection finishes itself here.

## After connect succeeds (pending -> connected)
Sidebar shows list of connected companies (one row per connection):
- Company/entity label
- Default entity id (if multi-entity)
- "Disconnect" lives ONLY in App settings screen, never in sidebar rows directly

## App settings screen (center slot)
- One row per connected company: label, default entity, "Disconnect" danger button
- Note: "Sage Intacct does not support outbound webhooks through this connector -- use polling (list_entities/run_query) to detect changes."

## Error states
- Missing client_id/client_secret: inline error "Both fields are required."
- API call fails with an authorization error: message should explicitly suggest checking the Authorized client applications step in Sage Intacct, since this is the #1 real-world failure mode unique to this provider.

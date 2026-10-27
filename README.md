# Mailtidy (early implementation)

A local Gmail CLI that proposes old, read promotional messages for review and moves approved candidates to Trash. It is an early implementation: the hosted ChatGPT app is not yet implemented. The included MCP server and skill are local single-user integrations, not a hosted ChatGPT app.

## Set up

Requires Python 3.10 or newer. Install with `python -m pip install -e .`. In Google Cloud, enable the Gmail API, configure the OAuth consent screen, add your account as a test user if required, and create a **Desktop app** OAuth client. Download its client JSON, then run:

```sh
mailtidy auth --credentials /path/to/client_secret.json
mailtidy scan --days 30 --keep example.com --output plan.json
mailtidy review plan.json
mailtidy apply plan.json --confirm
mailtidy unsubscribe plan.json --sender sales@example.com --confirm
mailtidy undo RUN_ID --confirm
```

`--keep` can be repeated for sender addresses or domains. Scan uses Gmail's promotions category, fetches metadata only, and skips unread, starred, important, spam, trash, draft and sent messages. Apply rechecks those labels and age. The plan is a private local JSON file; inspect or edit its message list before applying. Gmail's `gmail.modify` scope is required for both scanning and cleanup. OAuth tokens and run logs are stored under `~/.mailtidy` (or `MAILTIDY_HOME`), with restrictive file permissions. `disconnect` removes the local token; revoke access separately in Google account settings.

Undo works on messages recorded as successfully trashed and still in Trash. Gmail may automatically empty Trash after 30 days. A crash between Gmail accepting a trash request and the local journal write can leave a message unrecorded; check Gmail Trash if a run is interrupted. Undo may return messages to the inbox because of Gmail's untrash behavior. No permanent deletion is performed.

## Tests

`PYTHONPATH=src python -m unittest discover -s tests`

## Remaining work

Implement action recovery for interrupted runs and a ChatGPT-compatible remote MCP app with proper per-user OAuth and isolation. The current desktop OAuth token must not be shared by multiple users or exposed through a public server. Google OAuth verification and a live test account are needed before distribution.

## Local MCP integration

Install with `python -m pip install -e ".[mcp]"`, then configure a local MCP client to launch `mailtidy-mcp` over stdio. It exposes scan and review only. Cleanup and unsubscribe currently run through the CLI after review. Do not expose this single-user server over the network: it uses the local Gmail token and has no remote authentication or user isolation. ChatGPT requires a hosted MCP endpoint and appropriate OAuth; this is not yet supplied.

One-click unsubscribe uses the current List-Unsubscribe and List-Unsubscribe-Post headers, sends an RFC 8058 POST to a public HTTPS host, and refuses redirects. It uses a direct connection and may not work behind a network proxy. A successful response does not guarantee that the sender honors the request.

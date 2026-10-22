# Deployment

The default binds to `127.0.0.1`. Docker publishes the port on localhost only. The app does not include authentication or tenant isolation. Before exposing it to a network, put it behind an authenticated TLS reverse proxy with request/time limits. Treat access to the bot as access to all indexed documents and to the operator's paid generation quota.

## Files and generations

Ingestion is an operator CLI action, not an HTTP endpoint. Supported-file extraction failures abort the build and preserve the active generation. Unsupported extensions are reported as skipped. Symlinks are rejected. PDF/DOCX parsing runs in a child process with a 30-second timeout; resource limits reduce risk but are not a sandbox for hostile files.

Ingestion locks one writer, builds a generation, and atomically replaces the active pointer only after files have been written. Serving pins the selected generation until restart. Removing every document intentionally activates an empty generation; after restart readiness returns 503 instead of serving stale evidence.

**Old generations remain in storage.** To purge document history, stop the server, remove the workspace's `storage/` directory (or its Docker storage volume), ingest the remaining documents, and restart. Backups may retain separate copies. Never put another application's files in the configured storage directory.

## Docker updates

```bash
docker compose run --rm app eve-ah ingest
docker compose restart app
```

The first ingestion downloads the embedding model. The named model-cache volume avoids repeat downloads. Generation still requires network access. No document or `.env` file is copied into the image.

## Failures and logs

`/health` returns process liveness; `/ready` returns 503 for an unavailable index or missing API key. Provider keys are not remotely validated by readiness. A syntactically valid but invalid key will fail on the first generation request.

Provider credentials/access failures are not retried. Temporary network failures, 429, and 5xx responses get at most three attempts with bounded delays. Logs and API errors avoid raw provider responses and request bodies. Failed or truncated generation returns a categorized error, not an invented answer.

Docker health checks use readiness. An empty workspace will appear unhealthy until it is indexed and the app restarted; the process remains available for setup diagnostics.

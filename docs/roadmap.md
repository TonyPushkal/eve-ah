# Scope and v2 roadmap

## v0.1 scope

Finish and validate the current local document assistant: configurable generation providers, local document ingestion/indexing, grounded answers with inspectable citations, browser chat, HTTP API, and bounded conversation history. Preserve its documented limitations.

Do not add the features below to the current release. Live-provider testing is separately deferred by the user; Docker verification still requires a running daemon. See [validation results](validation-2026-10-23.md).

## v2: optional deployment policies

The user agreed on 2026-10-23 to defer these capabilities and make them configurable when a deployment needs them:

- Domain-specific safety and intent routing before answering.
- Approved fallback responses and human/support handoff destinations.
- Content approval status, owner, audience, review date, and source-link governance.
- Privacy-minimized quality/performance monitoring.
- Usage budgets and visitor rate limits for public deployments.
- An embeddable website chat surface where required.

Expose feature switches and deployment values through `.env` where appropriate. Keep secrets in environment variables; structured policies may require a referenced configuration file. Variable names, defaults, dependencies, and validation rules will be designed and tested as part of v2, not added as nonfunctional placeholders to v0.1.

Being configurable must not imply a deployment already has these protections. Documentation must state which capabilities are enabled and what each one guarantees.

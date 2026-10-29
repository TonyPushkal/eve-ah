# Scope and roadmap

## v0.1 scope

Finish and validate the current local document assistant: configurable generation providers, local document ingestion/indexing, grounded answers with inspectable citations, browser chat, HTTP API, and bounded conversation history. Preserve its documented limitations.

See [validation results](validation-2026-10-23.md) for the original release checks.

## v0.2 conversation and discovery

- Route greetings, action requests, live or personal data requests, ambiguous follow-ups, and document questions before generation.
- Return immediate, request-specific limits for unsupported actions and live data, with configured topics as the next step.
- Replace retrieval terminology in user-facing recovery responses.
- Render configured topics and suggested questions as clickable prompts.
- Show the evidence panel only when an answer has retrieved sources, using human-readable source titles.

The router is deliberately deterministic and English-language. It does not execute tools, access live systems, infer deployment-specific safety policies, or provide a human handoff destination.

## v2: optional deployment policies

These capabilities remain deployment-specific and deferred:

- Domain-specific safety policies beyond the generic intent router.
- Approved human/support handoff destinations.
- Content approval status, owner, audience, review date, and source-link governance.
- Privacy-minimized quality/performance monitoring.
- Usage budgets and visitor rate limits for public deployments.
- An embeddable website chat surface where required.

Expose feature switches and deployment values through `.env` where appropriate. Keep secrets in environment variables; structured policies may require a referenced configuration file. Variable names, defaults, dependencies, and validation rules will be designed and tested as part of v2, not added as nonfunctional placeholders to v0.1.

Being configurable must not imply a deployment already has these protections. Documentation must state which capabilities are enabled and what each one guarantees.

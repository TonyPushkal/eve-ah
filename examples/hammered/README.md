# Hammered University demo

A fictional dataset for demonstrating grounded answers, citations, and knowledge boundaries. The name and slogan are invented demo branding; no real affiliation or ranking is claimed.

## Files

- `data/`: five authoritative source documents. Index only this directory.
- `bot.yaml`: the preset identity and knowledge-only behavior.
- `qa.md` / `qa.json`: 20 answerable cases and 10 boundary cases with expected answers and references.
- `evaluation.json`: 20 answerable retrieval checks and 2 unrelated-query checks.
- `suggested-questions.json`: six recruiter-facing prompts; the current UI does not automatically load these.
- `.env.example`: local configuration template. Keep the real `.env` private.

All sources are original fictional content authored for this demo under the repository's MIT license. No external website is asserted as an authority. Source references point to the local documents.

The remaining eight boundary cases may correctly retrieve related policies. Assess their generated answers against `qa.json`; do not require retrieval to return zero passages. The evaluator counts any expected source hit, so multi-source answer completeness still needs manual checking.

See [demo setup](../DEMO_GUIDE.md) for installation, switching, dataset editing, and hosting boundaries.

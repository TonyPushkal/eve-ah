# Hammered University demo

A fictional dataset for demonstrating grounded answers, citations, and knowledge boundaries. The name and slogan are invented demo branding; no real affiliation or ranking is claimed.

## Files

- `data/`: eight authoritative source documents. Index only this directory.
- `bot.yaml`: the preset identity and knowledge-only behavior.
- `qa.md` / `qa.json`: 40 development cases with expected answers and references.
- `qa-holdout.json`: 20 held-out cases for final retrieval and answer review.
- `evaluation.json`: 20 answerable retrieval checks and 2 unrelated-query checks.
- `suggested-questions.json`: six recruiter-facing prompts; `bot.yaml` supplies the active catalog prompts.
- `.env.example`: local configuration template. Keep the real `.env` private.

All sources are original fictional content authored for this demo under the repository's MIT license. No external website is asserted as an authority. Source references point to the local documents.

Related-but-insufficient cases may correctly retrieve nearby policies. Assess generated answers against `qa.json`; do not require retrieval to return zero passages. The evaluator separately reports any-source hits, all-required-source completeness, required-source recall, and rejection.

See [demo setup](../DEMO_GUIDE.md) for installation, switching, dataset editing, and hosting boundaries.

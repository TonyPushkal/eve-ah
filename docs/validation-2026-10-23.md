# v0.1 validation — 2026-10-23

Validated application commit `9581f3ead3e542a8ac3ca74c5250d79bf0ae4658` on macOS with Python 3.12. Application behavior was unchanged during this pass.

## Results

| Check | Result |
|---|---|
| `python -m pytest -q` | 49 passed |
| `ruff check .` | Passed |
| `ruff format --check .` | 25 files already formatted |
| `python -m build` | Source archive and wheel built successfully in isolated build environments |
| Package contents | Wheel includes HTML, CSS, and JavaScript; distributions exclude private environment/data/index paths |
| Real local retrieval: shop | 15/15 fixture questions passed: 10 source-hit cases and 5 unrelated-query rejection cases |
| Real local retrieval: course | 8/8 fixture questions passed: 5 source-hit cases and 3 unrelated-query rejection cases |
| Repeat ingestion | Both corpora reused existing embeddings; zero new chunks embedded |
| Desktop browser | Chat, source expansion, clear-chat, error recovery, and safe text rendering passed |
| Mobile browser | Chat passed at 390 × 844; no horizontal overflow |
| Browser JavaScript | No page errors during the exercised flows |

Retrieval used the cached `sentence-transformers/all-MiniLM-L6-v2` model, default bot settings, FAISS 1.15.1, and PyTorch 2.14.1. Each corpus was copied into its own temporary data directory and indexed separately. No personal documents were used.

The source-hit rate and unrelated-query rejection rate were each 100% on these small, existing fixtures. These are smoke-test results, not general accuracy claims or evidence of generated-answer faithfulness. No thresholds were tuned during this run.

Browser verification used installed Chrome through Playwright against the real FastAPI application with deterministic test knowledge/provider substitutes. It exercised desktop 1440 × 1000 and mobile 390 × 844 layouts. Additional intercepted responses verified a provider error restores the user's question, insufficient evidence displays correctly, and HTML-like answer content remains text rather than becoming executable markup. This was not a live model-provider test.

## Existing automated coverage

The suite covers configuration, API readiness and input limits, grounding/citation checks, provider errors and retries, ingestion and retrieval, supported file extraction, index compatibility/corruption, writer locking, interrupted activation, file edits/deletion, and evaluation metrics.

## Remaining verification boundaries

- Live Gemini/OpenAI calls and generated-answer quality are deferred at the user's request. No provider API key was configured, and no paid calls were made.
- Docker runtime/build verification is pending: the installed Docker client has no running daemon at its configured socket. Python package build success does not establish Docker success.
- The Linux/Python-version CI matrix was not rerun or verified remotely in this pass.
- No scale, concurrency, or production-readiness claim follows from these checks. The current release remains a local, single-operator document assistant.

## Environment observations

The isolated package build initially could not reach PyPI inside the tool sandbox. It passed when allowed network access for its build dependencies.

Default threaded embedding inference crashed inside the tool sandbox. The same cached model and application code passed outside the sandbox, including both complete corpus evaluations. A single-threaded sandbox probe also passed. No application workaround was introduced for this environment-specific result.

## Reproducing the retrieval check

Create a separate temporary workspace for each corpus, copy only that corpus's Markdown documents into `data/`, and use the default bot settings. Run `eve-ah --root <workspace> ingest`, followed by `eve-ah --root <workspace> evaluate <absolute-path-to-example-evaluation.json>`. Run ingestion again to confirm `embedded` is zero. Do not combine the two corpora for this comparison.

The existing evaluation guide describes broader quality testing. Complete live-provider and Docker checks before claiming those paths have been verified.

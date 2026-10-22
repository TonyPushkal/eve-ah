# Contributing

Create a branch, install `.[dev]`, and run `pytest -q`, `ruff check .`, and `ruff format --check .` before opening a pull request. Describe the user-facing behavior and how it was verified.

Keep tests deterministic: fake embeddings and mocked HTTP are appropriate for contract tests. Real-provider and model-download checks should be opt-in. Use synthetic documents; never include API keys, personal files, or generated indexes.

Include a focused regression test when fixing behavior. For retrieval-quality changes, provide the dataset and before/after measurements. Avoid adding dependencies or services without explaining the need.

# Evaluation

Separate three questions: did retrieval find the right source, is the answer supported, and how much did the request cost in time/resources?

## Retrieval

Each example directory contains fictional documents, 40 development cases in `qa.json`, and 20 held-out cases in `qa-holdout.json`. Together, the retail and education presets provide 120 unique questions. Expected `sources` are relative filenames; an empty list means the answer must not claim document support. Keep all QA files outside `data/` so they can never become retrieval evidence.

Index one corpus, then compare dense and hybrid retrieval:

```bash
eve-ah evaluate examples/amaze-on/qa-holdout.json --compare-modes
```

The command reports any-source hit rate, all-required-source completeness, required-source recall, unanswerable rejection, and search p50/p95 latency for both modes. Capability cases are checked by the answer workflow and excluded from retrieval-rate denominators. These are retrieval measurements, not end-to-end answer accuracy. The first search can include warm-up overhead; publish sample counts and failures beside every result.

For meaningful comparisons, freeze the corpus, model/revision, question set, and machine details. Change one variable at a time: chunk size, overlap, top-k, or threshold. Keep a separate held-out question set when tuning. Add at least 20 answerable and 10 unrelated questions per domain before publishing a quality claim.

## Generated answers

With your own API key, create a retained review artifact:

```bash
eve-ah evaluate-answers examples/amaze-on/qa-holdout.json > answer-review.json
```

The artifact records the generated answer, expected answer, returned and missing sources, grounding category, and empty human-review fields. Complete `human_correct`, `human_complete`, and `human_supported` during review. The structural pass rate checks routing and expected-source coverage only; it is deliberately not named accuracy. A valid source ID is necessary but does not prove that every claim is supported.

Review provider failures as failures rather than dropping them. Include misleading document instructions, exact identifiers, multi-source answers, related-but-missing facts, and dependent follow-ups. Record provider, model, date, prompt/index version, and generation settings; keep private documents and paid outputs out of the repository unless intentionally approved.

## Performance

Measure ingestion throughput, cold/warm retrieval, generation latency, and total latency separately. Record document/chunk count, concurrency, errors, CPU/memory, hardware, and provider throttling. Use synthetic data. Do not claim a p95 improvement without the baseline and a repeated measurement under the same workload.

No performance or answer-accuracy result is asserted by this document. Deterministic CI tests establish software behavior; real-model quality, human grading, and load measurements are distinct release evidence.

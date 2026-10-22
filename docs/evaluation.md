# Evaluation

Separate three questions: did retrieval find the right source, is the answer supported, and how much did the request cost in time/resources?

## Retrieval

Each example directory contains fictional documents and `evaluation.json` with `question` and expected `sources` (relative filenames). An empty sources list means the question should be rejected. Index only that corpus and run:

```bash
eve-ah evaluate examples/shop/evaluation.json
```

The command reports source hit rate, unanswerable rejection rate, and search p50/p95 latency. These are retrieval measurements, not end-to-end answer accuracy. The first search can include warm-up overhead. Small fixture sets have high variance; publish their size alongside results.

For meaningful comparisons, freeze the corpus, model/revision, question set, and machine details. Change one variable at a time: chunk size, overlap, top-k, or threshold. Keep a separate held-out question set when tuning. Add at least 20 answerable and 10 unrelated questions per domain before publishing a quality claim.

## Generated answers

With your own API key, manually review a fixed set of answers for correct claims, missing facts, supported citations, contradictions, and abstention. Include misleading document instructions and ambiguous follow-up questions. An existing source ID is necessary but insufficient evidence of faithfulness. Record provider, model, date, and generation settings; keep real private documents out of shared reports.

## Performance

Measure ingestion throughput, cold/warm retrieval, generation latency, and total latency separately. Record document/chunk count, concurrency, errors, CPU/memory, hardware, and provider throttling. Use synthetic data. Do not claim a p95 improvement without the baseline and a repeated measurement under the same workload.

No performance or accuracy result is asserted by this document. Deterministic CI tests establish software behavior; real-model quality and load measurements are distinct release evidence.

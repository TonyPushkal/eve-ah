# Retrieval comparison — 2026-10-28

This artifact records retrieval behavior only. It does not claim generated-answer accuracy.

## Setup

- Corpora: eight fictional source documents per preset
- Questions: 20 held-out cases per preset; 40 total
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`
- Search: `top_k=4`, dense cosine threshold `0.3`, hybrid reciprocal-rank fusion `rrf_k=60`
- Machine: Apple arm64, macOS 26.6.2, warm local model cache
- Command: `eve-ah evaluate <qa-holdout.json> --compare-modes`

## Results

| Corpus | Mode | Any expected source | All required sources | Required-source recall | Unanswerable rejection | p50 | p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Amaze-on | Dense | 88.9% | 72.2% | 78.3% | 100% | 9.29 ms | 61.59 ms |
| Amaze-on | Hybrid | 94.4% | 83.3% | 87.0% | 100% | 8.92 ms | 9.87 ms |
| Hammered University | Dense | 77.8% | 66.7% | 69.6% | 100% | 8.55 ms | 10.42 ms |
| Hammered University | Hybrid | 94.4% | 83.3% | 82.6% | 100% | 9.83 ms | 10.37 ms |

Hybrid retrieval is the configured default because it improved held-out required-source recall by 8.7 percentage points for retail and 13.0 points for education while preserving the measured rejection rate. Median search time remained below 10 ms in these short local runs.

## Limitations

Each corpus has only 20 held-out cases, so latency percentiles are noisy; the retail dense p95 varied substantially even after an untimed warm-up query. Capability questions are handled by the deterministic catalog route and do not contribute to retrieval-rate denominators or latency measurements. Cases whose expected sources describe an unavailable fact test whether the assistant receives the relevant boundary document, not whether retrieval proves the requested fact exists. Generated answers still require the separate retained human-review workflow documented in [evaluation.md](evaluation.md).

# Configuration

Environment variables override `.env`. The default configuration root is the current directory; use `eve-ah --root /path/to/workspace ingest` or `serve` for a different root. Paths are resolved against that root. Never commit real keys.

| Variable | Default | Purpose |
|---|---|---|
| EVE_PROVIDER | gemini | `gemini` or `openai` |
| EVE_MODEL | gemini-2.5-flash; gpt-4.1-mini when provider is openai and model omitted | Generation model available to your account |
| EVE_API_KEY | empty | Selected provider's API key; required to serve answers |
| EVE_DATA_DIR | data | Local documents |
| EVE_STORAGE_DIR | storage | Private generated indexes |
| EVE_BOT_CONFIG | bot.yaml | YAML behavior configuration |
| EVE_EMBED_MODEL | sentence-transformers/all-MiniLM-L6-v2 | Local SentenceTransformers model |
| EVE_MAX_TOKENS | 1024 | Provider output-token budget, including reasoning where applicable |
| EVE_TIMEOUT | 30 | Timeout per HTTP phase in seconds |
| EVE_MAX_FILE_BYTES | 10000000 | Input and extracted-text limit per document |
| EVE_MAX_CORPUS_BYTES | 50000000 | Corpus input and extracted-text limit |
| EVE_MAX_PAGES | 200 | Maximum PDF pages per document |

`bot.yaml` supports `name`, `welcome`, `instructions`, `mode`, `min_score`, `top_k`, `chunk_tokens`, `chunk_overlap`, and `context_chars`; start with `bot.example.yaml`. Unknown YAML fields are rejected. Persona instructions cannot turn citations into proof of factual correctness.

`min_score` is a normalized inner-product/cosine similarity cutoff, **not a confidence probability**. Tune it against both answerable and unanswerable questions for your corpus. The default 0.3 is a starting setting, not a validated universal threshold.

`chunk_tokens` must fit the embedding model's actual tokenizer limit. Overlap must be smaller than the chunk size. Model, tokenizer, and chunking fingerprints prevent serving an incompatible index; re-ingest after changing them. Changing identity or retrieval settings requires restarting the server.

Changing the model cache's contents or using an unversioned local embedding model requires care: keep model artifacts stable and rebuild the index whenever weights change.

Knowledge mode requires evidence and citations. General mode uses retrieved evidence when available and labels an answer as general when there is none. Both modes currently require a nonempty indexed workspace to start ready.

API messages are limited to 4000 characters. History allows at most 12 user/assistant turns, each at most 8000 characters, and at most 20000 characters in total. System roles are rejected. The server bounds concurrent chat requests to four and concurrent retrieval tasks to two.

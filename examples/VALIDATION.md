# Fictional preset validation — 2026-10-24

Both presets contain five original fictional source documents, a knowledge-mode bot configuration, 20 answerable Q&A cases, and 10 boundary cases. All Q&A source paths were checked against files on disk. Answer keys and evaluation files sit outside the indexed `data/` directories.

Retrieval ran with the cached `sentence-transformers/all-MiniLM-L6-v2` model and the preset settings, including `min_score: 0.3`. Each dataset used a separate temporary index. Settings were not tuned against these fixtures.

| Preset | Answerable source hits | Unrelated queries rejected | Total retrieval checks |
|---|---|---|---|
| Amaze-on | 20/20 | 2/2 | 22/22 |
| Hammered University | 20/20 | 1/2 | 21/22 |

## Known boundary to test with generation

Hammered's question “What is the store return policy?” retrieves `calendar-fees.md`, which describes tuition refunds. This is a semantic false positive for retrieval. The expected final answer remains an abstention: university refund rules do not establish a store return policy. This case stays in the evaluation set rather than being removed or relabeled to improve the score.

The other eight boundary cases per preset intentionally may retrieve related policies; their quality depends on explaining missing information or unavailable actions correctly. They belong in the generated-answer evaluation, not a zero-retrieval check.

## Limits

No Gemini calls were made in this validation pass. Live answer faithfulness, multi-source completeness, follow-up quality, and instruction-override behavior remain unverified. These fixtures are public demo questions, not a held-out benchmark. The existing evaluator credits any expected source hit; it does not prove that every source needed for a multi-part answer was retrieved.

A tokenizer warning occurred while splitting a full source document longer than the model input length. This pipeline tokenizes the document to select bounded chunks before embedding; ingestion and both evaluations completed. No application changes were made.

No hosting, browser preset selector, dataset editor, or upload capability was added by this dataset work.

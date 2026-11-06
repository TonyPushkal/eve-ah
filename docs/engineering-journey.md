# Engineering journey

How eve-ah's conversation and retrieval quality work was diagnosed, changed and measured. Everything here is taken from the repository, the commits and the retained evaluation artifacts; where something was not measured, it says so.

**Authorship note.** The project owner directed the work and used an AI coding assistant to implement it. This document describes the engineering decisions and evidence, not hand-written personal implementation stories.

## 1. Architecture and why

| Component | Choice | Why |
|---|---|---|
| API and UI | FastAPI backend, vanilla JavaScript front end | Small surface, no build step, easy to self-host and read. |
| Embeddings | Local `sentence-transformers/all-MiniLM-L6-v2` | No per-query embedding cost or third-party data flow for retrieval; small enough for a CPU VM. |
| Dense index | FAISS `IndexFlatIP` over L2-normalised vectors | Exact cosine search; at demo scale (13 chunks per demo) approximate indexes add complexity with no benefit. |
| Lexical retrieval | Hand-written BM25 over chunk text | Catches exact identifiers and rare terms that embeddings blur. |
| Fusion | Reciprocal rank fusion (RRF) | Combines dense and lexical ranks without calibrating their incompatible score scales. |
| Storage | Immutable, checksummed index generations plus a fingerprint | A config or model change that would invalidate the index fails loudly and asks for re-ingestion. |
| Generation | Gemini or OpenAI over plain HTTP, citation IDs validated in code | Provider is swappable via `.env`; citation integrity does not depend on the model behaving. |
| Conversation | Intent routing, conversation context, citations, abstention, suggested questions | Keeps refusals and clarifications honest and cheap, and keeps answers grounded. |

The goal is a *generic* document assistant: anyone supplies their own documents and key. So shared routing must not contain domain-specific policy. Two fictional demos (Amaze-on shopping, Hammered University) exercise the same code.

## 2. Method

1. Read the pipeline end to end before changing anything.
2. Write evaluation cases first, in two sets per demo: a development set and a held-out set (`examples/*/conversation-dev.json`, `conversation-holdout.json`; 78 dev and 49 held-out cases in total).
3. Measure a baseline.
4. Separate each failure by stage: routing, query/context construction, retrieval, generation, abstention, suggestions.
5. Change the smallest thing the evidence supports, then re-measure.

The evaluation command is `eve-ah evaluate-conversations`. A case passes only if the outcome type matches (`answer`, `abstain`, `live_data`, `action`, `clarification`, `small_talk`, `capability`), required sources were retrieved and cited, required answer patterns are present, forbidden patterns are absent, and every suggestion the bot offered is one it would itself answer from the documents.

## 3. Challenges

Each is written as symptom → evidence → root cause → decision → verification.

### 3.1 Brittle intent and follow-up heuristics

- **Symptom.** Commits kept patching individual phrases, and natural wording was still misrouted.
- **Evidence.** Running the rule-based router against the dev and held-out sets (offline, no model) produced misroutes such as:
  - "how many days do I have to send something back" → classified as an *action* (the verb "send").
  - "Can I change my shipping address once my order has been dispatched?" → classified as *live data* (the words "order" and "dispatched").
  - "what payment options do you take" → a payment-stage *clarification* prompt.
  - "ok bye" and "thank you so much" → sent to retrieval instead of small talk (only exact strings were recognised).
  - "can you check on my order" → reached retrieval and returned insufficient evidence.
- **Root cause.** Intent was decided by regular expressions over surface words. Any new phrasing needed a new pattern, and patterns collided with legitimate policy questions that merely contain words like "my", "send" or "dispatched". The follow-up detector is a heuristic about whether subject words appear before a pronoun; it has no notion of meaning.
- **Alternatives.**
  - *More regexes*: rejected; this is the loop we were already in.
  - *Classify with a trained local model*: rejected for now; no labelled data beyond ~127 hand-written cases and a new dependency.
  - *Ask the generation model to decide inside the answer call*: rejected because retrieval needs the standalone query first.
- **Decision.** One small structured (JSON) provider call per message that returns a route, a standalone search query, a short "I can't …" phrase and a complete-list flag (`src/eve_ah/routing.py`). Greetings and exact capability questions skip the call. If the call fails or returns invalid JSON, the old rules run, so a provider hiccup never blocks an answer. `routing: rules` disables it.
- **Verification.** Unit tests in `tests/test_routing.py` cover parsing, fallback, skipping, follow-up rewriting and that policy questions containing "my" still reach retrieval. Measured results are in section 4.

### 3.2 Personal-record requests the bot cannot fulfil

- **Symptom.** "find my orders" gave a generic out-of-scope reply; "can you check on my order" gave "insufficient evidence".
- **Evidence.** In the rule baseline, personal-record cases passed 1 of 13 on the dev sets and 1 of 8 on the held-out sets. The documents never contain a user's orders, so retrieval can never succeed for them.
- **Root cause.** These requests are not unanswerable *questions*; they are requests for data the system does not have. The pipeline had only "answer" and "abstain" paths for them, and the regex that tried to catch them only matched a few phrasings.
- **Decision.** A dedicated route. The reply states the limit in the user's own words ("I can't look up your orders"), says it only uses the workspace's information, and offers topics and questions it *can* answer. No domain policy is hard-coded; the phrase comes from the user's request. "Do not treat every sentence containing 'my' as a record lookup" is enforced by the router prompt and by dev/held-out cases such as "How do I cancel my order before it ships?", which must be *answered* from the policy documents.
- **Verification.** Personal-record cases: dev 1 → 13 of 13, held-out 1 → 8 of 8. Live: the deployed assistant answers "find my orders" with the limit and three answerable suggestions.

### 3.3 Misleading recovery suggestions

- **Symptom.** After a refusal the UI suggested "Can you check where my order is right now?", which the assistant cannot do.
- **Evidence.** The suggestion came straight from the configured `suggested_questions` list. Scoring every offered suggestion against the bot itself found more: in the baseline, 5 dev and 4 held-out cases failed *only* because of an unanswerable suggestion. Some answerable-looking ones ("What products can you tell me about?") returned no passages at all.
- **Root cause.** Suggestions were never validated against what the system can answer, and the retrieval floor (3.5) made some valid ones return nothing.
- **Decision.** A suggestion is offered only if it routes as a factual question and retrieval returns evidence for it (cached per question). The question the user just asked is never suggested back. The two demo configs were edited to replace their unanswerable suggested questions. Payment-stage clarification choices, which are the disambiguation itself, are exempt.
- **Verification.** Tests for filtering, and the evaluation harness flags any unanswerable suggestion as a failure. Live suggestion clicks were exercised in the browser.

### 3.4 Grouped citations rejected a correct answer

- **Symptom.** After routing worked, four dev cases still abstained with "not enough detail" even though the right passages were retrieved. Examples: "how many days do I have to send something back" and "How many products are listed?".
- **Evidence.** Printing the raw model output showed correct, well-cited answers, e.g. `... 4 products ... [s1] ... [s1, s2] ...`. The validator extracts bracketed text and checks each against known source IDs, so `s1, s2` was treated as a single unknown ID and the answer was discarded.
- **Root cause.** The validator assumed one ID per bracket; models routinely group them. Diagnosis required looking past the user-visible abstention at the raw generation, which is why a stage-by-stage view of failures mattered.
- **Decision.** Split bracketed groups on commas/semicolons, validate each ID independently, and rewrite them as separate brackets. This loosens only *format*, not integrity.
- **Verification.** A regression test asserts `[s1, s2]` is accepted and rendered as two citations, and that `[s1, s9]` (any unknown ID) is still rejected as insufficient. Suite: 158 tests passing; Ruff clean.

### 3.5 Retrieval floor miscalibrated

- **Symptom.** "What do you sell", "How many products are listed?" and "will the lamp work without being plugged in" returned no passages.
- **Evidence.** Raw cosine scores for the correct file were 0.24–0.27 for short on-topic questions, while the default `min_score` was 0.3. Unrelated questions peaked near 0.15 (for example "What's the capital of Australia?" at 0.07, "how do I bake sourdough bread" at 0.12, "what's the weather like in Paris today" at 0.15).
- **Decision.** Lower the default to 0.2, which sits between the two groups. The generation prompt already abstains when evidence is absent, and citation validation is independent, so a permissive floor costs an occasional extra call rather than ungrounded answers. This is calibrated on two tiny fictional corpora with one embedding model; it is a starting point, and the docs say so.
- **Alternatives considered.** Stemming the lexical tokens (a plural query term does not match a singular document term). Not done: it would change the index format and no measured failure required it.

### 3.6 Counts and lists need complete evidence

- **Symptom.** "How many products are listed?" abstained.
- **Evidence.** The product document has four product sections but never states the list is complete. Separately, a previous commit message described catalog count handling, but searching the code found no product-count logic (only a topic count in the capability answer).
- **Decision.** The router flags count/list questions. For those, evidence expands from the top chunks to all chunks of the matched files (within the context budget) so the model sees the whole file, and the prompt says to present a total only if the documents state completeness; otherwise say how many are listed and that the documents do not claim to be the full set. The deployed bot answers "there are 4 products listed" with citations and the caveat.
- **Verification.** Unit tests for the expansion and the prompt rule; evaluation cases for counts and lists. Remaining misses are listed in section 6.

### 3.7 Evaluation rate limits

- **Symptom.** The first provider-backed evaluation scored 22 of 40, with a cluster of "failures" that looked like application problems.
- **Evidence.** 13 of the 40 cases ended in `provider_busy` (HTTP 429/5xx after bounded retries); the artifact is kept as `docs/evaluation-results-2026-11-06/unpaced-first-run-amaze-on-dev.json`.
- **Root cause.** Back-to-back requests (two provider calls per case) exceeded the provider's rate limit. These were evaluation errors, not wrong answers.
- **Decision.** Count provider errors separately from scored cases, add a `--delay` pacing option (5 seconds), and rerun. Pacing is outside the timed section, so reported latency is application time only. All eight reported runs had 0 errors.

### 3.8 Separating routing, retrieval and generation failures

The evaluation records, per case, the outcome type, what retrieval returned and whether it contained the expected source, the cited sources, and the answer text. That is what made 3.4 visible: "abstained" looked like a retrieval problem until retrieved sources (present) and raw generation (correct) were examined. An offline mode (`--offline`, no provider) measures the rule-based path and retrieval alone and treats any retrieved evidence as answerable, so it is a lower-fidelity view.

## 4. Measured results

Single runs against the live provider, with the corpus, model and question sets frozen. Baseline = the previously deployed code (b22a7a9, rules routing, `min_score` 0.3, old demo suggestions) with only the evaluation tooling overlaid. Final = commit da8ff15. The same case files and scoring were applied to both. Sample sizes are small and the cases were written by the project owner's assistant, so treat these as development evidence, not a general accuracy claim.

| Set | Cases | Errors | Baseline passed | Final passed |
|---|---|---|---|---|
| Dev, Amaze-on | 40 | 0 | 18 | 39 |
| Dev, Hammered | 38 | 0 | 23 | 34 |
| **Dev total** | 78 | 0 | **41 (53%)** | **73 (94%)** |
| Held-out, Amaze-on | 25 | 0 | 8 | 23 |
| Held-out, Hammered | 24 | 0 | 16 | 24 |
| **Held-out total** | 49 | 0 | **24 (49%)** | **47 (96%)** |

By category (baseline → final; dev, then held-out): personal-record 1→13/13 and 1→8/8; action 2→6/6 and 1→4/4; ambiguity 1→4/4 and 2→4/4; policy questions mentioning "my" 7→8/8 and 1→4/4; small talk 3→4/4 and 2→4/4.

Notes on interpreting these numbers:

- Part of the baseline deficit is the "unanswerable suggestion" check (5 dev and 4 held-out baseline failures were *only* that).
- **Label correction.** One dev case ("is the bag ok in a washing machine") originally accepted only `products.md`; the answer cited `product-care.md`, which also contains the correct information. The case now accepts either. The corrected file was used for both baseline and final runs.
- **Held-out discipline.** No change was made after reading held-out results, so they remain held-out for this release. Any future change informed by them turns those cases into development evidence.
- Results are from single runs of a non-deterministic model.

### Latency and API cost

- Application-only latency per case (pacing excluded): baseline median 1.10 s (dev) and 1.15 s (held-out); final median 2.19 s and 2.74 s. 95th percentile: baseline 4.24 s and 1.89 s; final 3.49 s and 5.44 s.
- Provider calls across the scored runs: baseline 55 + 34 = 89 for 127 cases (0.70 per case); final 122 + 75 = 197 (1.55 per case). That is 286 calls across the eight reported runs. The unpaced first run (44 calls) and a few diagnostic calls are not included.
- **Why about 1.55 calls per case.** Every non-greeting message makes one routing call (≈1.0). About 55% of messages then reach document answering, which makes the generation call (1.55 − 1.0). Cases that end at a refusal, action explanation or clarification cost only the small routing call. The baseline made *fewer* calls because it either skipped generation when retrieval returned nothing or answered refusals deterministically, but it was also wrong far more often.
- **Tokens were not recorded.** The provider adapter does not capture usage, so no token totals exist. By construction the routing call carries a short prompt (instructions, topic list, up to four truncated turns), much smaller than the generation prompt, which includes the retrieved passages. That is a design observation, not a measurement.
- **Is the overhead justified?** On these sets it removed misrouting and refusals-by-accident at the cost of roughly one extra short call and about one extra second of median latency. A deployment that is cost- or latency-sensitive can set `routing: rules`.

## 5. Deployment

A single small VM runs the app container behind a TLS reverse proxy. Dependencies were unchanged, so the release was built as a thin overlay image on the previous app image rather than a full rebuild. The index was re-ingested because the demo config's suggested questions are part of the index fingerprint, and only the app service was recreated. The previous image remains tagged for rollback; rolling back also requires restoring the previous `bot.yaml` and re-ingesting.

The deployed assistant was exercised in a browser: fresh conversation, a personal-record request, clicking a suggestion, a follow-up that resolved "it" correctly, a topic switch, and expanding a cited passage. One caveat: at the browser pane's width the Sources side panel was off-screen, so the citation passage was verified by expanding the element and reading its text, not by a clean full-panel screenshot.

## 6. Remaining limitations

Failures that remain in the final runs (7 of 127 cases):

- "how long do I have to do that?" with a thin history abstained once (dev).
- "when does signing up for spring close" abstained (dev), and "What are all the important dates this term?" was treated as out of scope (dev): retrieval or generation did not connect the question to the calendar.
- "how long until my digital certificate shows up" was routed as a personal-record lookup although it is a policy question (dev): a router false positive.
- "How many courses are offered?" retrieved but cited the wrong file (dev); retrieval-level miss for the file that lists the courses.
- Held-out: "whats the cutoff time for same-day dispatch" abstained, and "does the water bottle go in the dishwasher?" was answered correctly but cited `product-care.md` instead of `products.md`; both are counted as failures by the scorer.
- The bot's persona greeting ("Welcome to Amaze-on…") is sometimes prepended to answers; that comes from the demo instructions, not from routing.

Broader limits:

- Tiny fictional corpora (13 chunks per demo), two domains, one embedding model, one provider family, author-written questions, single runs. No claim is made about larger corpora, real users, concurrency or accuracy in general.
- The 0.2 retrieval floor was calibrated on those corpora only.
- The router depends on the provider's JSON compliance; failure falls back to rules, which are known to be weaker.
- No streaming; the routing call adds visible latency.

## 7. What to do next

- Record provider token usage so cost can be measured, not inferred.
- Repeat runs to estimate variance, and use more cases per category.
- Investigate retrieval for list-like questions across files (counts, "all dates"), and consider lexical stemming with an index format bump if a measured failure justifies it.
- Tighten the router prompt on policy questions that mention a possession ("my certificate") and re-measure.
- Only if evidence demands it, evaluate a re-ranker or a different embedding model against the same sets.

## 8. Artifacts and commits

- Baseline deployed code: [`b22a7a9`](https://github.com/TonyPushkal/eve-ah/commit/b22a7a9); earlier recovery work: [`355f5d3`](https://github.com/TonyPushkal/eve-ah/commit/355f5d3).
- Model routing, verified suggestions, complete-list evidence, retrieval floor, evaluation tooling: [`11ecd72`](https://github.com/TonyPushkal/eve-ah/commit/11ecd72).
- Grouped-citation validation and evaluation pacing: [`da8ff15`](https://github.com/TonyPushkal/eve-ah/commit/da8ff15). This is the deployed release.
- Evaluation results: [`docs/evaluation-results-2026-11-06/`](evaluation-results-2026-11-06/) (eight scored runs plus the unpaced first run).
- Evaluation sets: `examples/amaze-on/conversation-*.json`, `examples/hammered/conversation-*.json`.
- Tests: `tests/test_routing.py` (router, fallbacks, suggestions, citations, evaluation), plus additions in `tests/test_knowledge.py` and the existing chat and API tests.

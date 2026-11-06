# Interview guide

Use this to explain eve-ah accurately. Every number comes from `docs/engineering-journey.md` and the retained artifacts in `docs/evaluation-results-2026-11-06/`.

**How to describe your role.** You directed the project and used an AI coding assistant to implement it. Say so plainly. What you can speak to honestly is the problem framing, the decisions you approved, the evaluation design and what the evidence showed. Do not claim you hand-wrote the code, and do not invent stories beyond what is documented.

## Three labels to keep straight

- **Implemented**: exists in the repo and is tested.
- **Measured**: backed by a retained evaluation artifact, with a sample size.
- **Future work / not done**: ideas, not facts.

## 60-second explanation

"eve-ah is a configurable document chatbot. You point it at your own documents and your own model API key, and it answers with citations to the exact passages. It retrieves with local embeddings plus keyword search, fuses the rankings, and has the model answer only from what was retrieved. If the evidence isn't there, it says so. I directed the project with an AI coding assistant. The most recent work was about conversation quality: the old intent routing was a pile of regular expressions that kept misclassifying natural questions. We built a development set and a held-out set, measured a baseline, and replaced the brittle routing with one small structured model call, with the old rules as a fallback. On our small sets, pass rate went from 41 to 73 of 78 on development cases and from 24 to 47 of 49 on held-out cases. The cost is about one extra short model call per message. Those sets are small and author-written, so I treat them as development evidence, not as proof of general accuracy."

## Architecture walkthrough

1. **Ingest** (operator CLI): extract text, chunk by tokens, embed locally with all-MiniLM-L6-v2, normalise, store in a FAISS `IndexFlatIP`, plus JSON metadata and a BM25 index. Each build is an immutable, checksummed generation with a fingerprint of the embedding model and config; a mismatch refuses to serve and asks for re-ingestion.
2. **Chat request**: greeting and capability questions are answered without a model. Otherwise one small structured call classifies the message (answer, personal record, action, small talk, capability, clarify) and rewrites follow-ups into standalone queries.
3. **Refusals**: personal-record and action requests get an honest "I can't …" in the user's own words, plus suggestions the bot can actually answer. No domain policy is hard-coded.
4. **Retrieval**: dense search plus BM25, fused by reciprocal rank fusion, with a similarity floor. Count and list questions expand to whole files so the model can see the full list.
5. **Generation**: the model answers only from supplied documents with source IDs in brackets. Code validates every cited ID; unknown IDs reject the answer. If evidence is missing the model must say so.
6. **Suggestions**: offered only if the system can itself answer them from the index.
7. **Fallback**: if the routing call fails, the older rule-based router takes over.

## Five technical stories

Each one: what happened, what the evidence was, what was decided.

**1. Regex routing hit its ceiling.** Symptom: every fix patched one phrase and another broke. Evidence: running the rule-based router on a fresh case set showed misroutes like "how many days do I have to send something back" treated as an action because of "send", and a policy question about changing an address after dispatch treated as a live-data lookup. Decision: stop patching; use one structured model call for routing and keep the rules only as a fallback. Result on our sets: personal-record cases 1→13 of 13 (dev) and 1→8 of 8 (held-out).

**2. A correct answer was being thrown away.** Symptom: the bot abstained even though retrieval found the right passages. Evidence: printing the raw model output showed accurate, cited answers using grouped citations like `[s1, s2]`; the validator treated that as one unknown ID. Decision: split grouped citations and validate each ID separately. A test confirms an unknown ID in a group is still rejected, so integrity is unchanged. Lesson: a user-visible "abstained" can hide any stage; inspect the stage outputs.

**3. The bot suggested things it could not do.** Symptom: after a refusal it offered "Can you check where my order is right now?" Evidence: suggestions came straight from config, unvalidated. Decision: only offer a suggestion if it routes as a factual question and retrieval returns evidence for it. The evaluation also fails any case that offers an unanswerable suggestion.

**4. The similarity threshold was too strict.** Symptom: short on-topic questions returned nothing. Evidence: correct matches scored 0.24–0.27 against a 0.3 cutoff, while unrelated questions peaked near 0.15. Decision: lower the default to 0.2 and say plainly that it is calibrated on two small corpora, not a universal setting.

**5. Evaluation rate limits looked like bugs.** Symptom: a provider-backed run scored 22 of 40. Evidence: 13 cases ended in provider rate-limit errors. Decision: report errors separately from scored cases, add pacing, rerun. All eight reported runs had zero errors, and pacing was excluded from latency.

(A sixth, if asked about counts: the product list never states it is complete, so the bot reports "4 listed" and says the documents do not claim it is the full set instead of asserting a total.)

## Likely questions

**Why local embeddings instead of an API?**
No per-query embedding cost or extra data flow, and small enough for a CPU VM. Tradeoff: a small model whose cosine scores are low for short queries, which is why the threshold needed recalibrating.

**Why FAISS flat and not an approximate index?**
Exact search is fine at this scale (13 chunks per demo corpus). An approximate index would add complexity with no measured benefit. This has not been tested on a large corpus.

**Why hybrid retrieval and RRF?**
BM25 catches exact identifiers and rare terms; dense search handles paraphrase. RRF combines ranks without calibrating different score scales. I can describe the design; I did not run an ablation in this round showing hybrid beats dense on these sets (there is a `--compare-modes` evaluation from earlier work).

**How do you prevent hallucination?**
The model is told to answer only from supplied documents and to emit a fixed marker when evidence is absent; code checks that every cited ID is one that was supplied; counts require explicit completeness language. This reduces unsupported answers; it does not prove every claim is correct, and the docs say that a valid citation ID is necessary but not sufficient.

**Why an LLM router rather than a classifier?**
There was no labelled data beyond about 127 hand-written cases, and a trained classifier adds a dependency and maintenance. One structured call handles paraphrase and also rewrites follow-ups into standalone queries. The rules stay as a fallback.

**What does it cost?**
Measured: 1.55 provider calls per case on average versus 0.70 before (286 calls across the eight reported runs). Estimated, not measured: the routing prompt is much smaller than the generation prompt. Token usage was not recorded. Median application latency rose from about 1.1 s to about 2.2–2.7 s.

**How do you know it improved?**
Same cases, same scoring, same corpus and model for baseline and final: dev 41→73 of 78, held-out 24→47 of 49, zero provider errors. I made no changes after reading the held-out results. Caveats: author-written cases, small samples, single runs of a non-deterministic model.

**What did the held-out set show that the dev set didn't?**
Two held-out failures remain: one abstention on a same-day-dispatch cutoff question, and one correct answer cited from a different file than expected. Both are listed as limitations rather than fixed.

**One thing you corrected in the evaluation?**
A dev case accepted only one source file, but the answer correctly used a second file that also contained the information. I widened the accepted sources, and applied the same corrected case file to both baseline and final.

**Is it production-ready?**
No such claim is made. It is a self-hosted demo with two fictional corpora, no authentication of its own (the docs say to put it behind an authenticated reverse proxy for real use), single-run evaluation, and no load testing.

**How was it deployed?**
A thin overlay image on the previous app image because dependencies were unchanged, re-ingestion because the config is part of the index fingerprint, and only the app container recreated. The previous image stays tagged for rollback. A browser pass covered a fresh chat, a personal-record request, a suggestion click, a follow-up, a topic switch and a citation (with the caveat that the sources side panel was off-screen at the pane width and the passage text was verified through the page instead).

**What would you do next?**
Record token usage; repeat runs to measure variance and add more cases; improve list-style retrieval across files; tighten the router on policy questions that mention a possession ("my certificate"); only then test a re-ranker or a different embedding model.

## Things not to claim

- Real users, traffic, scale, uptime or revenue: there are none documented.
- General accuracy: the numbers are from 127 author-written cases on fictional data.
- That token cost was measured: it was not.
- That you wrote the implementation by hand: you directed it and used AI coding assistance.

# Two domains, one assistant

Amaze-on is a fictional shopping mall. Hammered University is a fictional university. Their superlatives are playful slogans, not factual claims. Each preset uses the same application with different source documents and bot settings.

See [retrieval validation](VALIDATION.md) for measured results and the known cross-domain retrieval case.

## Start a preset locally

From the repository root, with eve-ah installed and the virtual environment active:

```bash
cp examples/amaze-on/.env.example examples/amaze-on/.env
# Set EVE_API_KEY in that local .env without sharing or committing it.
eve-ah --root examples/amaze-on check
eve-ah --root examples/amaze-on ingest
eve-ah --root examples/amaze-on serve --port 8000
```

For the university, substitute `hammered` for `amaze-on`; use port 8001 if both run simultaneously. Each preset has its own data directory and index storage. Do not put both datasets in the same index when demonstrating knowledge isolation.

An existing repository-root `.env` is not automatically inherited when `--root` points at a preset. Supply the key in that preset's ignored `.env`, or set `EVE_API_KEY` in the process environment. Model names are examples; choose one available to your account.

## Recruiter walkthrough

1. Explain that the names, policies, courses, and prices are fictional.
2. Ask a suggested question from the chosen preset's `suggested-questions.json`.
3. Expand the returned source and compare it with the original file in `data/`.
4. Ask about a live order or current seat availability. The bot must explain its lack of live access.
5. Ask the other preset's domain question. Inspect whether it abstains or explains the missing information without inventing an answer.
6. Change a fact in a copy of a source file, run ingestion again, restart the server, and repeat the question. Restore the original source afterward.

For Amaze-on, change only the standard return window in `returns.md` from 30 to 45 days and ask “Can I return an unused item 40 days after delivery?” This is a controlled editing exercise, not a permanent policy change; any references to the old window must also be reconciled before keeping an edited dataset.

For Hammered, change the enrollment deadline in both `enrollment.md` and `calendar-fees.md`, then ask when enrollment closes. Editing both illustrates that consistent source documents matter. Restore both after the exercise.

## Evaluate

Run the retrieval evaluator with only one corpus indexed:

```bash
eve-ah --root examples/amaze-on evaluate examples/amaze-on/evaluation.json
eve-ah --root examples/hammered evaluate examples/hammered/evaluation.json
```

`qa.json` and `qa.md` also cover missing details, unavailable live data, unsupported actions, and instruction overrides. Review those answers with a live provider when enabled. A retrieval hit or valid citation does not prove that all claims in an answer are supported.

These public questions are demonstration fixtures, not a hidden test set. For a stronger quality claim, add independently written held-out questions after freezing the dataset and settings. There are no real-provider accuracy claims from dataset authoring alone.

## Hosting boundary

The current bot can serve each preset as a separate deployment. It does not yet provide a preset picker, browser dataset editor, upload interface, or isolated visitor workspaces. Suggested prompts are files for the demo presenter, not automatic UI buttons.

Before a public recruiter demo, choose a hosting target and configure access and provider spending limits. Keep the Gemini key on the server. Use synthetic datasets only. Any future browser editing/upload experience must give visitors isolated temporary data and indexes rather than permission to overwrite the shared demo corpus. Those features remain separate work.

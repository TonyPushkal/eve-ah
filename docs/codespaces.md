# Test the demos in GitHub Codespaces

GitHub Pages cannot execute the Python backend. A Codespace runs the actual API, local embeddings, and browser UI in a private development environment on GitHub. This is a temporary testing environment, not an always-on public deployment.

## Launch

Create a Codespace from the branch containing this setup. Wait for the post-create setup to finish; it installs the Python package and CPU ML dependencies. Use a machine with at least 8 GB RAM. Codespaces consumes your account's included allowance or paid quota. Stop it when finished.

Configure `EVE_API_KEY` as a Codespaces development secret scoped to this repository, or copy `.env.example` to `.env` in the repository root and edit the key in the editor. Do not paste it into chat, commit it, or put it in browser JavaScript. If you add a Codespaces secret after creation, stop and restart the Codespace to load it. Set `EVE_PROVIDER=gemini` and choose an available `EVE_MODEL` if needed.

In the Codespace terminal:

```bash
bash scripts/run-demo.sh amaze-on
```

Open forwarded port **8000** from the Ports tab. Keep its visibility **Private**. The first ingestion downloads the embedding model, so startup can take a few minutes. The script validates settings, indexes the chosen fictional dataset, and starts its server.

In a second terminal:

```bash
bash scripts/run-demo.sh hammered
```

Open forwarded port **8001**, also Private. Both demos use the root `.env` or Codespaces secrets, but have separate datasets, bot configurations, and index storage. Each running server loads its own embedding model; if memory is constrained, stop the first demo with Ctrl+C before starting the second.

## Try it

- Amaze-on: “Can I return an opened but unused product?”
- Amaze-on: “Does express shipping speed up NameTag engraving?”
- Hammered: “Can I take PF101, DA110, and PL201 together?”
- Hammered: “What grade is a final score of 69.9?”

Inspect the cited passages. Read or edit the files under `examples/<preset>/data/` in the Codespace editor. After an edit, stop that server and rerun its launch command to reindex and restart. Expected Q&A is under each preset's `qa.md`; see [demo guide](../examples/DEMO_GUIDE.md).

This does not add in-page uploads, a preset picker, or shared visitor editing. Do not make the forwarded ports public as a substitute for an authenticated public deployment with spending controls. GitHub authentication protects access only while the port remains private.

A Codespaces creation link opens setup; it is not a running bot URL. A running server has its own forwarded-port URL, available in the Ports tab after launch.

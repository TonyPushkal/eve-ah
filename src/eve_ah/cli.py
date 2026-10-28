"""Small operator CLI: ingest locally, then serve a read-only index."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from eve_ah.config import load_settings
from eve_ah.models import EveError


def main():
    parser = argparse.ArgumentParser(
        prog="eve-ah", description="Your documents. Traceable answers."
    )
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Folder containing .env and bot.yaml"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="Build and activate a document index")
    serve = sub.add_parser("serve", help="Start the local chat UI and API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("check", help="Validate configuration without making model calls")
    evaluate = sub.add_parser("evaluate", help="Measure retrieval against a JSON question set")
    evaluate.add_argument("dataset", type=Path)
    evaluate.add_argument(
        "--compare-modes", action="store_true", help="Compare dense and hybrid retrieval"
    )
    answer_evaluate = sub.add_parser(
        "evaluate-answers", help="Generate an answer artifact for human quality review"
    )
    answer_evaluate.add_argument("dataset", type=Path)
    args = parser.parse_args()
    try:
        settings = load_settings(args.root)
        if args.command == "check":
            settings.require_key()
            print("Configuration valid. No provider calls made.")
        elif args.command == "serve":
            import uvicorn

            from eve_ah.api import create_app

            uvicorn.run(create_app(settings), host=args.host, port=args.port, access_log=False)
        else:
            from eve_ah.knowledge import Knowledge

            knowledge = Knowledge(settings)
            if args.command == "ingest":
                print(json.dumps(knowledge.ingest(), indent=2))
                print("Restart the server to load the active index.")
            elif args.command == "evaluate":
                from eve_ah.evaluation import evaluate

                knowledge.load()
                result = evaluate(knowledge, args.dataset, compare_modes=args.compare_modes)
                print(json.dumps(result, indent=2))
            else:
                settings.require_key()
                knowledge.load()
                result = asyncio.run(_evaluate_answers(settings, knowledge, args.dataset))
                print(json.dumps(result, indent=2))
    except (ValueError, EveError) as exc:
        if isinstance(exc, EveError):
            message = exc.message
        else:
            message = "Invalid configuration or input. Check .env, bot.yaml, and command arguments."
        print(f"Error: {message}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print(
            "Error: operation failed. Check model availability, network access, and workspace permissions.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


async def _evaluate_answers(settings, knowledge, dataset):
    from eve_ah.chat import ChatService
    from eve_ah.evaluation import evaluate_answers
    from eve_ah.providers import Provider

    provider = Provider(settings)
    try:
        return await evaluate_answers(ChatService(settings, knowledge, provider), dataset)
    finally:
        await provider.aclose()


if __name__ == "__main__":
    main()

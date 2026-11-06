import asyncio
import json

import httpx
import pytest

from eve_ah.chat import ChatService
from eve_ah.config import BotConfig, Settings
from eve_ah.evaluation import evaluate_conversations
from eve_ah.models import ChatRequest, Source, Turn
from eve_ah.providers import Provider
from eve_ah.routing import parse_decision

OVERVIEW = {
    "topics": [
        {"name": "Shipping", "description": "Delivery fees and timing", "sources": ["s.md"]},
        {"name": "Returns", "description": "Return windows", "sources": ["r.md"]},
    ],
    "suggested_questions": [
        "Can you check where my order is right now?",
        "When is standard shipping free?",
        "What is the capital of France?",
    ],
}


class Store:
    def __init__(self, hits=("s.md",)):
        self.hits = hits
        self.queries = []
        self.expanded = False

    def search(self, query):
        self.queries.append(query)
        if "capital" in query:
            return []
        return [Source(id=f"c-{n}", name=n, text=f"Text from {n}.") for n in self.hits]

    def expand(self, sources):
        self.expanded = True
        return sources + [Source(id="c-extra", name=sources[0].name, text="More.")]

    def overview(self):
        return OVERVIEW


class Router:
    """Answers the routing call with fixed JSON and generation calls with a cited answer."""

    def __init__(self, decision, answer="Shipping is free over $50 [s1]."):
        self.decision, self.answer = decision, answer
        self.routing_calls = 0
        self.generation_calls = 0
        self.system = ""

    async def generate(self, system, user, *, json_output=False):
        if json_output:
            self.routing_calls += 1
            if isinstance(self.decision, Exception):
                raise self.decision
            return self.decision if isinstance(self.decision, str) else json.dumps(self.decision)
        self.generation_calls += 1
        self.system = system
        return self.answer


def run(message, provider, store=None, history=None, routing="model"):
    service = ChatService(Settings(bot=BotConfig(routing=routing)), store or Store(), provider)
    return asyncio.run(service.answer(ChatRequest(message=message, history=history or [])))


def test_parse_decision_accepts_fenced_json_and_rejects_unknown_routes():
    fenced = '```json\n{"route": "answer", "query": "free shipping", "complete_list": true}\n```'
    decision = parse_decision(fenced, "original")
    assert (decision.route, decision.query, decision.complete_list) == (
        "answer",
        "free shipping",
        True,
    )
    assert parse_decision('{"route": "delete_everything"}', "x") is None
    assert parse_decision("not json", "x") is None
    assert parse_decision('{"route": "answer"}', "my message").query == "my message"


def test_personal_record_request_explains_limit_and_suggests_only_answerable_questions():
    provider = Router(
        {"route": "personal_record", "query": "orders", "limit": "look up your orders"}
    )
    store = Store()
    result = run("find my orders", provider, store)
    assert result.response_type == "live_data"
    assert result.answer.startswith("I can’t look up your orders.")
    assert provider.generation_calls == 0
    assert "find my orders" not in store.queries
    assert "When is standard shipping free?" in result.suggested_questions
    assert "Can you check where my order is right now?" not in result.suggested_questions
    assert "What is the capital of France?" not in result.suggested_questions


def test_action_route_uses_model_limit_without_retrieval_of_the_request():
    provider = Router({"route": "action", "query": "x", "limit": "cancel your order."})
    result = run("please cancel it", provider)
    assert result.response_type == "action"
    assert "I can’t cancel your order." in result.answer


def test_policy_question_mentioning_my_still_reaches_retrieval():
    provider = Router({"route": "answer", "query": "cancel order before dispatch"})
    store = Store()
    result = run("How do I cancel my order before it ships?", provider, store)
    assert result.grounding == "documents"
    assert store.queries[0] == "cancel order before dispatch"


def test_followup_uses_standalone_query_from_router():
    provider = Router({"route": "answer", "query": "express shipping cost"})
    store = Store()
    history = [
        Turn(role="user", content="Standard shipping fee?"),
        Turn(role="assistant", content="$5"),
    ]
    run("and express?", provider, store, history)
    assert store.queries[0] == "express shipping cost"


def test_clarify_route_does_not_offer_the_same_clarification_back():
    provider = Router({"route": "clarify", "query": "how long"})
    result = run("How long?", provider)
    assert result.response_type == "clarification"
    assert "How long?" not in result.suggested_questions
    assert provider.generation_calls == 0


def test_complete_list_expands_evidence_and_requires_explicit_completeness():
    provider = Router({"route": "answer", "query": "products", "complete_list": True})
    store = Store()
    run("How many products are listed?", provider, store)
    assert store.expanded
    assert "do not state it is the full set" in provider.system


def test_router_failure_falls_back_to_rules():
    for broken in (RuntimeError("boom"), "not json"):
        provider = Router(broken)
        result = run("Can you cancel my order?", provider)
        assert result.response_type == "action"
        assert provider.generation_calls == 0


def test_rules_mode_makes_no_routing_call():
    provider = Router({"route": "answer", "query": "x"})
    run("When is standard shipping free?", provider, routing="rules")
    assert provider.routing_calls == 0


def test_greetings_skip_the_routing_call():
    provider = Router({"route": "answer", "query": "x"})
    assert run("hello", provider).response_type == "capability"
    assert provider.routing_calls == 0


@pytest.mark.parametrize("name", ["gemini", "openai"])
def test_provider_requests_json_output_only_when_asked(name):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if name == "gemini":
            return httpx.Response(
                200,
                json={
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]
                },
            )
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        )

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = Provider(Settings(provider=name, api_key="k"), client)
            await provider.generate("s", "u", json_output=True)
            await provider.generate("s", "u")

    asyncio.run(go())
    json_body, plain_body = bodies
    if name == "gemini":
        assert json_body["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseMimeType" not in plain_body["generationConfig"]
    else:
        assert json_body["response_format"] == {"type": "json_object"}
        assert "response_format" not in plain_body


def test_conversation_evaluation_reports_categories_and_bad_suggestions(tmp_path):
    cases = [
        {
            "id": "a",
            "category": "personal_record",
            "question": "Can you cancel my order?",
            "expect": "action",
        },
        {
            "id": "b",
            "category": "paraphrase",
            "question": "When is standard shipping free?",
            "expect": "answer",
            "sources": ["s.md"],
        },
    ]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    settings = Settings(bot=BotConfig(routing="rules"))
    report = asyncio.run(evaluate_conversations(settings, Store(), None, path, offline=True))
    assert report["cases"] == 2
    assert report["categories"]["paraphrase"] == {"cases": 1, "passed": 1}
    assert report["pass_rate"] == 1.0

import asyncio

import pytest

from eve_ah.chat import ChatService
from eve_ah.config import BotConfig, Settings
from eve_ah.models import ChatRequest, Source


class Store:
    def __init__(self, sources=None):
        self.sources = sources or []
        self.query = ""

    def search(self, query):
        self.query = query
        return self.sources


class Generator:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    async def generate(self, system, user):
        self.calls += 1
        return self.text


def test_no_evidence_no_provider_call():
    provider = Generator("guess")
    answer = asyncio.run(
        ChatService(Settings(), Store(), provider).answer(ChatRequest(message="unknown"))
    )
    assert answer.grounding == "insufficient"
    assert provider.calls == 0


@pytest.mark.parametrize(
    "text", ["A fact without citation", "A fact [made-up]", "INSUFFICIENT_EVIDENCE"]
)
def test_unsupported_answers_abstain(text):
    store = Store([Source(id="s1", name="policy.md", text="Returns in 30 days")])
    answer = asyncio.run(
        ChatService(Settings(), store, Generator(text)).answer(ChatRequest(message="returns?"))
    )
    assert answer.grounding == "insufficient"
    assert answer.sources == []


def test_citations_and_followup_context():
    store = Store([Source(id="s1", name="policy.md", text="Returns in 30 days")])
    request = ChatRequest(
        message="How long?",
        history=[
            {"role": "user", "content": "Return policy?"},
            {"role": "assistant", "content": "untrusted fabricated fact"},
        ],
    )
    answer = asyncio.run(ChatService(Settings(), store, Generator("30 days [s1]")).answer(request))
    assert answer.grounding == "documents"
    assert [s.id for s in answer.sources] == ["s1"]
    assert "Return policy?" in store.query
    assert "fabricated" not in store.query


def test_general_answers_labeled():
    answer = asyncio.run(
        ChatService(
            Settings(bot=BotConfig(mode="general")), Store(), Generator("General answer")
        ).answer(ChatRequest(message="question"))
    )
    assert answer.grounding == "general"
    assert "not verified" in answer.answer

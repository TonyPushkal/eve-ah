import asyncio

import pytest

from eve_ah.chat import ChatService
from eve_ah.config import BotConfig, Settings
from eve_ah.models import ChatRequest, Source


class Store:
    def __init__(self, sources=None, overview=None):
        self.sources = sources or []
        self._overview = overview or {"topics": [], "suggested_questions": []}
        self.query = ""
        self.search_calls = 0

    def search(self, query):
        self.search_calls += 1
        self.query = query
        return self.sources

    def overview(self):
        return self._overview


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
    "message",
    [
        "Hello",
        "What can you help me with?",
        "What can you help me with it?",
        "Hi, what can you help me with?",
        "Tell me what can you do",
        "How can you help me?",
        "What can you tell me about?",
        "What can I ask you about?",
        "Which university questions can you answer?",
        "What university topics do you know about?",
        "Which parts of this shop can you explain?",
    ],
)
def test_capability_questions_use_active_catalog_without_provider(message):
    store = Store(
        overview={
            "topics": [
                {
                    "name": "Returns",
                    "description": "Return windows and refunds",
                    "sources": ["returns.md"],
                    "source_ids": ["s1"],
                },
                {
                    "name": "Shipping",
                    "description": "Delivery times and fees",
                    "sources": ["shipping.md"],
                    "source_ids": ["s2"],
                },
            ],
            "suggested_questions": ["When is shipping free?"],
        }
    )
    provider = Generator("should not run")
    answer = asyncio.run(
        ChatService(Settings(), store, provider).answer(ChatRequest(message=message))
    )
    assert answer.grounding == "workspace"
    assert "Returns" in answer.answer and "Shipping" in answer.answer
    assert "When is shipping free?" in answer.answer
    assert store.search_calls == 0
    assert provider.calls == 0


def test_capability_question_without_catalog_explains_ingestion():
    answer = asyncio.run(
        ChatService(Settings(), Store(), Generator("unused")).answer(
            ChatRequest(message="What can you help me with?")
        )
    )
    assert answer.grounding == "workspace"
    assert "No topic overview" in answer.answer
    assert "re-run ingestion" in answer.answer


def test_factual_help_word_is_not_misrouted():
    store = Store([Source(id="s1", name="returns.md", text="Returns in 30 days")])
    answer = asyncio.run(
        ChatService(Settings(), store, Generator("Returns take 30 days [s1]")).answer(
            ChatRequest(message="Can you help me understand the return window?")
        )
    )
    assert answer.grounding == "documents"
    assert store.search_calls == 1


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


def test_topic_switch_does_not_pollute_retrieval_query():
    store = Store([Source(id="s1", name="shipping.md", text="Delivery takes 3 days")])
    request = ChatRequest(
        message="Tell me about shipping fees",
        history=[
            {"role": "user", "content": "What is the return policy?"},
            {"role": "assistant", "content": "Returns take 30 days."},
        ],
    )
    asyncio.run(ChatService(Settings(), store, Generator("Shipping is $5 [s1]")).answer(request))
    assert store.query == "Tell me about shipping fees"


def test_anaphoric_followup_uses_previous_user_subject():
    store = Store([Source(id="s1", name="returns.md", text="Damage is covered")])
    request = ChatRequest(
        message="What if it arrived damaged?",
        history=[
            {"role": "user", "content": "Can I return a personalized item?"},
            {"role": "assistant", "content": "Not for change of mind."},
        ],
    )
    asyncio.run(ChatService(Settings(), store, Generator("Damage is covered [s1]")).answer(request))
    assert "personalized item" in store.query
    assert "arrived damaged" in store.query


@pytest.mark.parametrize("message", ["How long?", "What about that?", "Can I do it?"])
def test_ambiguous_question_without_subject_asks_for_clarification(message):
    store = Store(
        overview={
            "topics": [
                {
                    "name": "Returns",
                    "description": "Return policy",
                    "sources": ["returns.md"],
                    "source_ids": ["s1"],
                }
            ],
            "suggested_questions": [],
        }
    )
    provider = Generator("should not run")
    answer = asyncio.run(
        ChatService(Settings(), store, provider).answer(ChatRequest(message=message))
    )
    assert answer.grounding == "clarification"
    assert "Which topic or item" in answer.answer
    assert "Returns" in answer.answer
    assert store.search_calls == 0
    assert provider.calls == 0


def test_missing_information_names_available_topics():
    store = Store(
        overview={
            "topics": [
                {
                    "name": "Returns",
                    "description": "Return policy",
                    "sources": ["returns.md"],
                    "source_ids": ["s1"],
                }
            ],
            "suggested_questions": [],
        }
    )
    answer = asyncio.run(
        ChatService(Settings(), store, Generator("unused")).answer(
            ChatRequest(message="Where is order 123?")
        )
    )
    assert answer.grounding == "insufficient"
    assert "Returns" in answer.answer
    assert "indexed documents" in answer.answer


def test_general_answers_labeled():
    answer = asyncio.run(
        ChatService(
            Settings(bot=BotConfig(mode="general")), Store(), Generator("General answer")
        ).answer(ChatRequest(message="question"))
    )
    assert answer.grounding == "general"
    assert "not verified" in answer.answer

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
        self.system = ""
        self.user = ""

    async def generate(self, system, user):
        self.calls += 1
        self.system = system
        self.user = user
        return self.text


def test_no_evidence_no_provider_call():
    provider = Generator("guess")
    answer = asyncio.run(
        ChatService(Settings(), Store(), provider).answer(ChatRequest(message="unknown"))
    )
    assert answer.grounding == "insufficient"
    assert answer.response_type == "out_of_scope"
    assert "outside the information" in answer.answer
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("message", "expected_limit"),
    [
        ("I have 3 orders to place", "can’t place orders or complete purchases"),
        ("Can you change my shipping address?", "can’t change records or account data"),
        ("Please book an appointment for tomorrow", "can’t book or schedule appointments"),
        ("Can you cancel my order?", "can’t cancel orders or requests"),
        ("Please issue my refund now", "can’t issue refunds"),
        ("Reset my account password for me", "can’t reset passwords or account access"),
        ("Download my transcript for me", "can’t download private files or records"),
    ],
)
def test_action_requests_are_handled_without_retrieval_or_provider(message, expected_limit):
    store = Store(
        overview={
            "topics": [
                {
                    "name": "Orders and payments",
                    "description": "Order and payment policies",
                    "sources": ["orders.md"],
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

    assert answer.grounding == "workspace"
    assert answer.response_type == "action"
    assert expected_limit in answer.answer
    assert "Orders and payments" in answer.answer
    assert store.search_calls == 0
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("message", "expected_limit"),
    [
        ("How is the weather today?", "live weather or forecasts"),
        ("Where is my order right now?", "live order, delivery, or payment status"),
        ("Have I passed PF101?", "personal grades or records"),
        ("How many seats are left in UX120?", "live availability or stock levels"),
        ("Has order MM-88 been dispatched?", "live order, delivery, or payment status"),
        ("Is the learning platform down right now?", "current service status or outages"),
    ],
)
def test_live_data_requests_are_handled_without_retrieval_or_provider(message, expected_limit):
    store = Store(
        overview={
            "topics": [
                {
                    "name": "Orders",
                    "description": "Published order policies",
                    "sources": ["orders.md"],
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

    assert answer.grounding == "workspace"
    assert answer.response_type == "live_data"
    assert expected_limit in answer.answer
    assert store.search_calls == 0
    assert provider.calls == 0


@pytest.mark.parametrize("message", ["Thanks", "Thank you!", "How are you?", "Bye"])
def test_social_messages_get_a_short_workspace_aware_reply(message):
    store = Store(
        overview={
            "topics": [
                {
                    "name": "Shipping",
                    "description": "Delivery policies",
                    "sources": ["shipping.md"],
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

    assert answer.grounding == "workspace"
    assert answer.response_type == "small_talk"
    assert "Shipping" in answer.answer
    assert store.search_calls == 0
    assert provider.calls == 0


@pytest.mark.parametrize(
    "message",
    [
        "Can I cancel an order after dispatch?",
        "When are orders dispatched?",
    ],
)
def test_policy_questions_still_use_document_retrieval(message):
    store = Store([Source(id="c-policy", name="orders.md", text="Published order policy")])
    provider = Generator("The policy is documented [s1].")

    answer = asyncio.run(
        ChatService(Settings(), store, provider).answer(ChatRequest(message=message))
    )

    assert answer.grounding == "documents"
    assert store.search_calls == 1
    assert provider.calls == 1


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


def test_natural_catalog_count_question_reports_configured_topics_without_retrieval():
    topics = [
        {
            "name": name,
            "description": f"Information about {name.lower()}",
            "sources": [f"{index}.md"],
            "source_ids": [f"s{index}"],
        }
        for index, name in enumerate(
            [
                "Store overview",
                "Products",
                "Shipping",
                "Returns and refunds",
                "Warranty",
                "Orders and payments",
                "Accounts and support",
                "Product care",
            ],
            1,
        )
    ]
    store = Store(overview={"topics": topics, "suggested_questions": []})
    provider = Generator("should not run")

    answer = asyncio.run(
        ChatService(Settings(), store, provider).answer(
            ChatRequest(message="how many item categorizes do you have?")
        )
    )

    assert answer.grounding == "workspace"
    assert answer.response_type == "capability"
    assert "8 topics" in answer.answer
    assert "Products" in answer.answer
    assert "Orders and payments" in answer.answer
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
    "message",
    [
        "Can you update me on the refund policy?",
        "Can you please update me about the refund policy?",
    ],
)
def test_informational_update_request_still_uses_document_retrieval(message):
    store = Store([Source(id="s1", name="returns.md", text="Refunds take five days")])
    provider = Generator("Refunds take five days [s1].")

    answer = asyncio.run(
        ChatService(Settings(), store, provider).answer(ChatRequest(message=message))
    )

    assert answer.grounding == "documents"
    assert answer.response_type == "answer"
    assert store.search_calls == 1
    assert provider.calls == 1


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


def test_provider_citation_aliases_are_translated_to_stable_source_ids():
    source = Source(id="c-a1b2c3", name="shipping.md", text="Shipping is free at $50")
    provider = Generator("Shipping is free at $50 [s1].")
    answer = asyncio.run(
        ChatService(Settings(), Store([source]), provider).answer(
            ChatRequest(message="When is shipping free?")
        )
    )

    assert '"id": "s1"' in provider.user
    assert "c-a1b2c3" not in provider.user
    assert answer.answer == "Shipping is free at $50 [c-a1b2c3]."
    assert answer.sources == [source]
    assert answer.grounding == "documents"


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


def test_ambiguous_payment_timing_asks_which_stage_and_offers_focused_choices():
    store = Store(
        overview={
            "topics": [
                {
                    "name": "Orders and payments",
                    "description": "Payment authorization, final charge timing, and receipts",
                    "sources": ["orders-payments.md"],
                    "source_ids": ["s1"],
                },
                {
                    "name": "Returns and refunds",
                    "description": "Return eligibility and refund timing",
                    "sources": ["returns.md"],
                    "source_ids": ["s2"],
                },
            ],
            "suggested_questions": ["When is shipping free?"],
        }
    )
    provider = Generator("should not run")

    answer = asyncio.run(
        ChatService(Settings(), store, provider).answer(
            ChatRequest(message="how long for a payment to process from india")
        )
    )

    assert answer.grounding == "clarification"
    assert answer.response_type == "clarification"
    assert "authorization" in answer.answer
    assert "final charge" in answer.answer
    assert "refund" in answer.answer
    assert answer.suggested_questions == [
        "When does payment authorization appear?",
        "When is the final payment charged?",
        "How long does a refund take?",
    ]
    assert store.search_calls == 0
    assert provider.calls == 0


def test_payment_deadline_workspace_uses_retrieval_instead_of_retail_clarification():
    store = Store(
        [Source(id="deadline", name="calendar-fees.md", text="Tuition is due 15 January.")],
        overview={
            "topics": [
                {
                    "name": "Calendar, tuition, and withdrawals",
                    "description": "Term dates, fees, payment deadlines, and refunds",
                    "sources": ["calendar-fees.md"],
                    "source_ids": ["deadline"],
                }
            ],
            "suggested_questions": [],
        },
    )
    provider = Generator("Tuition is due 15 January [s1].")

    answer = asyncio.run(
        ChatService(Settings(), store, provider).answer(
            ChatRequest(message="When is my tuition payment due?")
        )
    )

    assert answer.grounding == "documents"
    assert store.search_calls == 1
    assert provider.calls == 1


@pytest.mark.parametrize(
    "message",
    [
        "When does payment authorization appear?",
        "When is the final payment charged?",
        "How long does a refund take?",
    ],
)
def test_payment_clarification_choices_continue_to_document_retrieval(message):
    store = Store([Source(id="policy", name="payments.md", text="Published timing policy")])
    provider = Generator("The timing is documented [s1].")

    answer = asyncio.run(
        ChatService(Settings(), store, provider).answer(
            ChatRequest(
                message=message,
                history=[{"role": "user", "content": "How long does a payment take?"}],
            )
        )
    )

    assert answer.grounding == "documents"
    assert store.search_calls == 1
    assert provider.calls == 1


def test_live_order_status_names_available_topics():
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
    assert answer.grounding == "workspace"
    assert answer.response_type == "live_data"
    assert "Returns" in answer.answer
    assert "live order, delivery, or payment status" in answer.answer


def test_general_answers_labeled():
    answer = asyncio.run(
        ChatService(
            Settings(bot=BotConfig(mode="general")), Store(), Generator("General answer")
        ).answer(ChatRequest(message="question"))
    )
    assert answer.grounding == "general"
    assert "not verified" in answer.answer

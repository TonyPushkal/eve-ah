from fastapi.testclient import TestClient

from eve_ah.api import create_app
from eve_ah.config import Settings
from eve_ah.models import EveError, Source


class Store:
    def load(self):
        pass

    def search(self, query):
        return [Source(id="s1", name="policy.md", text="Returns within 30 days.", score=0.9)]

    def overview(self):
        return {
            "topics": [
                {
                    "name": "Returns",
                    "description": "Return policy",
                    "sources": ["policy.md"],
                    "source_ids": ["s1"],
                }
            ],
            "suggested_questions": ["What is the return window?"],
        }


class Generator:
    async def generate(self, system, user):
        return "Returns within 30 days. [s1]"

    async def aclose(self):
        pass


def test_chat_and_health():
    with TestClient(create_app(Settings(api_key="test"), Store(), Generator())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        result = client.post("/api/chat", json={"message": "What is the return policy?"})
        assert result.status_code == 200
        assert result.json()["grounding"] == "documents"
        assert result.json()["response_type"] == "answer"
        assert result.json()["sources"][0]["name"] == "policy.md"
        info = client.get("/api/info")
        assert "api_key" not in info.text
        assert info.json()["topics"][0]["name"] == "Returns"
        assert "source_ids" not in info.json()["topics"][0]
        assert info.json()["suggested_questions"] == ["What is the return window?"]


def test_conversation_type_is_additive_to_stable_grounding_contract():
    with TestClient(create_app(Settings(api_key="test"), Store(), Generator())) as client:
        result = client.post("/api/chat", json={"message": "Can you cancel my order?"})

    assert result.status_code == 200
    assert result.json()["grounding"] == "workspace"
    assert result.json()["response_type"] == "action"


def test_chat_can_return_contextual_followup_questions():
    class PaymentStore(Store):
        def overview(self):
            return {
                "topics": [
                    {
                        "name": "Orders and payments",
                        "description": "Payment authorization and final charge timing",
                        "sources": ["payments.md"],
                    },
                    {
                        "name": "Returns",
                        "description": "Return policy and refund timing",
                        "sources": ["policy.md"],
                    },
                ],
                "suggested_questions": [],
            }

    with TestClient(create_app(Settings(api_key="test"), PaymentStore(), Generator())) as client:
        result = client.post(
            "/api/chat", json={"message": "How long does a payment take to process?"}
        )

    assert result.status_code == 200
    assert result.json()["grounding"] == "clarification"
    assert result.json()["suggested_questions"] == [
        "When does payment authorization appear?",
        "When is the final payment charged?",
        "How long does a refund take?",
    ]


def test_browser_shell_has_guided_discovery_and_collapsible_evidence():
    with TestClient(create_app(Settings(api_key="test"), Store(), Generator())) as client:
        page = client.get("/")
        app_js = client.get("/static/app.js")

    assert page.status_code == 200
    assert 'id="welcome-suggestions"' in page.text
    assert 'id="topic-guides"' in page.text
    assert 'id="evidence-panel"' in page.text
    assert 'id="evidence-panel" class="evidence-panel"' in page.text
    assert "hidden" in page.text.split('id="evidence-panel"', 1)[1].split(">", 1)[0]
    assert "data.suggested_questions" in app_js.text
    assert (
        'const recoveryType = responseType === "answer" ? data.grounding : responseType'
        in app_js.text
    )


def test_missing_key_unready():
    with TestClient(create_app(Settings(), Store(), Generator())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.post("/api/chat", json={"message": "Hi"}).status_code == 503


def test_invalid_input_and_oversized_body():
    with TestClient(create_app(Settings(api_key="test"), Store(), Generator())) as client:
        assert client.post("/api/chat", json={"message": " "}).status_code == 422
        assert client.post("/api/chat", json={"message": "x" * 150000}).status_code == 413
        assert (
            client.post(
                "/api/chat", json={"message": "Hi", "history": [{"role": "system", "content": "x"}]}
            ).status_code
            == 422
        )


def test_failed_index_unready():
    class Broken(Store):
        def load(self):
            raise EveError("Run ingestion first.")

    with TestClient(create_app(Settings(api_key="test"), Broken(), Generator())) as client:
        assert client.get("/ready").status_code == 503
        assert client.get("/api/info").json()["ready"] is False

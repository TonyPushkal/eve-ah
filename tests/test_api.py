from fastapi.testclient import TestClient

from eve_ah.api import create_app
from eve_ah.config import Settings
from eve_ah.models import EveError, Source


class Store:
    def load(self):
        pass

    def search(self, query):
        return [Source(id="s1", name="policy.md", text="Returns within 30 days.", score=0.9)]


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
        assert result.json()["sources"][0]["name"] == "policy.md"
        assert "api_key" not in client.get("/api/info").text


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

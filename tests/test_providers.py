import asyncio

import httpx
import pytest

from eve_ah.config import Settings
from eve_ah.models import EveError
from eve_ah.providers import Provider


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_success_and_credentials_stay_out_of_url(provider):
    def handler(request):
        assert "private-key" not in str(request.url)
        if provider == "gemini":
            assert request.headers["x-goog-api-key"] == "private-key"
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [{"text": "thinking", "thought": True}, {"text": "answer"}]
                            },
                        }
                    ]
                },
            )
        assert request.headers["authorization"] == "Bearer private-key"
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "answer"}}]}
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await Provider(
                Settings(provider=provider, api_key="private-key"), client
            ).generate("system", "question")
            assert result == "answer"

    asyncio.run(run())


def test_auth_error_not_retried_and_redacted():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="private-key credential failed")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(EveError) as caught:
                await Provider(Settings(api_key="private-key"), client).generate("x", "y")
            assert caught.value.code == "provider_auth"
            assert "private-key" not in str(caught.value)

    asyncio.run(run())
    assert len(calls) == 1


def test_transient_retries_bounded():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(EveError) as caught:
                await Provider(Settings(), client).generate("x", "y")
            assert caught.value.status == 503

    asyncio.run(run())
    assert len(calls) == 3


@pytest.mark.parametrize(
    "body", [{}, {"candidates": []}, {"candidates": [{"content": {"parts": []}}]}]
)
def test_empty_or_malformed_output(body):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
        ) as client:
            with pytest.raises(EveError, match="usable answer"):
                await Provider(Settings(), client).generate("x", "y")

    asyncio.run(run())


@pytest.mark.parametrize(
    "provider,body",
    [
        ("gemini", {"candidates": [None]}),
        ("gemini", {"candidates": ["invalid"]}),
        ("gemini", {"candidates": [{"content": {"parts": [None]}}]}),
        ("openai", {"choices": [None]}),
        ("openai", {"choices": ["invalid"]}),
    ],
)
def test_malformed_objects_are_sanitized(provider, body):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
        ) as client:
            with pytest.raises(EveError) as caught:
                await Provider(Settings(provider=provider), client).generate("x", "y")
            assert caught.value.code == "provider_output"
            assert caught.value.status == 502

    asyncio.run(run())

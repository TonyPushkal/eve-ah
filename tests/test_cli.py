import asyncio

import pytest

from eve_ah.cli import _evaluate_answers
from eve_ah.config import Settings
from eve_ah.models import EveError


@pytest.mark.parametrize("fails", [False, True])
def test_answer_evaluation_always_closes_provider(monkeypatch, fails):
    class FakeProvider:
        instance = None

        def __init__(self, settings):
            self.closed = False
            FakeProvider.instance = self

        async def aclose(self):
            self.closed = True

    async def fake_evaluate(chat, dataset):
        if fails:
            raise EveError("provider failed")
        return {"kind": "answer_quality_review"}

    monkeypatch.setattr("eve_ah.providers.Provider", FakeProvider)
    monkeypatch.setattr("eve_ah.evaluation.evaluate_answers", fake_evaluate)

    if fails:
        with pytest.raises(EveError, match="provider failed"):
            asyncio.run(_evaluate_answers(Settings(), object(), object()))
    else:
        assert asyncio.run(_evaluate_answers(Settings(), object(), object())) == {
            "kind": "answer_quality_review"
        }
    assert FakeProvider.instance.closed is True

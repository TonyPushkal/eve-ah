import json
from pathlib import Path

from eve_ah.evaluation import evaluate, evaluate_answers
from eve_ah.models import Source


def test_evaluation_counts_hits_and_abstentions(tmp_path):
    class Store:
        def search(self, query):
            return [Source(id="x", name="a.md", text="Evidence")] if query == "covered" else []

    p = tmp_path / "cases.json"
    p.write_text(
        json.dumps(
            [{"question": "covered", "sources": ["a.md"]}, {"question": "unknown", "sources": []}]
        )
    )
    report = evaluate(Store(), p)
    assert report["source_hit_rate"] == 1
    assert report["unanswerable_rejection_rate"] == 1
    assert report["kind"] == "retrieval_only"


def test_evaluation_requires_every_expected_source(tmp_path):
    class Store:
        def search(self, query, mode=None):
            return [Source(id="x", name="a.md", text="Evidence")]

    p = tmp_path / "cases.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "multi-source",
                    "category": "answerable",
                    "question": "Combine both policies",
                    "sources": ["a.md", "b.md"],
                }
            ]
        )
    )
    report = evaluate(Store(), p)
    assert report["source_hit_rate"] == 1
    assert report["required_source_recall"] == 0.5
    assert report["complete_source_rate"] == 0
    assert report["results"][0]["missing"] == ["b.md"]


def test_evaluation_compares_dense_and_hybrid(tmp_path):
    class Store:
        def search(self, query, mode=None):
            name = "exact.md" if mode == "hybrid" else "nearby.md"
            return [Source(id=mode or "x", name=name, text="Evidence")]

    p = tmp_path / "cases.json"
    p.write_text(json.dumps([{"question": "SKU-42", "sources": ["exact.md"]}]))
    report = evaluate(Store(), p, compare_modes=True)
    assert report["modes"]["dense"]["complete_source_rate"] == 0
    assert report["modes"]["hybrid"]["complete_source_rate"] == 1


def test_retrieval_evaluation_skips_capability_cases(tmp_path):
    class Store:
        def search(self, query, mode=None):
            raise AssertionError("capability questions belong to answer evaluation")

    p = tmp_path / "cases.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "capability",
                    "category": "capability",
                    "question": "What can you help me with?",
                    "sources": [],
                }
            ]
        )
    )
    report = evaluate(Store(), p)
    assert report["categories"]["capability"] == {
        "questions": 1,
        "passed": 0,
        "skipped": 1,
    }
    assert report["results"][0]["passed"] is None


def test_answer_evaluation_reports_structure_without_claiming_correctness(tmp_path):
    class Chat:
        async def answer(self, request):
            from eve_ah.models import ChatResponse

            return ChatResponse(
                answer="The answer [s1]",
                sources=[Source(id="s1", name="a.md", text="Evidence")],
                grounding="documents",
            )

    p = tmp_path / "qa.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "case-1",
                    "category": "answerable",
                    "question": "Question?",
                    "expected_answer": "Expected meaning",
                    "sources": ["a.md", "b.md"],
                    "citation_required": True,
                }
            ]
        )
    )
    report = __import__("asyncio").run(evaluate_answers(Chat(), p))
    assert report["kind"] == "answer_quality_review"
    assert report["structural_pass_rate"] == 0
    assert report["results"][0]["missing_sources"] == ["b.md"]
    assert report["results"][0]["human_review_required"] is True
    assert "accuracy" not in report


def test_answer_evaluation_counts_provider_failure_instead_of_dropping_case(tmp_path):
    class Chat:
        async def answer(self, request):
            from eve_ah.models import EveError

            raise EveError("provider unavailable")

    p = tmp_path / "qa.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "failed-provider",
                    "question": "Question?",
                    "expected_answer": "Expected meaning",
                    "sources": ["a.md"],
                }
            ]
        )
    )
    report = __import__("asyncio").run(evaluate_answers(Chat(), p))
    assert report["questions"] == 1
    assert report["provider_failures"] == 1
    assert report["structural_pass_rate"] == 0
    assert report["results"][0]["failure"] == "provider_or_request_failure"


def test_demo_quality_sets_have_120_unique_cases_and_no_source_leakage():
    root = Path(__file__).parents[1] / "examples"
    cases = []
    for preset in ("amaze-on", "hammered"):
        development = json.loads((root / preset / "qa.json").read_text())
        holdout = json.loads((root / preset / "qa-holdout.json").read_text())
        assert len(development) == 40
        assert len(holdout) == 20
        data_files = {path.name for path in (root / preset / "data").iterdir()}
        for case in development + holdout:
            assert set(case["sources"]).issubset(data_files)
        cases.extend(development + holdout)
    assert len(cases) == 120
    assert len({case["id"] for case in cases}) == 120
    assert len({case["question"].casefold() for case in cases}) == 120

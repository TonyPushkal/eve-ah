import json

from eve_ah.evaluation import evaluate
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

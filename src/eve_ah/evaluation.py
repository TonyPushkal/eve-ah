"""Retrieval-only measurements. These do not claim generated-answer correctness."""

import json
import math
import statistics
import time
from pathlib import Path


def evaluate(knowledge, path: Path):
    cases = json.loads(path.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation requires a nonempty list.")
    hits, answerable, abstained, unanswerable, durations = 0, 0, 0, 0, []
    details = []
    for case in cases:
        if not isinstance(case.get("question"), str) or not isinstance(case.get("sources"), list):
            raise ValueError("Each case needs question and sources fields.")
        started = time.perf_counter()
        sources = knowledge.search(case["question"])
        durations.append((time.perf_counter() - started) * 1000)
        names = {s.name for s in sources}
        if case["sources"]:
            answerable += 1
            passed = bool(names.intersection(case["sources"]))
            hits += int(passed)
        else:
            unanswerable += 1
            passed = not sources
            abstained += int(passed)
        details.append({"question": case["question"], "passed": passed, "retrieved": sorted(names)})
    ordered = sorted(durations)
    return {
        "kind": "retrieval_only",
        "questions": len(cases),
        "source_hit_rate": hits / answerable if answerable else None,
        "unanswerable_rejection_rate": abstained / unanswerable if unanswerable else None,
        "search_p50_ms": round(statistics.median(durations), 2),
        "search_p95_ms": round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 2),
        "results": details,
    }

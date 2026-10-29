"""Retrieval measurements and review artifacts for generated answers."""

import json
import math
import statistics
import time
from pathlib import Path

from eve_ah.models import ChatRequest, EveError

_DETERMINISTIC_CATEGORIES = frozenset({"action", "live_data", "out_of_scope", "small_talk"})


def _load_cases(path: Path) -> list[dict]:
    cases = json.loads(path.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation requires a nonempty list.")
    for case in cases:
        if not isinstance(case.get("question"), str) or not isinstance(case.get("sources"), list):
            raise ValueError("Each case needs question and sources fields.")
        if not all(isinstance(source, str) and source for source in case["sources"]):
            raise ValueError("Evaluation source names must be nonempty strings.")
    return cases


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _search(knowledge, question: str, mode: str | None):
    if mode is None:
        return knowledge.search(question)
    return knowledge.search(question, mode=mode)


def _evaluate_mode(knowledge, cases: list[dict], mode: str | None) -> dict:
    any_hits = complete_hits = rejected = answerable = unanswerable = 0
    required_found = required_total = 0
    durations: list[float] = []
    categories: dict[str, dict[str, int]] = {}
    details = []
    warmup = next((case for case in cases if case.get("category") != "capability"), None)
    if warmup:
        _search(knowledge, warmup["question"], mode)
    for case in cases:
        category = case.get("category", "unspecified")
        category_stats = categories.setdefault(
            category, {"questions": 0, "passed": 0, "skipped": 0}
        )
        category_stats["questions"] += 1
        if category == "capability":
            category_stats["skipped"] += 1
            details.append(
                {
                    "id": case.get("id"),
                    "category": category,
                    "question": case["question"],
                    "passed": None,
                    "retrieved": [],
                    "missing": [],
                }
            )
            continue
        started = time.perf_counter()
        sources = _search(knowledge, case["question"], mode)
        durations.append((time.perf_counter() - started) * 1000)
        names = {source.name for source in sources}
        expected = set(case["sources"])
        found = expected.intersection(names)
        missing = expected.difference(names)
        if expected:
            answerable += 1
            required_total += len(expected)
            required_found += len(found)
            any_hit = bool(found)
            complete = not missing
            any_hits += int(any_hit)
            complete_hits += int(complete)
            passed = complete
        else:
            unanswerable += 1
            passed = not sources
            rejected += int(passed)
        category_stats["passed"] += int(passed)
        details.append(
            {
                "id": case.get("id"),
                "category": category,
                "question": case["question"],
                "passed": passed,
                "retrieved": sorted(names),
                "missing": sorted(missing),
            }
        )
    return {
        "questions": len(cases),
        "source_hit_rate": any_hits / answerable if answerable else None,
        "complete_source_rate": complete_hits / answerable if answerable else None,
        "required_source_recall": required_found / required_total if required_total else None,
        "unanswerable_rejection_rate": rejected / unanswerable if unanswerable else None,
        "search_p50_ms": round(statistics.median(durations), 2) if durations else None,
        "search_p95_ms": round(_percentile(durations, 0.95), 2) if durations else None,
        "categories": categories,
        "results": details,
    }


def evaluate(knowledge, path: Path, *, compare_modes: bool = False):
    """Measure source recall and rejection without making answer-quality claims."""
    cases = _load_cases(path)
    if compare_modes:
        return {
            "kind": "retrieval_comparison",
            "modes": {mode: _evaluate_mode(knowledge, cases, mode) for mode in ("dense", "hybrid")},
        }
    return {"kind": "retrieval_only", **_evaluate_mode(knowledge, cases, None)}


async def evaluate_answers(chat, path: Path) -> dict:
    """Create an answer artifact for human correctness and completeness review."""
    cases = _load_cases(path)
    details = []
    structural_passes = 0
    provider_failures = 0
    for case in cases:
        try:
            response = await chat.answer(
                ChatRequest(message=case["question"], history=case.get("history", []))
            )
        except EveError:
            provider_failures += 1
            details.append(
                {
                    "id": case.get("id"),
                    "category": case.get("category", "unspecified"),
                    "question": case["question"],
                    "expected_answer": case.get("expected_answer"),
                    "answer": None,
                    "grounding": None,
                    "returned_sources": [],
                    "missing_sources": sorted(case["sources"]),
                    "structural_pass": False,
                    "failure": "provider_or_request_failure",
                    "human_review_required": True,
                    "human_correct": None,
                    "human_complete": None,
                    "human_supported": None,
                }
            )
            continue
        category = case.get("category", "unspecified")
        returned = {source.name for source in response.sources}
        expected = set() if category in _DETERMINISTIC_CATEGORIES else set(case["sources"])
        missing = expected.difference(returned)
        citation_required = bool(case.get("citation_required", expected))
        if category in _DETERMINISTIC_CATEGORIES:
            citation_required = False
        citation_shape_valid = not citation_required or bool(response.sources)
        if category in _DETERMINISTIC_CATEGORIES:
            grounding_valid = response.response_type == category
            source_coverage_valid = not response.sources
        elif category == "capability":
            grounding_valid = response.grounding == "workspace"
            source_coverage_valid = not response.sources
        elif expected:
            grounding_valid = response.grounding == "documents"
            source_coverage_valid = not missing
        else:
            grounding_valid = response.response_type == "out_of_scope"
            source_coverage_valid = not response.sources
        structural_pass = citation_shape_valid and grounding_valid and source_coverage_valid
        structural_passes += int(structural_pass)
        details.append(
            {
                "id": case.get("id"),
                "category": case.get("category", "unspecified"),
                "question": case["question"],
                "expected_answer": case.get("expected_answer"),
                "answer": response.answer,
                "grounding": response.grounding,
                "response_type": response.response_type,
                "returned_sources": sorted(returned),
                "missing_sources": sorted(missing),
                "structural_pass": structural_pass,
                "human_review_required": True,
                "human_correct": None,
                "human_complete": None,
                "human_supported": None,
            }
        )
    return {
        "kind": "answer_quality_review",
        "questions": len(cases),
        "structural_pass_rate": structural_passes / len(cases),
        "provider_failures": provider_failures,
        "accuracy_claim": "Human review required; structural checks do not establish accuracy.",
        "results": details,
    }

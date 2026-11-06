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


class _CountingProvider:
    """Wraps a provider to count calls; offline mode cites the first source without a model."""

    def __init__(self, provider, offline: bool):
        self.provider, self.offline, self.calls = provider, offline, 0

    async def generate(self, system: str, user: str, **options) -> str:
        self.calls += 1
        if self.offline:
            return "[s1]" if "documents" in user else "{}"
        return await self.provider.generate(system, user, **options)


def _outcome(response) -> str:
    if response.response_type == "out_of_scope" or response.grounding == "insufficient":
        return "abstain"
    if response.response_type == "answer":
        return "answer" if response.grounding == "documents" else "general"
    return response.response_type


async def evaluate_conversations(settings, knowledge, provider, path: Path, *, offline=False):
    """Route-level pass rates per category. Text checks run only with a real provider."""
    import re

    from eve_ah.chat import ChatService

    cases = json.loads(path.read_text())
    counting = _CountingProvider(provider, offline)
    retrieved: list[str] = []
    original_search = knowledge.search

    def recording_search(query, *args, **kwargs):
        sources = original_search(query, *args, **kwargs)
        retrieved[:] = [source.name for source in sources]
        return sources

    knowledge.search = recording_search
    service = ChatService(settings, knowledge, counting)
    categories: dict[str, dict[str, int]] = {}
    details = []
    try:
        for case in cases:
            retrieved.clear()
            counting.calls = 0
            started = time.perf_counter()
            try:
                response = await service.answer(
                    ChatRequest(message=case["question"], history=case.get("history", []))
                )
            except EveError as error:
                details.append(
                    {"id": case["id"], "question": case["question"], "error": error.code}
                )
                categories.setdefault(case["category"], {"cases": 0, "passed": 0})["cases"] += 1
                continue
            elapsed = (time.perf_counter() - started) * 1000
            expect = case["expect"] if isinstance(case["expect"], list) else [case["expect"]]
            outcome = _outcome(response)
            reasons = []
            if outcome not in expect:
                reasons.append(f"outcome={outcome}")
            if outcome == "answer" and case.get("sources") and not offline:
                cited = {source.name for source in response.sources}
                if not cited.intersection(case["sources"]):
                    reasons.append("cited_wrong_source")
            if outcome == "answer" and case.get("sources"):
                if not set(retrieved).intersection(case["sources"]):
                    reasons.append("retrieval_miss")
            if outcome == "answer" and not offline:
                for pattern in case.get("must", []):
                    if not re.search(pattern, response.answer, re.I):
                        reasons.append(f"missing:{pattern}")
                for pattern in case.get("forbid", []):
                    if re.search(pattern, response.answer, re.I):
                        reasons.append(f"forbidden:{pattern}")
            bad_suggestions = _bad_suggestions(knowledge, response.suggested_questions)
            if bad_suggestions:
                reasons.append("unanswerable_suggestion")
            stats = categories.setdefault(case["category"], {"cases": 0, "passed": 0})
            stats["cases"] += 1
            stats["passed"] += int(not reasons)
            details.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "question": case["question"],
                    "passed": not reasons,
                    "reasons": reasons,
                    "outcome": outcome,
                    "retrieved": sorted(set(retrieved)),
                    "provider_calls": counting.calls,
                    "latency_ms": round(elapsed, 1),
                    "suggested_questions": response.suggested_questions,
                    "answer": response.answer if not offline else None,
                }
            )
    finally:
        knowledge.search = original_search
    total = sum(stats["cases"] for stats in categories.values())
    passed = sum(stats["passed"] for stats in categories.values())
    return {
        "kind": "conversation_routing" if offline else "conversation_end_to_end",
        "cases": total,
        "passed": passed,
        "pass_rate": passed / total if total else None,
        "categories": categories,
        "avg_provider_calls": round(
            sum(d.get("provider_calls", 0) for d in details) / max(1, len(details)), 2
        ),
        "results": details,
    }


def _bad_suggestions(knowledge, suggestions: list[str]) -> list[str]:
    """A suggestion is unhelpful when the bot would not answer it from documents."""
    from eve_ah.conversation import classify_intent

    bad = []
    for question in suggestions:
        intent = classify_intent(question)
        if intent == "capability":
            continue
        if intent != "factual" or not knowledge.search(question):
            bad.append(question)
    return bad

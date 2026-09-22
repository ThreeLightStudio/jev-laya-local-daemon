from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_PATH = ROOT / "benchmarks" / "statecarry" / "scenarios.json"
RESULTS_DIR = ROOT / "benchmarks" / "statecarry" / "results"
DEFAULT_BASE_URL = os.getenv("DECISION_API_URL", "http://127.0.0.1:8787").rstrip("/")

ACTIONS: dict[str, str] = {
    "continue": "Continue the known unfinished work from its current next step.",
    "inspect": "Inspect the current repository or workspace state before continuing.",
    "reanalyze": "Refresh the project understanding before choosing further work.",
    "review_result": "Review the result returned by delegated or completed work.",
    "wait": "Wait because the required current process is already in progress.",
    "switch_work": "Temporarily switch to an independent work item that can progress now.",
    "reconnect": "Reconnect the project source before relying on current-state decisions.",
    "choose_work": "Choose which unfinished work item is the current work.",
    "define_direction": "Confirm or define the current project direction.",
    "review_direction": "Review a conflict between current work and a project constraint.",
    "review_release": "Review release or delivery state that currently needs attention.",
    "review_completion": "Review whether the selected work should be marked complete.",
    "review_plan": "Re-check an older saved work plan against the current project state.",
    "start_work": "Start the already queued next work item.",
    "choose_next_work": "Choose the next work item for the active direction.",
}

SIGNAL_QUESTIONS: dict[str, str] = {
    "safe_to_continue": (
        "Is it safe to immediately continue or start the known work without first "
        "refreshing, inspecting, reviewing, reconnecting, or waiting?"
    ),
    "needs_reanalysis": (
        "Has the project changed enough that the saved project understanding or work plan "
        "must be refreshed before it is trusted?"
    ),
    "needs_inspection": (
        "Does the current repository or workspace state need inspection before work can safely continue?"
    ),
    "needs_review": (
        "Is there a result, completion claim, direction conflict, release issue, or stale plan "
        "that requires explicit review before normal work continues?"
    ),
    "must_wait": (
        "Should the system wait because required work is already in progress and there is no useful "
        "independent work to switch to?"
    ),
}

SCORE_LEVELS = [
    "No intervention is needed; normal work can continue.",
    "Low attention; a routine selection or transition is needed.",
    "Medium attention; inspect, refresh, or review before proceeding.",
    "High attention; progress is blocked or an important conflict/failure needs review.",
    "Critical attention; delivery or project safety requires immediate review.",
]


def load_scenarios() -> list[dict[str, Any]]:
    scenarios = json.loads(SCENARIOS_PATH.read_text())
    ids = [scenario["id"] for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("Scenario ids must be unique")
    unknown = sorted({scenario["expected_action"] for scenario in scenarios} - ACTIONS.keys())
    if unknown:
        raise ValueError(f"Unknown expected actions: {unknown}")
    return scenarios


def stable_rng(seed: int, *parts: str) -> random.Random:
    value = seed
    for part in parts:
        for char in part:
            value = (value * 131 + ord(char)) % (2**63 - 1)
    return random.Random(value)


def choice_criteria(
    expected: str,
    count: int,
    *,
    seed: int,
    token: str,
    shuffle: bool = False,
) -> dict[str, str]:
    names = list(ACTIONS)
    if count >= len(names):
        selected = names[:]
    else:
        others = [name for name in names if name != expected]
        rng = stable_rng(seed, token, str(count), "selection")
        rng.shuffle(others)
        selected = [expected, *others[: count - 1]]
    if shuffle:
        stable_rng(seed, token, str(count), "order").shuffle(selected)
    else:
        selected.sort(key=names.index)
    return {name: ACTIONS[name] for name in selected}


def noise_state(state: dict[str, Any], count: int) -> dict[str, Any]:
    noisy = dict(state)
    for index in range(1, count + 1):
        noisy[f"synthetic_metadata_{index:02d}"] = (
            f"Unrelated synthetic metadata item {index}; it does not describe current work, "
            "project freshness, repository safety, delivery, or direction."
        )
    return noisy


def represented_state(scenario: dict[str, Any], variant: str) -> Any:
    state = scenario["state"]
    if variant == "canonical":
        return dict(state)
    if variant == "text":
        return scenario["paraphrase"]
    if variant == "nested":
        return {"project": {"resume_context": dict(state)}}
    if variant == "reordered":
        return dict(reversed(list(state.items())))
    if variant.startswith("noise-"):
        return noise_state(state, int(variant.split("-", 1)[1]))
    if variant == "korean":
        return scenario["korean"]
    raise ValueError(f"Unknown representation variant: {variant}")


def choice_question(criteria: dict[str, str], instruction: str | None = None) -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": instruction or "Choose the next StateCarry action for this project state.",
        "criteria": criteria,
    }


def noul_questions() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "type": "noul",
            "instructions": instruction,
            "criteria": {
                "true": "The condition is present in the current state.",
                "false": "The condition is not present in the current state.",
            },
        }
        for key, instruction in SIGNAL_QUESTIONS.items()
    }


def score_question() -> dict[str, Any]:
    return {
        "type": "score",
        "instructions": "How much intervention is needed before normal project work can proceed?",
        "criteria": SCORE_LEVELS,
    }


def make_case(
    *,
    case_id: str,
    family: str,
    variant: str,
    state: Any,
    questions: dict[str, dict[str, Any]],
    expected: dict[str, Any],
    scenario_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "scenario_id": scenario_id,
        "family": family,
        "variant": variant,
        "state": state,
        "questions": questions,
        "expected": expected,
        "meta": meta or {},
    }


def base_cases(scenarios: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    representation_variants = ["text", "nested", "reordered", "noise-8", "noise-32"]
    option_counts = [2, 4, 8, len(ACTIONS)]
    for scenario in scenarios:
        scenario_id = scenario["id"]
        expected = scenario["expected_action"]
        canonical_eight = choice_criteria(expected, 8, seed=seed, token=scenario_id)
        for count in option_counts:
            criteria = choice_criteria(expected, count, seed=seed, token=scenario_id)
            cases.append(
                make_case(
                    case_id=f"{scenario_id}::choice-{count}",
                    scenario_id=scenario_id,
                    family="choice",
                    variant=f"choice-{count}",
                    state=represented_state(scenario, "canonical"),
                    questions={"next_action": choice_question(criteria)},
                    expected={"next_action": expected},
                    meta={"option_count": len(criteria), "representation": "canonical"},
                )
            )
        shuffled_names = list(canonical_eight)
        stable_rng(seed, scenario_id, "8", "order").shuffle(shuffled_names)
        shuffled = {name: canonical_eight[name] for name in shuffled_names}
        cases.append(
            make_case(
                case_id=f"{scenario_id}::choice-8-shuffled",
                scenario_id=scenario_id,
                family="choice",
                variant="choice-8-shuffled",
                state=represented_state(scenario, "canonical"),
                questions={"next_action": choice_question(shuffled)},
                expected={"next_action": expected},
                meta={"option_count": len(shuffled), "representation": "canonical"},
            )
        )
        for representation in representation_variants:
            cases.append(
                make_case(
                    case_id=f"{scenario_id}::{representation}",
                    scenario_id=scenario_id,
                    family="choice",
                    variant=representation,
                    state=represented_state(scenario, representation),
                    questions={"next_action": choice_question(dict(canonical_eight))},
                    expected={"next_action": expected},
                    meta={"option_count": len(canonical_eight), "representation": representation},
                )
            )
        if scenario.get("korean"):
            cases.append(
                make_case(
                    case_id=f"{scenario_id}::korean",
                    scenario_id=scenario_id,
                    family="choice",
                    variant="korean",
                    state=represented_state(scenario, "korean"),
                    questions={"next_action": choice_question(dict(canonical_eight))},
                    expected={"next_action": expected},
                    meta={"option_count": len(canonical_eight), "representation": "korean"},
                )
            )
        cases.append(
            make_case(
                case_id=f"{scenario_id}::signals",
                scenario_id=scenario_id,
                family="noul",
                variant="signals",
                state=represented_state(scenario, "canonical"),
                questions=noul_questions(),
                expected=dict(scenario["signals"]),
            )
        )
        cases.append(
            make_case(
                case_id=f"{scenario_id}::urgency",
                scenario_id=scenario_id,
                family="score",
                variant="urgency",
                state=represented_state(scenario, "canonical"),
                questions={"intervention": score_question()},
                expected={"intervention": scenario["urgency"]},
            )
        )
    return cases


def challenge_cases(seed: int) -> list[dict[str, Any]]:
    rows: list[tuple[str, str, Any, bool]] = [
        (
            "temporal-latest-clean",
            "continue",
            {
                "history": "Yesterday the build failed and work stopped.",
                "current": "The latest build passes, the task is unfinished, and its next implementation step is known.",
                "analysis": "The current project understanding was checked after the latest build.",
            },
            False,
        ),
        (
            "temporal-latest-stale",
            "reanalyze",
            {
                "history": "The project analysis was accurate when it was created.",
                "current": "A major architecture change was completed after that analysis.",
                "repository": "The new architecture is intentional and understood.",
            },
            False,
        ),
        (
            "negation-no-failure",
            "continue",
            "The current task is unfinished. The latest build did not fail. There are no unexplained local changes, and the saved project understanding is not stale.",
            False,
        ),
        (
            "double-negation-project-changed",
            "reanalyze",
            "It is not true that the project stayed unchanged after the saved analysis. A large intentional source reorganization happened later, so the old analysis is no longer current.",
            False,
        ),
        (
            "release-secondary-to-active-work",
            "continue",
            {
                "work": "The selected implementation work is active and has a known next step.",
                "release": "A delivery issue also needs attention, but it does not block the selected implementation.",
                "analysis": "The project state is current.",
            },
            True,
        ),
        (
            "other-result-secondary-to-current-work",
            "continue",
            {
                "work": "The selected work is active and ready to continue.",
                "other_result": "A separate work item has a result ready, but it blocks nothing in the selected work.",
                "analysis": "The project state is current.",
            },
            True,
        ),
        (
            "stale-return-point-with-explicit-fresh-match",
            "continue",
            {
                "work": "The selected work is unfinished.",
                "return_point": "The saved return point predates the latest project check.",
                "match": "A fresh explicit interpretation links the current project state to this same work and provides a valid next action.",
                "analysis": "The latest project state is checked.",
            },
            False,
        ),
        (
            "missing-selection-with-one-unmatched-proposal",
            "choose_work",
            {
                "work": "No durable current work is selected.",
                "proposal": "Fresh evidence contains one unfinished work proposal that has not been confirmed as current.",
                "analysis": "The project state is current.",
            },
            False,
        ),
        (
            "old-conflict-resolved-currently",
            "continue",
            {
                "history": "An older project state had a direction conflict.",
                "current": "The conflict has been resolved and the current direction is confirmed.",
                "work": "The selected unfinished work has a clear next step.",
                "analysis": "The project state is current.",
            },
            False,
        ),
        (
            "ambiguous-docs-and-config-change",
            "review_plan",
            {
                "work": "The selected task has a saved resume point.",
                "changes": "Documentation changed and one configuration file changed after the resume point.",
                "analysis": "The latest project state is checked, but no explicit fresh match confirms the old plan.",
            },
            True,
        ),
    ]
    cases = []
    for challenge_id, expected, state, ambiguous in rows:
        criteria = choice_criteria(expected, 8, seed=seed, token=f"challenge:{challenge_id}", shuffle=True)
        cases.append(
            make_case(
                case_id=f"challenge::{challenge_id}",
                family="challenge",
                variant=challenge_id,
                state=state,
                questions={"next_action": choice_question(criteria)},
                expected={"next_action": expected},
                meta={"ambiguous": ambiguous, "option_count": len(criteria)},
            )
        )
    return cases


def repeat_cases(scenarios: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    preferred = [
        "continue-known-step",
        "inspect-unexplained-changes",
        "reanalyze-major-refactor",
        "review-result-ready",
        "wait-running-check",
        "reconnect-disconnected-project",
        "review-direction-conflict",
        "review-release-problem",
    ]
    by_id = {scenario["id"]: scenario for scenario in scenarios}
    cases = []
    for scenario_id in preferred:
        scenario = by_id[scenario_id]
        expected = scenario["expected_action"]
        criteria = choice_criteria(expected, 8, seed=seed, token=scenario_id)
        for repeat in range(1, 4):
            cases.append(
                make_case(
                    case_id=f"{scenario_id}::repeat-{repeat}",
                    scenario_id=scenario_id,
                    family="repeat",
                    variant=f"repeat-{repeat}",
                    state=represented_state(scenario, "canonical"),
                    questions={"next_action": choice_question(criteria)},
                    expected={"next_action": expected},
                    meta={"repeat_group": scenario_id},
                )
            )
    return cases


def same_state_batch_cases(scenarios: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    selected_ids = [
        "continue-known-step",
        "inspect-unexplained-changes",
        "reanalyze-major-refactor",
        "review-result-ready",
    ]
    by_id = {scenario["id"]: scenario for scenario in scenarios}
    cases = []
    for scenario_id in selected_ids:
        scenario = by_id[scenario_id]
        expected = scenario["expected_action"]
        criteria = choice_criteria(expected, 8, seed=seed, token=scenario_id)
        for size in [1, 2, 4, 8, 16]:
            questions = {
                f"next_action_{index:02d}": choice_question(
                    criteria,
                    f"Choose the next StateCarry action for this same project state. Equivalent check number {index}.",
                )
                for index in range(1, size + 1)
            }
            expected_map = {key: expected for key in questions}
            cases.append(
                make_case(
                    case_id=f"{scenario_id}::same-state-batch-{size}",
                    scenario_id=scenario_id,
                    family="same_state_batch",
                    variant=f"batch-{size}",
                    state=represented_state(scenario, "canonical"),
                    questions=questions,
                    expected=expected_map,
                    meta={"question_count": size},
                )
            )
    return cases


def cross_case_batch_cases(scenarios: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    pool = [
        scenario
        for scenario in scenarios
        if scenario["id"]
        in {
            "continue-known-step",
            "inspect-unexplained-changes",
            "reanalyze-major-refactor",
            "review-result-ready",
            "wait-running-check",
            "reconnect-disconnected-project",
            "review-direction-conflict",
            "review-release-problem",
        }
    ]
    cases = []
    for size in [2, 4, 8]:
        selected = pool[:size]
        state = {f"case_{index:02d}": scenario["state"] for index, scenario in enumerate(selected, 1)}
        questions = {}
        expected = {}
        for index, scenario in enumerate(selected, 1):
            key = f"case_{index:02d}"
            criteria = choice_criteria(
                scenario["expected_action"],
                8,
                seed=seed,
                token=scenario["id"],
            )
            questions[key] = choice_question(
                criteria,
                f"Consider only state.{key}. Choose the next StateCarry action for that case.",
            )
            expected[key] = scenario["expected_action"]
        cases.append(
            make_case(
                case_id=f"cross-case-batch::{size}",
                family="cross_case_batch",
                variant=f"batch-{size}",
                state=state,
                questions=questions,
                expected=expected,
                meta={
                    "question_count": size,
                    "scenario_ids": [scenario["id"] for scenario in selected],
                },
            )
        )
    return cases


def mixed_cases(scenarios: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    selected = scenarios[:6]
    cases = []
    for scenario in selected:
        expected_action = scenario["expected_action"]
        criteria = choice_criteria(expected_action, 8, seed=seed, token=scenario["id"])
        questions = {
            "next_action": choice_question(criteria),
            **noul_questions(),
            "intervention": score_question(),
        }
        expected = {
            "next_action": expected_action,
            **scenario["signals"],
            "intervention": scenario["urgency"],
        }
        cases.append(
            make_case(
                case_id=f"{scenario['id']}::mixed",
                scenario_id=scenario["id"],
                family="mixed",
                variant="choice+noul+score",
                state=represented_state(scenario, "canonical"),
                questions=questions,
                expected=expected,
                meta={"question_count": len(questions)},
            )
        )
    return cases


def request_ab_cases(scenarios: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    selected_ids = [
        "continue-known-step",
        "inspect-unexplained-changes",
        "reanalyze-major-refactor",
        "review-result-ready",
        "wait-running-check",
        "reconnect-disconnected-project",
        "review-direction-conflict",
        "review-release-problem",
    ]
    by_id = {scenario["id"]: scenario for scenario in scenarios}
    cases = []
    for scenario_id in selected_ids:
        scenario = by_id[scenario_id]
        expected_action = scenario["expected_action"]
        criteria = choice_criteria(expected_action, 8, seed=seed, token=scenario_id)
        questions = {
            "next_action": choice_question(criteria),
            **noul_questions(),
            "intervention": score_question(),
        }
        expected = {
            "next_action": expected_action,
            **scenario["signals"],
            "intervention": scenario["urgency"],
        }
        state = represented_state(scenario, "canonical")
        cases.append(
            make_case(
                case_id=f"{scenario_id}::request-ab-batch",
                scenario_id=scenario_id,
                family="request_ab",
                variant="batch",
                state=state,
                questions=questions,
                expected=expected,
                meta={"mode": "batch", "question_count": len(questions)},
            )
        )
        for question_id, question in questions.items():
            cases.append(
                make_case(
                    case_id=f"{scenario_id}::request-ab-single::{question_id}",
                    scenario_id=scenario_id,
                    family="request_ab",
                    variant=f"single-{question_id}",
                    state=state,
                    questions={question_id: question},
                    expected={question_id: expected[question_id]},
                    meta={
                        "mode": "single",
                        "question_id": question_id,
                        "question_count": 1,
                    },
                )
            )
    return cases


def build_cases(scenarios: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    return [
        *base_cases(scenarios, seed),
        *challenge_cases(seed),
        *repeat_cases(scenarios, seed),
        *same_state_batch_cases(scenarios, seed),
        *cross_case_batch_cases(scenarios, seed),
        *mixed_cases(scenarios, seed),
        *request_ab_cases(scenarios, seed),
    ]


def request_json(url: str, payload: dict[str, Any], timeout: float = 90.0) -> tuple[dict[str, Any], float]:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(5):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.load(response)
            return result, (time.perf_counter() - started) * 1000
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 502, 503} or attempt == 4:
                detail = exc.read().decode(errors="replace")[:500]
                raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == 4:
                raise RuntimeError(f"Request failed: {type(exc).__name__}") from exc
        time.sleep(min(2**attempt, 8))
    raise RuntimeError(f"Request failed: {type(last_error).__name__ if last_error else 'unknown'}")


def get_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def run_case(base_url: str, provider: str, case: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "provider": provider,
        "state": case["state"],
        "questions": case["questions"],
    }
    try:
        response, latency_ms = request_json(f"{base_url}/v1/decide", payload)
        return {
            "case_id": case["case_id"],
            "scenario_id": case["scenario_id"],
            "family": case["family"],
            "variant": case["variant"],
            "expected": case["expected"],
            "meta": case["meta"],
            "latency_ms": round(latency_ms, 3),
            "model": response.get("model"),
            "usage": response.get("usage", {}),
            "answers": response.get("answers", {}),
            "error": None,
        }
    except Exception as exc:
        return {
            "case_id": case["case_id"],
            "scenario_id": case["scenario_id"],
            "family": case["family"],
            "variant": case["variant"],
            "expected": case["expected"],
            "meta": case["meta"],
            "latency_ms": None,
            "model": None,
            "usage": {},
            "answers": {},
            "error": str(exc),
        }


def answer_choice(answer: dict[str, Any]) -> str | None:
    value = answer.get("choice")
    return value if isinstance(value, str) else None


def answer_probability(answer: dict[str, Any], choice: str | None) -> float | None:
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or choice is None:
        return None
    value = probabilities.get(choice)
    return float(value) if isinstance(value, (int, float)) else None


def answer_noul(answer: dict[str, Any]) -> float | None:
    value = answer.get("noul")
    return float(value) if isinstance(value, (int, float)) else None


def answer_score_level(answer: dict[str, Any]) -> int | None:
    probabilities = answer.get("probabilities")
    if isinstance(probabilities, dict) and probabilities:
        numeric = []
        for key, value in probabilities.items():
            try:
                numeric.append((int(key), float(value)))
            except (TypeError, ValueError):
                continue
        if numeric:
            return max(numeric, key=lambda item: item[1])[0]
    score = answer.get("score")
    if isinstance(score, (int, float)):
        return max(0, min(len(SCORE_LEVELS) - 1, round(float(score))))
    return None


def answer_score_value(answer: dict[str, Any]) -> float | None:
    value = answer.get("score")
    return float(value) if isinstance(value, (int, float)) else None


def usage_tokens(record: dict[str, Any], key: str) -> int:
    value = record.get("usage", {}).get(key)
    return int(value) if isinstance(value, (int, float)) else 0


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def best_binary_threshold(values: list[tuple[float, bool]]) -> dict[str, Any]:
    if not values:
        return {}
    unique = sorted({value for value, _ in values})
    candidates = [0.0, 1.000001, *unique]
    candidates.extend((a + b) / 2 for a, b in zip(unique, unique[1:]))
    best: dict[str, Any] | None = None
    for threshold in candidates:
        tp = fp = fn = tn = 0
        for value, expected in values:
            predicted = value >= threshold
            if predicted and expected:
                tp += 1
            elif predicted:
                fp += 1
            elif expected:
                fn += 1
            else:
                tn += 1
        tpr = tp / (tp + fn) if tp + fn else 0.0
        tnr = tn / (tn + fp) if tn + fp else 0.0
        accuracy = (tp + tn) / len(values)
        balanced = (tpr + tnr) / 2
        candidate = {
            "threshold": threshold,
            "accuracy": accuracy,
            "balanced_accuracy": balanced,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        }
        if best is None or (balanced, accuracy, -threshold) > (
            best["balanced_accuracy"],
            best["accuracy"],
            -best["threshold"],
        ):
            best = candidate
    return best or {}


def summarize_provider(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [record for record in records if record["error"]]
    latencies = [
        float(record["latency_ms"])
        for record in records
        if isinstance(record.get("latency_ms"), (int, float))
    ]

    choice_rows = [
        record
        for record in records
        if record["family"] in {"choice", "challenge"}
        and not record["error"]
        and "next_action" in record["expected"]
    ]
    by_variant: dict[str, list[bool]] = defaultdict(list)
    calibration: dict[str, list[bool]] = defaultdict(list)
    choice_correct = 0
    for record in choice_rows:
        answer = record["answers"].get("next_action", {})
        actual = answer_choice(answer)
        correct = actual == record["expected"]["next_action"]
        choice_correct += int(correct)
        by_variant[record["variant"]].append(correct)
        probability = answer_probability(answer, actual)
        if probability is not None:
            lower = min(0.9, int(probability * 10) / 10)
            key = f"{lower:.1f}-{min(1.0, lower + 0.1):.1f}"
            calibration[key].append(correct)

    metamorphic_groups: dict[str, list[str | None]] = defaultdict(list)
    for record in records:
        if record["family"] != "choice" or record["error"] or not record["scenario_id"]:
            continue
        if record["variant"] not in {
            "choice-8",
            "choice-8-shuffled",
            "text",
            "nested",
            "reordered",
            "noise-8",
            "noise-32",
            "korean",
        }:
            continue
        metamorphic_groups[record["scenario_id"]].append(
            answer_choice(record["answers"].get("next_action", {}))
        )
    metamorphic_consistency = []
    for scenario_id, values in metamorphic_groups.items():
        filtered = [value for value in values if value is not None]
        if filtered:
            metamorphic_consistency.append(len(set(filtered)) == 1)

    noul_records = [record for record in records if record["family"] == "noul" and not record["error"]]
    noul_summary: dict[str, Any] = {}
    for signal in SIGNAL_QUESTIONS:
        values = []
        for record in noul_records:
            value = answer_noul(record["answers"].get(signal, {}))
            expected = record["expected"].get(signal)
            if value is not None and isinstance(expected, bool):
                values.append((value, expected))
        if not values:
            continue
        accuracy_05 = sum((value >= 0.5) == expected for value, expected in values) / len(values)
        brier = sum((value - float(expected)) ** 2 for value, expected in values) / len(values)
        noul_summary[signal] = {
            "cases": len(values),
            "accuracy_at_0_5": accuracy_05,
            "brier": brier,
            "best_threshold": best_binary_threshold(values),
            "positive_mean": statistics.fmean(value for value, expected in values if expected)
            if any(expected for _, expected in values)
            else None,
            "negative_mean": statistics.fmean(value for value, expected in values if not expected)
            if any(not expected for _, expected in values)
            else None,
        }

    score_records = [record for record in records if record["family"] == "score" and not record["error"]]
    score_pairs = []
    for record in score_records:
        level = answer_score_level(record["answers"].get("intervention", {}))
        expected = record["expected"].get("intervention")
        if level is not None and isinstance(expected, int):
            score_pairs.append((level, expected))

    repeat_groups: dict[str, list[str | None]] = defaultdict(list)
    for record in records:
        if record["family"] == "repeat" and not record["error"]:
            repeat_groups[record["meta"]["repeat_group"]].append(
                answer_choice(record["answers"].get("next_action", {}))
            )
    repeat_consistency = {
        group: len(set(value for value in values if value is not None)) <= 1
        for group, values in repeat_groups.items()
    }

    canonical_choices = {
        record["scenario_id"]: answer_choice(record["answers"].get("next_action", {}))
        for record in records
        if record["family"] == "choice"
        and record["variant"] == "choice-8"
        and record["scenario_id"]
        and not record["error"]
    }
    batch_summary: dict[str, dict[str, Any]] = {}
    for family in ["same_state_batch", "cross_case_batch"]:
        grouped: dict[int, list[bool]] = defaultdict(list)
        consistency: dict[int, list[bool]] = defaultdict(list)
        single_choices: dict[str, str | None] = {}
        if family == "same_state_batch":
            for record in records:
                if (
                    record["family"] == family
                    and not record["error"]
                    and int(record["meta"]["question_count"]) == 1
                    and record["scenario_id"]
                ):
                    single_choices[record["scenario_id"]] = answer_choice(
                        record["answers"].get("next_action_01", {})
                    )
        for record in records:
            if record["family"] != family or record["error"]:
                continue
            size = int(record["meta"]["question_count"])
            scenario_ids = record["meta"].get("scenario_ids", [])
            for index, (key, expected) in enumerate(record["expected"].items()):
                actual = answer_choice(record["answers"].get(key, {}))
                grouped[size].append(actual == expected)
                if family == "same_state_batch" and record["scenario_id"] in single_choices:
                    consistency[size].append(actual == single_choices[record["scenario_id"]])
                if family == "cross_case_batch" and index < len(scenario_ids):
                    baseline = canonical_choices.get(scenario_ids[index])
                    if baseline is not None:
                        consistency[size].append(actual == baseline)
        batch_summary[family] = {
            str(size): {
                "questions": len(values),
                "accuracy": sum(values) / len(values) if values else None,
                "consistency_with_baseline": (
                    sum(consistency[size]) / len(consistency[size])
                    if consistency[size]
                    else None
                ),
            }
            for size, values in sorted(grouped.items())
        }

    mixed_records = [record for record in records if record["family"] == "mixed" and not record["error"]]
    mixed_checks: dict[str, list[bool]] = {"choice": [], "noul": [], "score": []}
    for record in mixed_records:
        for key, expected in record["expected"].items():
            answer = record["answers"].get(key, {})
            if key == "next_action":
                mixed_checks["choice"].append(answer_choice(answer) == expected)
            elif key == "intervention":
                mixed_checks["score"].append(answer_score_level(answer) == expected)
            else:
                value = answer_noul(answer)
                if value is not None:
                    mixed_checks["noul"].append((value >= 0.5) == expected)

    request_ab_records = [
        record for record in records if record["family"] == "request_ab" and not record["error"]
    ]
    request_ab_by_scenario: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"batch": None, "single": {}}
    )
    for record in request_ab_records:
        scenario_id = record["scenario_id"]
        if not scenario_id:
            continue
        if record["meta"]["mode"] == "batch":
            request_ab_by_scenario[scenario_id]["batch"] = record
        else:
            request_ab_by_scenario[scenario_id]["single"][record["meta"]["question_id"]] = record

    request_ab_quality: dict[str, dict[str, list[bool]]] = {
        "choice": {"single": [], "batch": []},
        "noul": {"single": [], "batch": []},
        "score": {"single": [], "batch": []},
    }
    request_ab_consistency: list[bool] = []
    request_ab_noul_delta: list[float] = []
    request_ab_score_delta: list[float] = []
    request_ab_latency: list[dict[str, float]] = []
    request_ab_input_tokens = {"single": 0, "batch": 0}
    request_ab_output_tokens = {"single": 0, "batch": 0}

    for scenario_id, group in sorted(request_ab_by_scenario.items()):
        batch = group["batch"]
        singles = group["single"]
        if not batch or not singles:
            continue
        single_latency = sum(
            float(record["latency_ms"])
            for record in singles.values()
            if isinstance(record.get("latency_ms"), (int, float))
        )
        batch_latency = (
            float(batch["latency_ms"])
            if isinstance(batch.get("latency_ms"), (int, float))
            else 0.0
        )
        request_ab_latency.append(
            {
                "single_total_ms": single_latency,
                "batch_ms": batch_latency,
            }
        )
        request_ab_input_tokens["single"] += sum(
            usage_tokens(record, "input_tokens") for record in singles.values()
        )
        request_ab_input_tokens["batch"] += usage_tokens(batch, "input_tokens")
        request_ab_output_tokens["single"] += sum(
            usage_tokens(record, "output_tokens") for record in singles.values()
        )
        request_ab_output_tokens["batch"] += usage_tokens(batch, "output_tokens")

        for question_id, single in singles.items():
            expected = single["expected"][question_id]
            single_answer = single["answers"].get(question_id, {})
            batch_answer = batch["answers"].get(question_id, {})
            if question_id == "next_action":
                single_value = answer_choice(single_answer)
                batch_value = answer_choice(batch_answer)
                request_ab_quality["choice"]["single"].append(single_value == expected)
                request_ab_quality["choice"]["batch"].append(batch_value == expected)
                request_ab_consistency.append(single_value == batch_value)
            elif question_id == "intervention":
                single_level = answer_score_level(single_answer)
                batch_level = answer_score_level(batch_answer)
                request_ab_quality["score"]["single"].append(single_level == expected)
                request_ab_quality["score"]["batch"].append(batch_level == expected)
                request_ab_consistency.append(single_level == batch_level)
                single_score = answer_score_value(single_answer)
                batch_score = answer_score_value(batch_answer)
                if single_score is not None and batch_score is not None:
                    request_ab_score_delta.append(abs(single_score - batch_score))
            else:
                single_value = answer_noul(single_answer)
                batch_value = answer_noul(batch_answer)
                if single_value is None or batch_value is None:
                    continue
                single_bool = single_value >= 0.5
                batch_bool = batch_value >= 0.5
                request_ab_quality["noul"]["single"].append(single_bool == expected)
                request_ab_quality["noul"]["batch"].append(batch_bool == expected)
                request_ab_consistency.append(single_bool == batch_bool)
                request_ab_noul_delta.append(abs(single_value - batch_value))

    single_latency_total = sum(row["single_total_ms"] for row in request_ab_latency)
    batch_latency_total = sum(row["batch_ms"] for row in request_ab_latency)
    request_ab_summary = {
        "scenarios": len(request_ab_latency),
        "questions_per_scenario": 7,
        "quality": {
            primitive: {
                mode: {
                    "questions": len(values),
                    "accuracy": sum(values) / len(values) if values else None,
                }
                for mode, values in modes.items()
            }
            for primitive, modes in request_ab_quality.items()
        },
        "decision_consistency": {
            "questions": len(request_ab_consistency),
            "rate": (
                sum(request_ab_consistency) / len(request_ab_consistency)
                if request_ab_consistency
                else None
            ),
            "mean_abs_noul_delta": (
                statistics.fmean(request_ab_noul_delta) if request_ab_noul_delta else None
            ),
            "mean_abs_score_delta": (
                statistics.fmean(request_ab_score_delta) if request_ab_score_delta else None
            ),
        },
        "latency_ms": {
            "single_requests_total": single_latency_total,
            "batch_requests_total": batch_latency_total,
            "single_mean_per_scenario": (
                statistics.fmean(row["single_total_ms"] for row in request_ab_latency)
                if request_ab_latency
                else None
            ),
            "batch_mean_per_scenario": (
                statistics.fmean(row["batch_ms"] for row in request_ab_latency)
                if request_ab_latency
                else None
            ),
            "batch_speedup": (
                single_latency_total / batch_latency_total if batch_latency_total else None
            ),
        },
        "tokens": {
            "input": request_ab_input_tokens,
            "output": request_ab_output_tokens,
        },
    }

    models = sorted({record["model"] for record in records if record.get("model")})
    return {
        "records": len(records),
        "errors": len(errors),
        "models": models,
        "latency_ms": {
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
            "mean": statistics.fmean(latencies) if latencies else None,
        },
        "choice": {
            "cases": len(choice_rows),
            "accuracy": choice_correct / len(choice_rows) if choice_rows else None,
            "by_variant": {
                variant: {
                    "cases": len(values),
                    "accuracy": sum(values) / len(values) if values else None,
                }
                for variant, values in sorted(by_variant.items())
            },
            "metamorphic_consistency": (
                sum(metamorphic_consistency) / len(metamorphic_consistency)
                if metamorphic_consistency
                else None
            ),
            "calibration": {
                key: {"cases": len(values), "accuracy": sum(values) / len(values)}
                for key, values in sorted(calibration.items())
            },
        },
        "noul": noul_summary,
        "score": {
            "cases": len(score_pairs),
            "top_level_accuracy": (
                sum(actual == expected for actual, expected in score_pairs) / len(score_pairs)
                if score_pairs
                else None
            ),
            "mae": (
                statistics.fmean(abs(actual - expected) for actual, expected in score_pairs)
                if score_pairs
                else None
            ),
        },
        "repeat": {
            "groups": len(repeat_consistency),
            "fully_consistent": sum(repeat_consistency.values()),
            "rate": (
                sum(repeat_consistency.values()) / len(repeat_consistency)
                if repeat_consistency
                else None
            ),
            "by_group": repeat_consistency,
        },
        "batching": batch_summary,
        "mixed_question_accuracy": {
            key: (sum(values) / len(values) if values else None)
            for key, values in mixed_checks.items()
        },
        "request_ab": request_ab_summary,
    }


def provider_disagreement(provider_records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    if len(provider_records) < 2:
        return {}
    names = list(provider_records)
    left_name, right_name = names[0], names[1]
    left = {
        record["case_id"]: record
        for record in provider_records[left_name]
        if record["family"] in {"choice", "challenge"} and not record["error"]
    }
    right = {
        record["case_id"]: record
        for record in provider_records[right_name]
        if record["family"] in {"choice", "challenge"} and not record["error"]
    }
    shared = sorted(set(left) & set(right))
    buckets = {"both_correct": 0, f"{left_name}_only": 0, f"{right_name}_only": 0, "both_wrong": 0}
    disagreements = []
    for case_id in shared:
        expected = left[case_id]["expected"]["next_action"]
        left_choice = answer_choice(left[case_id]["answers"].get("next_action", {}))
        right_choice = answer_choice(right[case_id]["answers"].get("next_action", {}))
        left_ok = left_choice == expected
        right_ok = right_choice == expected
        if left_ok and right_ok:
            buckets["both_correct"] += 1
        elif left_ok:
            buckets[f"{left_name}_only"] += 1
        elif right_ok:
            buckets[f"{right_name}_only"] += 1
        else:
            buckets["both_wrong"] += 1
        if left_choice != right_choice:
            disagreements.append(
                {
                    "case_id": case_id,
                    "expected": expected,
                    left_name: left_choice,
                    right_name: right_choice,
                }
            )
    return {
        "shared_choice_cases": len(shared),
        "same_top_choice": len(shared) - len(disagreements),
        "different_top_choice": len(disagreements),
        "outcome_buckets": buckets,
        "disagreements": disagreements,
    }


def assert_private_safe(value: Any) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    forbidden = {
        str(Path.home()),
        str(ROOT),
        "/Users/",
        "/home/",
        "/projects/",
        "file://",
    }
    leaks = sorted(fragment for fragment in forbidden if fragment and fragment in serialized)
    if leaks:
        raise RuntimeError(f"Privacy guard blocked result output containing absolute-path markers: {leaks}")


def write_results(payload: dict[str, Any]) -> None:
    assert_private_safe(payload)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    latest = RESULTS_DIR / "latest.json"
    summary = RESULTS_DIR / "summary.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    summary.write_text(
        json.dumps(
            {
                "schema_version": payload["schema_version"],
                "benchmark": payload["benchmark"],
                "run_at": payload["run_at"],
                "case_count": payload["case_count"],
                "providers": payload["summary"]["providers"],
                "comparison": payload["summary"]["comparison"],
                "privacy": payload["privacy"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the synthetic StateCarry decision benchmark")
    parser.add_argument(
        "--providers",
        default="laya,jev",
        help="Comma-separated providers. Default: laya,jev",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument(
        "--families",
        default="",
        help="Optional comma-separated family filter for focused runs",
    )
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    providers = [value.strip() for value in args.providers.split(",") if value.strip()]
    unknown = sorted(set(providers) - {"laya", "jev"})
    if unknown:
        raise SystemExit(f"Unknown providers: {', '.join(unknown)}")

    scenarios = load_scenarios()
    cases = build_cases(scenarios, args.seed)
    if args.families:
        allowed = {value.strip() for value in args.families.split(",") if value.strip()}
        cases = [case for case in cases if case["family"] in allowed]

    provider_status = get_json(f"{args.base_url}/v1/providers")
    for provider in providers:
        if provider == "jev" and not provider_status.get("jev", {}).get("configured"):
            raise SystemExit("Jev is not configured in the running daemon")
        if provider == "laya" and not provider_status.get("laya", {}).get("ready"):
            raise SystemExit("Laya is not ready in the running daemon")

    provider_records: dict[str, list[dict[str, Any]]] = {}
    for provider in providers:
        print(f"\n[{provider}] running {len(cases)} cases")
        records = []
        for index, case in enumerate(cases, 1):
            record = run_case(args.base_url, provider, case)
            records.append(record)
            if index % 25 == 0 or index == len(cases):
                errors = sum(bool(item["error"]) for item in records)
                print(f"  {index}/{len(cases)} complete, errors={errors}")
        provider_records[provider] = records

    summaries = {
        provider: summarize_provider(records)
        for provider, records in provider_records.items()
    }
    payload = {
        "schema_version": 1,
        "benchmark": "statecarry-synthetic-decision-suite",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
        "scenario_count": len(scenarios),
        "privacy": {
            "synthetic_only": True,
            "absolute_paths_written": False,
            "source_project_content_copied": False,
            "api_keys_written": False,
        },
        "providers": provider_records,
        "summary": {
            "providers": summaries,
            "comparison": provider_disagreement(provider_records),
        },
    }
    assert_private_safe(payload)
    if not args.no_write:
        write_results(payload)

    print("\nSummary")
    print("=" * 72)
    for provider in providers:
        summary = summaries[provider]
        print(
            f"{provider:<5} choice={summary['choice']['accuracy']:.1%} "
            f"score={summary['score']['top_level_accuracy']:.1%} "
            f"repeat={summary['repeat']['rate']:.1%} "
            f"errors={summary['errors']}"
        )
        print(
            f"      latency p50={summary['latency_ms']['p50']:.1f} ms "
            f"p95={summary['latency_ms']['p95']:.1f} ms"
        )
    comparison = payload["summary"]["comparison"]
    if comparison:
        print(
            f"provider top-choice disagreements: "
            f"{comparison['different_top_choice']}/{comparison['shared_choice_cases']}"
        )


if __name__ == "__main__":
    main()

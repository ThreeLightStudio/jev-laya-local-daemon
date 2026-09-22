from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_statecarry_benchmark.py"
SPEC = importlib.util.spec_from_file_location("statecarry_benchmark", SCRIPT)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_generated_suite_is_deterministic_and_keeps_expected_choice_available() -> None:
    scenarios = benchmark.load_scenarios()
    first = benchmark.build_cases(scenarios, 20260923)
    second = benchmark.build_cases(scenarios, 20260923)
    assert first == second
    choice_cases = [case for case in first if case["family"] in {"choice", "challenge"}]
    assert choice_cases
    for case in choice_cases:
        expected = case["expected"]["next_action"]
        assert expected in case["questions"]["next_action"]["criteria"]


def test_suite_covers_statecarry_specific_robustness_families() -> None:
    cases = benchmark.build_cases(benchmark.load_scenarios(), 20260923)
    families = {case["family"] for case in cases}
    assert {
        "choice",
        "noul",
        "score",
        "challenge",
        "repeat",
        "same_state_batch",
        "cross_case_batch",
        "mixed",
        "request_ab",
    } <= families
    variants = {case["variant"] for case in cases}
    assert {"text", "nested", "reordered", "noise-8", "noise-32", "korean"} <= variants


def test_representation_variants_keep_the_same_choice_set() -> None:
    cases = benchmark.build_cases(benchmark.load_scenarios(), 20260923)
    grouped = {}
    for case in cases:
        if case["family"] != "choice" or not case["scenario_id"]:
            continue
        if case["variant"] not in {
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
        grouped.setdefault(case["scenario_id"], []).append(
            set(case["questions"]["next_action"]["criteria"])
        )
    assert grouped
    for sets in grouped.values():
        assert all(options == sets[0] for options in sets[1:])


def test_request_ab_uses_identical_questions_for_single_and_batch_modes() -> None:
    cases = [
        case
        for case in benchmark.build_cases(benchmark.load_scenarios(), 20260923)
        if case["family"] == "request_ab"
    ]
    grouped = {}
    for case in cases:
        grouped.setdefault(case["scenario_id"], []).append(case)
    assert len(grouped) == 8
    for scenario_cases in grouped.values():
        batch = next(case for case in scenario_cases if case["meta"]["mode"] == "batch")
        singles = [case for case in scenario_cases if case["meta"]["mode"] == "single"]
        assert len(singles) == 7
        assert len(batch["questions"]) == 7
        for single in singles:
            question_id = single["meta"]["question_id"]
            assert single["state"] == batch["state"]
            assert single["questions"][question_id] == batch["questions"][question_id]
            assert single["expected"][question_id] == batch["expected"][question_id]


def test_privacy_guard_rejects_absolute_paths() -> None:
    benchmark.assert_private_safe({"safe": "synthetic state"})
    with pytest.raises(RuntimeError, match="Privacy guard"):
        benchmark.assert_private_safe({"leak": str(Path.home() / "private-project")})


def test_scenario_fixture_has_no_absolute_path_markers() -> None:
    benchmark.assert_private_safe(benchmark.load_scenarios())

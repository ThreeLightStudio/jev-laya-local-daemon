from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass


BASE_URL = os.getenv("DECISION_API_URL") or f"http://127.0.0.1:{os.getenv('DAEMON_PORT', '8787')}"
PROVIDER = os.getenv("DECISION_PROVIDER", "laya")
URL = f"{BASE_URL}/v1/decide"

QUESTIONS = {
    "tests_blocking": {
        "type": "noul",
        "instructions": (
            "Are failing tests currently the main blocker that should be handled "
            "before continuing other project work?"
        ),
    },
    "changes_need_inspection": {
        "type": "noul",
        "instructions": (
            "Are there local working-tree changes whose origin or purpose is unknown "
            "and that should be inspected before continuing?"
        ),
    },
    "analysis_stale": {
        "type": "noul",
        "instructions": (
            "Is the current project analysis stale or invalid enough that it should "
            "be refreshed before continuing?"
        ),
    },
    "ready_to_resume": {
        "type": "noul",
        "instructions": (
            "Is the project ready to immediately resume the known unfinished "
            "implementation work?"
        ),
    },
}

ACTION_TO_SIGNAL = {
    "test": "tests_blocking",
    "inspect": "changes_need_inspection",
    "reanalyze": "analysis_stale",
    "resume": "ready_to_resume",
}

CASES = [
    ("test-1", "test", {
        "tests": "47 tests are failing and must be fixed before the work can proceed.",
        "implementation": "The feature implementation itself is complete.",
        "repository": "There are no unexplained local working-tree changes to inspect.",
        "analysis": "The current project analysis is fresh.",
    }),
    ("test-2", "test", {
        "tests": "The build is blocked by multiple failing integration tests.",
        "implementation": "The intended code changes are already implemented.",
        "repository": "All local working-tree changes are understood and expected.",
        "analysis": "The current analysis accurately represents the repository.",
    }),
    ("test-3", "test", {
        "tests": "A regression test that previously passed is now failing after the latest implementation.",
        "implementation": "The implementation is complete enough to validate.",
        "repository": "There are no unknown local working-tree changes.",
        "analysis": "No project reanalysis is currently necessary.",
    }),
    ("test-4", "test", {
        "tests": "Tests fail consistently and the failure prevents release.",
        "implementation": "No additional feature implementation is currently needed.",
        "repository": "The current local changes are fully understood.",
        "analysis": "The analysis is recent and valid.",
    }),
    ("inspect-1", "inspect", {
        "tests": "All tests are passing.",
        "implementation": "There is no unfinished implementation step to resume.",
        "repository": "Several uncommitted local files appeared and their origin and purpose are unknown.",
        "analysis": "The current project analysis is fresh.",
    }),
    ("inspect-2", "inspect", {
        "tests": "Tests are currently passing.",
        "implementation": "No immediate implementation task is pending.",
        "repository": "The local working tree contains unexpected modifications that were not part of the current task.",
        "analysis": "The current analysis is still valid.",
    }),
    ("inspect-3", "inspect", {
        "tests": "There are no known test failures.",
        "implementation": "There is no clear implementation step until the local repository state is understood.",
        "repository": "Several generated and source files changed locally and it is unknown what caused those changes.",
        "analysis": "The analysis itself is recent.",
    }),
    ("inspect-4", "inspect", {
        "tests": "Tests are green.",
        "implementation": "The previous task appears complete.",
        "repository": "There are unexplained local working-tree changes and it is unclear whether they are intentional.",
        "analysis": "The project analysis is not stale.",
    }),
    ("reanalyze-1", "reanalyze", {
        "tests": "All tests pass.",
        "implementation": "There is no unfinished implementation to continue.",
        "repository": "There are no unexplained local working-tree changes; all current changes are understood.",
        "analysis": "The existing project analysis is invalid because it predates major architectural changes.",
    }),
    ("reanalyze-2", "reanalyze", {
        "tests": "There are no failing tests requiring attention.",
        "implementation": "There is no immediate implementation step.",
        "repository": "All local working-tree changes are known and understood.",
        "analysis": "The stored analysis was created three days ago and many important source files have changed since then.",
    }),
    ("reanalyze-3", "reanalyze", {
        "tests": "Tests are passing.",
        "implementation": "Continuing implementation safely requires an accurate understanding of the new architecture.",
        "repository": "The large refactor is intentional, committed, and understood; there are no unexplained local changes.",
        "analysis": "The current analysis describes the repository before the refactor and is no longer trustworthy.",
    }),
    ("reanalyze-4", "reanalyze", {
        "tests": "There are no blocking test failures.",
        "implementation": "No next implementation step should be chosen from the old project understanding.",
        "repository": "The project changed substantially, but the changes are known and there are no unexplained local working-tree modifications.",
        "analysis": "A fresh project analysis is required before work can continue safely.",
    }),
    ("resume-1", "resume", {
        "tests": "All tests are passing.",
        "implementation": "The feature is unfinished and the next implementation step is clearly known.",
        "repository": "The local working tree is clean and there are no unexplained changes.",
        "analysis": "The current project analysis is fresh.",
    }),
    ("resume-2", "resume", {
        "tests": "There are no failing tests.",
        "implementation": "Work stopped halfway through a clearly defined task and the exact next code change is known.",
        "repository": "All current local changes are expected and understood.",
        "analysis": "The current analysis accurately represents the project.",
    }),
    ("resume-3", "resume", {
        "tests": "The existing tests are green.",
        "implementation": "The developer can immediately continue the unfinished implementation from the known next step.",
        "repository": "There are no suspicious or unexplained local changes.",
        "analysis": "No reanalysis is necessary.",
    }),
    ("resume-4", "resume", {
        "tests": "Tests are passing and do not require investigation.",
        "implementation": "The active task is unfinished and has a concrete next action ready to execute.",
        "repository": "The local working-tree state is understood.",
        "analysis": "The project analysis is recent and valid.",
    }),
]


@dataclass(frozen=True)
class Metrics:
    threshold: float
    tp: int
    fp: int
    fn: int
    tn: int
    accuracy: float
    balanced_accuracy: float
    precision: float
    recall: float
    f1: float


def call_laya(state: dict) -> dict[str, float]:
    payload = {"provider": PROVIDER, "state": state, "questions": QUESTIONS}
    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        answers = json.load(response)["answers"]
    return {name: answers[name]["noul"] for name in QUESTIONS}


def metrics_at(values: list[tuple[float, bool]], threshold: float) -> Metrics:
    tp = fp = fn = tn = 0
    for value, expected in values:
        predicted = value >= threshold
        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1
        else:
            tn += 1

    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total
    tpr = tp / (tp + fn) if tp + fn else 0.0
    tnr = tn / (tn + fp) if tn + fp else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tpr
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Metrics(
        threshold=threshold,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        accuracy=accuracy,
        balanced_accuracy=(tpr + tnr) / 2,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def best_threshold(values: list[tuple[float, bool]]) -> Metrics:
    unique = sorted({value for value, _ in values})
    candidates = [0.0, 1.0001]
    candidates.extend(unique)
    candidates.extend((a + b) / 2 for a, b in zip(unique, unique[1:]))
    scored = [metrics_at(values, threshold) for threshold in candidates]
    return max(
        scored,
        key=lambda m: (m.balanced_accuracy, m.f1, m.accuracy, -m.threshold),
    )


def main() -> None:
    print(f"Binary signal evaluation: provider={PROVIDER} api={BASE_URL}")
    print("=" * 118)

    results = []
    for case_id, expected_action, state in CASES:
        signals = call_laya(state)
        expected_signal = ACTION_TO_SIGNAL[expected_action]
        results.append((case_id, expected_action, expected_signal, signals))
        print(
            f"{case_id:<14} expected={expected_action:<10} "
            f"test={signals['tests_blocking']:.4f} "
            f"inspect={signals['changes_need_inspection']:.4f} "
            f"stale={signals['analysis_stale']:.4f} "
            f"resume={signals['ready_to_resume']:.4f}"
        )

    print("\nBest independent threshold per signal")
    print("=" * 118)
    print(
        f"{'SIGNAL':<28}{'THRESH':>9}{'BAL ACC':>10}{'ACC':>9}"
        f"{'PREC':>9}{'RECALL':>9}{'F1':>9}{'TP':>5}{'FP':>5}{'FN':>5}{'TN':>5}"
    )
    print("-" * 118)

    best = {}
    for signal in QUESTIONS:
        values = [
            (signals[signal], expected_signal == signal)
            for _, _, expected_signal, signals in results
        ]
        metric = best_threshold(values)
        best[signal] = metric
        print(
            f"{signal:<28}{metric.threshold:>9.4f}{metric.balanced_accuracy:>10.1%}"
            f"{metric.accuracy:>9.1%}{metric.precision:>9.1%}{metric.recall:>9.1%}"
            f"{metric.f1:>9.1%}{metric.tp:>5}{metric.fp:>5}{metric.fn:>5}{metric.tn:>5}"
        )

    print("\nErrors at each signal's best threshold")
    print("=" * 118)
    any_error = False
    for signal, metric in best.items():
        errors = []
        for case_id, _, expected_signal, signals in results:
            expected = expected_signal == signal
            predicted = signals[signal] >= metric.threshold
            if expected != predicted:
                errors.append((case_id, signals[signal], expected, predicted))
        if not errors:
            print(f"{signal}: none")
            continue
        any_error = True
        print(f"{signal} @ {metric.threshold:.4f}")
        for case_id, value, expected, predicted in errors:
            print(
                f"  {case_id:<14} value={value:.4f} "
                f"expected={str(expected):<5} predicted={str(predicted):<5}"
            )

    if not any_error:
        print("none")

    print("\nPositive vs negative averages")
    print("=" * 118)
    for signal in QUESTIONS:
        positives = [
            signals[signal]
            for _, _, expected_signal, signals in results
            if expected_signal == signal
        ]
        negatives = [
            signals[signal]
            for _, _, expected_signal, signals in results
            if expected_signal != signal
        ]
        pos_avg = sum(positives) / len(positives)
        neg_avg = sum(negatives) / len(negatives)
        print(
            f"{signal:<28} positive={pos_avg:.4f} "
            f"negative={neg_avg:.4f} delta={pos_avg - neg_avg:+.4f}"
        )


if __name__ == "__main__":
    main()

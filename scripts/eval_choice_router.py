from __future__ import annotations

import json
import os
import urllib.request


BASE_URL = os.getenv("DECISION_API_URL", "http://127.0.0.1:8787")
PROVIDER = os.getenv("DECISION_PROVIDER", "laya")
URL = f"{BASE_URL}/v1/decide"

CRITERIA = {
    "resume": "Continue unfinished implementation work",
    "inspect": "Inspect unexplained repository changes",
    "reanalyze": "Refresh the stale project analysis",
    "test": "Investigate and fix failing tests",
}

CASES = [
    ("test-1", "test", {
        "tests": "47 tests are failing and must be fixed before the work can proceed.",
        "implementation": "The feature implementation itself is complete.",
        "repository": "There are no unexplained working tree changes to inspect.",
        "analysis": "The current project analysis is fresh.",
    }),
    ("test-2", "test", {
        "tests": "The build is blocked by multiple failing integration tests.",
        "implementation": "The intended code changes are already implemented.",
        "repository": "All repository changes are understood.",
        "analysis": "The current analysis accurately represents the repository.",
    }),
    ("test-3", "test", {
        "tests": "A regression test that previously passed is now failing after the latest implementation.",
        "implementation": "The implementation is complete enough to validate.",
        "repository": "There are no unknown working-tree changes.",
        "analysis": "No project reanalysis is currently necessary.",
    }),
    ("test-4", "test", {
        "tests": "Tests fail consistently and the failure prevents release.",
        "implementation": "No additional feature implementation is currently needed.",
        "repository": "The current changes are fully understood.",
        "analysis": "The analysis is recent and valid.",
    }),
    ("inspect-1", "inspect", {
        "tests": "All tests are passing.",
        "implementation": "There is no unfinished implementation step to resume.",
        "repository": "Several uncommitted files appeared and their purpose is unknown.",
        "analysis": "The current project analysis is fresh.",
    }),
    ("inspect-2", "inspect", {
        "tests": "Tests are currently passing.",
        "implementation": "No immediate implementation task is pending.",
        "repository": "The working tree contains unexpected modifications that were not part of the current task.",
        "analysis": "The current analysis is still valid.",
    }),
    ("inspect-3", "inspect", {
        "tests": "There are no known test failures.",
        "implementation": "There is no clear implementation step until the repository state is understood.",
        "repository": "Several generated and source files changed unexpectedly after returning to the project.",
        "analysis": "The analysis itself is recent.",
    }),
    ("inspect-4", "inspect", {
        "tests": "Tests are green.",
        "implementation": "The previous task appears complete.",
        "repository": "There are unexplained local changes and it is unclear whether they are intentional.",
        "analysis": "The project analysis is not stale.",
    }),
    ("reanalyze-1", "reanalyze", {
        "tests": "All tests pass.",
        "implementation": "There is no unfinished implementation to continue.",
        "repository": "There are no unexplained repository changes.",
        "analysis": "The existing project analysis is invalid because it predates major architectural changes.",
    }),
    ("reanalyze-2", "reanalyze", {
        "tests": "There are no failing tests requiring attention.",
        "implementation": "There is no immediate implementation step.",
        "repository": "The current repository state is understood.",
        "analysis": "The stored analysis was created three days ago and many important source files have changed since then.",
    }),
    ("reanalyze-3", "reanalyze", {
        "tests": "Tests are passing.",
        "implementation": "Continuing implementation safely requires an accurate understanding of the new architecture.",
        "repository": "A large refactor has changed project structure substantially.",
        "analysis": "The current analysis describes the repository before the refactor and is no longer trustworthy.",
    }),
    ("reanalyze-4", "reanalyze", {
        "tests": "There are no blocking test failures.",
        "implementation": "No next implementation step should be chosen from the old project understanding.",
        "repository": "The project has changed substantially since the last observation.",
        "analysis": "A fresh project analysis is required before work can continue safely.",
    }),
    ("resume-1", "resume", {
        "tests": "All tests are passing.",
        "implementation": "The feature is unfinished and the next implementation step is clearly known.",
        "repository": "The repository is clean and there are no unexplained changes.",
        "analysis": "The current project analysis is fresh.",
    }),
    ("resume-2", "resume", {
        "tests": "There are no failing tests.",
        "implementation": "Work stopped halfway through a clearly defined task and the exact next code change is known.",
        "repository": "All current repository changes are expected.",
        "analysis": "The current analysis accurately represents the project.",
    }),
    ("resume-3", "resume", {
        "tests": "The existing tests are green.",
        "implementation": "The developer can immediately continue the unfinished implementation from the known next step.",
        "repository": "There are no suspicious or unexplained changes.",
        "analysis": "No reanalysis is necessary.",
    }),
    ("resume-4", "resume", {
        "tests": "Tests are passing and do not require investigation.",
        "implementation": "The active task is unfinished and has a concrete next action ready to execute.",
        "repository": "The working tree state is understood.",
        "analysis": "The project analysis is recent and valid.",
    }),
]


def call_laya(state: dict) -> dict:
    payload = {
        "provider": PROVIDER,
        "state": state,
        "questions": {
            "next_action": {
                "type": "choice",
                "instructions": "Choose the single next action justified by the current state.",
                "criteria": CRITERIA,
            }
        },
    }
    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)["answers"]["next_action"]


def main() -> None:
    results = []
    print(f"Choice routing evaluation: provider={PROVIDER} api={BASE_URL}")
    print("=" * 92)
    print(
        f"{'CASE':<14}{'EXPECTED':<12}{'ACTUAL':<12}"
        f"{'TOP':>8}{'2ND':>8}{'MARGIN':>10}{'OK':>6}"
    )
    print("-" * 92)

    for case_id, expected, state in CASES:
        answer = call_laya(state)
        probabilities = answer["probabilities"]
        ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        actual = ordered[0][0]
        top = ordered[0][1]
        second = ordered[1][1]
        margin = top - second
        correct = actual == expected
        results.append((case_id, expected, actual, margin, probabilities, correct))
        print(
            f"{case_id:<14}{expected:<12}{actual:<12}"
            f"{top:>8.4f}{second:>8.4f}{margin:>10.4f}"
            f"{'✓' if correct else '✗':>6}"
        )

    correct = sum(item[5] for item in results)
    correct_margins = [item[3] for item in results if item[5]]
    print("=" * 92)
    print(f"Top-1 accuracy : {correct}/{len(results)} = {correct / len(results):.1%}")
    print(f"Avg correct margin : {sum(correct_margins) / len(correct_margins):.4f}")

    print("\nAccuracy by expected action")
    print("-" * 40)
    for action in CRITERIA:
        subset = [item for item in results if item[1] == action]
        hits = sum(item[5] for item in subset)
        avg_margin = sum(item[3] for item in subset) / len(subset)
        print(
            f"{action:<10} {hits}/{len(subset)} ({hits / len(subset):.0%}), "
            f"avg margin={avg_margin:.4f}"
        )

    print("\nWrong cases")
    print("-" * 40)
    wrong = [item for item in results if not item[5]]
    if not wrong:
        print("none")
    else:
        for case_id, expected, actual, margin, probabilities, _ in wrong:
            print(f"\n{case_id}: expected={expected}, actual={actual}, margin={margin:.4f}")
            print(json.dumps(probabilities, indent=2))


if __name__ == "__main__":
    main()

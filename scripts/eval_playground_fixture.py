from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from statistics import mean


BASE_URL = os.getenv("LAYA_API_URL", "http://127.0.0.1:8787")


def post(payload: dict) -> dict:
    request = urllib.request.Request(
        f"{BASE_URL}/v1/decide",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def compact_question(question: dict, case_key: str) -> dict:
    result = dict(question)
    prefix = f"Consider only state.{case_key}. "
    instructions = result.get("instructions", "")
    if instructions.startswith(prefix):
        result["instructions"] = instructions[len(prefix) :]
    if result.get("type") == "noul":
        result.pop("criteria", None)
    return result


def evaluate_noul(rows: list[tuple[dict, dict]]) -> None:
    strict = [(answer["noul"], 1.0 if spec["expected"] else 0.0) for answer, spec in rows if spec.get("use_for_accuracy")]
    positives = [p for p, expected in strict if expected == 1.0]
    negatives = [p for p, expected in strict if expected == 0.0]
    brier = mean((p - expected) ** 2 for p, expected in strict)
    accuracy = mean((p >= 0.5) == bool(expected) for p, expected in strict)

    print(f"naive 0.5 accuracy : {accuracy:.1%}")
    print(f"Brier score        : {brier:.4f}")
    print(f"positive mean      : {mean(positives):.4f}")
    print(f"negative mean      : {mean(negatives):.4f}")
    print(f"separation         : {mean(positives) - mean(negatives):+.4f}")


def evaluate_score(rows: list[tuple[dict, dict]]) -> None:
    strict = [(answer, spec) for answer, spec in rows if spec.get("use_for_accuracy")]
    top_hits = 0
    errors = []
    for answer, spec in strict:
        probabilities = answer.get("probabilities", {})
        if probabilities:
            predicted = int(max(probabilities, key=probabilities.get))
            top_hits += predicted == spec["expected_index"]
        errors.append(abs(float(answer["score"]) - spec["expected_index"]))

    print(f"top-level accuracy : {top_hits / len(strict):.1%}")
    print(f"score MAE          : {mean(errors):.4f}")


def evaluate_choice(rows: list[tuple[dict, dict]]) -> None:
    strict = [(answer, spec) for answer, spec in rows if spec.get("use_for_accuracy")]
    accuracy = mean(answer["choice"] == spec["expected"] for answer, spec in strict)
    print(f"strict accuracy    : {accuracy:.1%} ({sum(answer['choice'] == spec['expected'] for answer, spec in strict)}/{len(strict)})")

    groups: dict[str, list[str]] = {}
    for answer, spec in strict:
        groups.setdefault(spec["paraphrase_group"], []).append(answer["choice"])
    print("paraphrase groups  :")
    for group, choices in groups.items():
        consistent = len(set(choices)) == 1
        print(f"  {group:<10} {choices} {'consistent' if consistent else 'changed'}")

    ambiguous = [(answer, spec) for answer, spec in rows if not spec.get("use_for_accuracy")]
    if ambiguous:
        print("ambiguous cases    :")
        for answer, spec in ambiguous:
            probabilities = answer.get("probabilities", {})
            ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
            top = ", ".join(f"{name}={value:.3f}" for name, value in ordered[:2])
            print(f"  {spec['case']}: choice={answer['choice']} {top}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/eval_playground_fixture.py <fixture-directory>")

    fixture_dir = Path(sys.argv[1])
    state = json.loads((fixture_dir / "state.json").read_text())
    questions = json.loads((fixture_dir / "questions.json").read_text())
    expected = json.loads((fixture_dir / "expected.json").read_text())
    primitive = expected["primitive"]

    print(f"Fixture: {fixture_dir}")
    print(f"Laya API: {BASE_URL}")
    print(f"Primitive: {primitive}")
    print("=" * 88)

    rows: list[tuple[dict, dict]] = []
    for question_key, spec in expected["cases"].items():
        case_key = spec["case"]
        question = compact_question(questions[question_key], case_key)
        response = post({"state": state[case_key], "questions": {question_key: question}})
        answer = response["answers"][question_key]
        rows.append((answer, spec))

        if primitive == "noul":
            print(f"{case_key:<10} expected={str(spec['expected']):<5} noul={answer['noul']:.4f}")
        elif primitive == "score":
            print(
                f"{case_key:<10} expected={spec['expected_level']:<8} "
                f"score={answer['score']:.4f} probabilities={json.dumps(answer.get('probabilities', {}))}"
            )
        else:
            expected_label = spec.get("expected", f"preferred={spec.get('preferred')}")
            print(
                f"{case_key:<10} expected={expected_label:<20} actual={answer['choice']:<10} "
                f"probabilities={json.dumps(answer.get('probabilities', {}))}"
            )

    print("=" * 88)
    if primitive == "noul":
        evaluate_noul(rows)
    elif primitive == "score":
        evaluate_score(rows)
    elif primitive == "choice":
        evaluate_choice(rows)
    else:
        raise SystemExit(f"unsupported primitive: {primitive}")


if __name__ == "__main__":
    main()

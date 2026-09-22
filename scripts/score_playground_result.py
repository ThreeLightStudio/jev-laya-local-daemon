from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean


def load_fixture(path: Path) -> tuple[dict, dict]:
    expected = json.loads((path / "expected.json").read_text())
    result = json.loads((path / "result.json").read_text())
    return expected, result


def best_binary_threshold(values: list[tuple[float, bool]]) -> tuple[float, float]:
    unique = sorted({value for value, _ in values})
    candidates = [0.0, 1.0001, *unique]
    candidates.extend((a + b) / 2 for a, b in zip(unique, unique[1:]))

    best_threshold = 0.5
    best_accuracy = -1.0
    for threshold in candidates:
        accuracy = mean((value >= threshold) == expected for value, expected in values)
        if accuracy > best_accuracy or (accuracy == best_accuracy and abs(threshold - 0.5) < abs(best_threshold - 0.5)):
            best_threshold = threshold
            best_accuracy = accuracy
    return best_threshold, best_accuracy


def score_noul(expected: dict, result: dict) -> None:
    values = []
    for question_id, spec in expected["cases"].items():
        value = float(result["answers"][question_id]["noul"])
        values.append((value, bool(spec["expected"])))

    positives = [value for value, label in values if label]
    negatives = [value for value, label in values if not label]
    accuracy = mean((value >= 0.5) == label for value, label in values)
    brier = mean((value - float(label)) ** 2 for value, label in values)
    threshold, fitted_accuracy = best_binary_threshold(values)

    print(f"0.5 threshold accuracy : {accuracy:.1%}")
    print(f"Brier score            : {brier:.5f}")
    print(f"positive mean          : {mean(positives):.4f}")
    print(f"negative mean          : {mean(negatives):.4f}")
    print(f"separation             : {mean(positives) - mean(negatives):+.4f}")
    print(f"best in-sample cutoff  : {threshold:.5f} -> {fitted_accuracy:.1%}")


def score_score(expected: dict, result: dict) -> None:
    hits = 0
    errors = []
    ties = 0
    for question_id, spec in expected["cases"].items():
        answer = result["answers"][question_id]
        probabilities = {int(key): float(value) for key, value in answer["probabilities"].items()}
        top_probability = max(probabilities.values())
        top_levels = {key for key, value in probabilities.items() if value == top_probability}
        hits += spec["expected_index"] in top_levels
        ties += len(top_levels) > 1
        errors.append(abs(float(answer["score"]) - spec["expected_index"]))

    total = len(expected["cases"])
    print(f"expected-at-top accuracy: {hits}/{total} = {hits / total:.1%}")
    print(f"score MAE               : {mean(errors):.4f}")
    print(f"top-probability ties    : {ties}")


def score_choice(expected: dict, result: dict) -> None:
    strict = []
    groups: dict[str, list[str]] = {}
    ambiguous = []

    for question_id, spec in expected["cases"].items():
        answer = result["answers"][question_id]
        if spec.get("use_for_accuracy"):
            strict.append(answer["choice"] == spec["expected"])
            groups.setdefault(spec["paraphrase_group"], []).append(answer["choice"])
        else:
            probabilities = answer["probabilities"]
            ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
            ambiguous.append((spec, answer, ordered))

    print(f"strict accuracy         : {sum(strict)}/{len(strict)} = {mean(strict):.1%}")
    consistent = sum(len(set(choices)) == 1 for choices in groups.values())
    print(f"paraphrase consistency : {consistent}/{len(groups)} groups")
    for group, choices in groups.items():
        print(f"  {group:<10} {choices}")

    print("ambiguous cases         :")
    for spec, answer, ordered in ambiguous:
        preferred = spec["preferred"]
        top_two = ", ".join(f"{name}={value:.3f}" for name, value in ordered[:2])
        print(
            f"  {spec['case']}: preferred={preferred:<9} choice={answer['choice']:<9} "
            f"confidence={answer.get('confidence', 0):.3f} {top_two}"
        )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 scripts/score_playground_result.py <fixture-directory>")

    fixture_dir = Path(sys.argv[1])
    expected, result = load_fixture(fixture_dir)

    print(f"Fixture: {fixture_dir}")
    print(f"Model: {result.get('model', 'unknown')}")
    if "evaluation_time_ms" in result:
        print(f"Evaluation time: {result['evaluation_time_ms']:.2f} ms")
    print("=" * 72)

    primitive = expected["primitive"]
    if primitive == "noul":
        score_noul(expected, result)
    elif primitive == "score":
        score_score(expected, result)
    elif primitive == "choice":
        score_choice(expected, result)
    else:
        raise SystemExit(f"unsupported primitive: {primitive}")


if __name__ == "__main__":
    main()

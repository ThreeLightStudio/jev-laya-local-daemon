# Jev Playground comparison fixtures

These fixtures are designed for copy/paste testing in the TypeSafe Jev Playground and for replaying the same cases through `jev-laya-local-daemon`.

## How to run a round in Jev Playground

1. Open one round directory.
2. Copy the entire contents of `state.json` into the Playground state field.
3. Copy the entire contents of `questions.json` into the Playground questions field.
4. Run the request.
5. Save the full result JSON plus the reported server/network timing.
6. Do **not** paste `expected.json` into the Playground. It is only for scoring after the run.

The current checked-in `result.json` files were produced with `jev-1.13.0` on September 23, 2026.

## Rounds

- `round-a-noul`: 16 clear, balanced human-review decisions (8 true / 8 false). Use probabilities to compare separation and calibration, not only a 0.5 threshold.
- `round-b-score`: 16 urgency cases, balanced across low / medium / high / critical. Compare top level and score MAE.
- `round-c-robustness`: 12 strict Choice cases arranged as paraphrase groups with rotated option order, plus 4 deliberately ambiguous cases. The last four are excluded from accuracy; inspect their probability spread instead.

The expected files are kept separate so the model input never contains the answer key.

## Laya replay

With `jev-laya-local-daemon` already running:

```bash
DECISION_PROVIDER=laya python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-a-noul
DECISION_PROVIDER=laya python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-b-score
DECISION_PROVIDER=laya python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-c-robustness
```

Set `DECISION_API_URL` when the daemon is not on `http://127.0.0.1:8787`.

When `JEV_API_KEY` is configured on the daemon, replay the exact same compact-state requests through Jev by changing only the provider:

```bash
DECISION_PROVIDER=jev python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-a-noul
DECISION_PROVIDER=jev python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-b-score
DECISION_PROVIDER=jev python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-c-robustness
```

## Score saved Jev results

```bash
python scripts/score_playground_result.py benchmarks/jev-playground/round-a-noul
python scripts/score_playground_result.py benchmarks/jev-playground/round-b-score
python scripts/score_playground_result.py benchmarks/jev-playground/round-c-robustness
```

Current Jev 1.13.0 snapshot:

| Round | Result |
| --- | --- |
| Noul | 16/16 at a 0.5 cutoff, Brier 0.00695, positive/negative mean separation 0.845 |
| Score | expected level has top probability in 14/16 cases, score MAE 0.1356 |
| Robustness | 12/12 strict Choice cases, 4/4 paraphrase groups consistent |
| Ambiguity diagnostic | preferred action selected in all 4, but confidence remained 0.66–0.99 |

The four ambiguity cases are intentionally excluded from accuracy because the preferred labels are subjective. They exist to inspect probability spread and uncertainty behavior.

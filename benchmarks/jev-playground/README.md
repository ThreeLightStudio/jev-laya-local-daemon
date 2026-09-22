# Jev Playground comparison fixtures

These fixtures are designed for copy/paste testing in the TypeSafe Jev Playground and for replaying the same cases through `laya-local-api`.

## How to run a round in Jev Playground

1. Open one round directory.
2. Copy the entire contents of `state.json` into the Playground state field.
3. Copy the entire contents of `questions.json` into the Playground questions field.
4. Run the request.
5. Save the full result JSON plus the reported server/network timing.
6. Do **not** paste `expected.json` into the Playground. It is only for scoring after the run.

## Rounds

- `round-a-noul`: 16 clear, balanced human-review decisions (8 true / 8 false). Use probabilities to compare separation and calibration, not only a 0.5 threshold.
- `round-b-score`: 16 urgency cases, balanced across low / medium / high / critical. Compare top level and score MAE.
- `round-c-robustness`: 12 strict Choice cases arranged as paraphrase groups with rotated option order, plus 4 deliberately ambiguous cases. The last four are excluded from accuracy; inspect their probability spread instead.

The expected files are kept separate so the model input never contains the answer key.

## Laya replay

With `laya-local-api` already running:

```bash
python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-a-noul
python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-b-score
python scripts/eval_playground_fixture.py benchmarks/jev-playground/round-c-robustness
```

Set `LAYA_API_URL` when the daemon is not on `http://127.0.0.1:8787`.

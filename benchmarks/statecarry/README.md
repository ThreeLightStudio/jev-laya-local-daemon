# StateCarry decision benchmark

This benchmark uses fully synthetic project states inspired by the kinds of resume decisions StateCarry needs to make.

It does not read a StateCarry checkout while the benchmark is running, and it does not store local repository paths, user names, home directories, source file names, session identifiers, API keys, or environment values in fixtures or results.

The hand-written source set is scenarios.json. The runner expands those scenarios into deterministic variants covering:

- choice size and option-order changes
- flat, text, nested, and reordered state representations
- irrelevant state noise at multiple sizes
- Korean state descriptions where a synthetic translation is provided
- independent Noul signals
- ordinal intervention scoring
- repeat stability
- same-state multi-question batching
- identical single-request vs batch-request A/B comparisons
- cross-case multiplexing in one shared state object
- temporal, negation, contradiction, and missing-information challenge cases
- provider disagreement and confidence calibration

Run both providers against an already running daemon:

    python3 scripts/run_statecarry_benchmark.py

Use a different local daemon port with:

    DECISION_API_URL=http://127.0.0.1:8790 python3 scripts/run_statecarry_benchmark.py

The runner writes canonical machine-readable results to benchmarks/statecarry/results/latest.json and a compact generated summary to benchmarks/statecarry/results/summary.json.

The benchmark fails before writing results if serialized output contains common absolute-path markers or the current home/project directory. This is a final guard in addition to using synthetic fixtures only.

The current interpreted result is documented in docs/statecarry-benchmark.md.

The current StateCarry recommendation is to keep UI language separate from model input language. For Laya, build the small semantic decision state in English with deterministic templates, even when the user-facing UI is Korean.

# Laya experiment: from a local decision model to a reusable localhost daemon

This document records the full path from discovering Laya to building `laya-local-api`, evaluating how Laya behaves on real decision tasks, and deciding how it should be used in practice.

## 1. How I discovered Laya

The starting point was a mention of Laya around Atomic Chat. My first question was simple: **is this effectively a local Jev-like model?**

I was already interested in decision models that play a different role from large language models. Instead of generating long answers, these models take an existing state and make a small typed decision such as `choice`, `score`, or `noul`.

That is especially interesting for local applications and agent systems. Many internal decisions do not need a large model. A fast local model might be enough for routing, gating, prioritization, or deciding whether another expensive step is justified.

Rather than installing several related models or building a model hierarchy immediately, I decided to try one model deeply first. I wanted to answer a few practical questions:

- How large is it on disk?
- How much memory does it use?
- Is the inference fast enough to keep resident locally?
- Can it make useful decisions on realistic developer-tool states?
- What kind of input representation works best?

Laya was distributed as a Python package, but it was not exposed as a reusable local HTTP service. That meant every TypeScript or Python project would otherwise need to manage its own Python runtime, model loading, and process lifecycle.

That led to this design:

```text
TypeScript / Python / other apps
             ↓ HTTP
      http://127.0.0.1:<port>
             ↓
          laya-local-api
             ↓
            Laya
             ↓
       local inference
```

The core goal became:

> Load Laya once, keep it resident in memory, and let multiple local projects reuse it through HTTP.

That is how `laya-local-api` started.

## 2. Verifying the real Laya API first

Before implementing the daemon, I inspected the currently installed official `laya` package instead of guessing its API.

The version used for this project is:

```text
laya 0.3.5
```

The checkpoint used for typed decisions is:

```text
model:     convaiinnovations/laya
subfolder: typed-decisions
```

The relevant package API is:

```python
laya.load(
    "convaiinnovations/laya",
    subfolder="typed-decisions",
)

agent.predict(state, questions)
```

`predict()` already returns rich native results:

- `noul`: a value corresponding to `P(true)`
- `choice`: the selected option plus probabilities for every option
- `score`: the expected score plus the full score distribution
- confidence values
- action probability
- token usage

Because the native output already contains what callers need, `laya-local-api` does not reinterpret those values or impose its own thresholds. The HTTP layer is intentionally thin: validate input, manage the model lifecycle, call Laya, and return the native result.

## 3. Why a daemon is useful

A Laya checkpoint is not something that should be reloaded for every small request.

The intended lifecycle is:

```text
process start
    ↓
load Laya once
    ↓
ready
    ↓
request
request
request
...
```

The FastAPI application therefore owns one model runtime. Loading happens once during application startup in a background loader thread. While the model is still loading, `/health` remains available and `/ready` returns HTTP 503. Once the model is usable, `/ready` changes to HTTP 200.

Other projects then only need a normal HTTP request:

```ts
await fetch("http://127.0.0.1:8790/v1/decide", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ state, questions }),
});
```

The caller does not need to manage PyTorch, checkpoint loading, MPS, or a Python process.

## 4. Real runtime environment

The primary test environment was macOS on Apple Silicon.

Laya 0.3.5 automatically chooses MPS when it is available. On the test machine, `torch.backends.mps.is_available()` returned `True`.

The first checkpoint download reported approximately 847 MB from Hugging Face. A later startup with a warm cache reported `0.00B` of additional download.

Observed process RSS after loading was roughly 1.0–1.2 GiB.

The `laya-local-api` project uses `8787` as its default daemon port. This is a project-level choice, not an upstream Laya recommendation or protocol requirement; upstream Laya is a Python package and does not assign an HTTP port for this daemon. During development, `8787` was already occupied by a Headroom proxy on `127.0.0.1:8787`, so the smoke tests and decision experiments used port `8790` instead.

That real collision is why the README now documents how to inspect a port with `lsof`, stop a known process, or launch `laya-local-api` on another loopback port.

## 5. Verifying the daemon itself

Before evaluating model quality, the daemon behavior had to be verified independently.

The implementation was tested for:

- `GET /health`
- `GET /ready`
- `POST /v1/decide`
  - `noul`
  - `choice`
  - `score`
- missing and invalid payloads
- unknown question types
- malformed JSON
- model loading failure
- inference failure
- reusing one loaded model across multiple requests
- graceful shutdown with Ctrl+C
- the `laya-local-api` CLI entry point
- the `python -m laya_local_api` entry point
- the default bind address being `127.0.0.1`

Unit and integration tests use a mockable model wrapper so they do not download or load the heavyweight checkpoint.

Final result:

```text
7 passed
```

Real-model smoke tests were also performed.

### Real `noul` response

```json
{
  "notify_user": {
    "type": "noul",
    "noul": 0.4011,
    "confidence": 0.5989,
    "action": {
      "act_probability": 1.0
    }
  }
}
```

### Real `choice` response

```json
{
  "next_action": {
    "type": "choice",
    "choice": "inspect",
    "probabilities": {
      "resume": 0.2589,
      "inspect": 0.2975,
      "reanalyze": 0.2602,
      "wait": 0.1834
    },
    "confidence": 0.0104
  }
}
```

### Real `score` response

```json
{
  "urgency": {
    "type": "score",
    "score": 2.1601,
    "legend": {
      "0": "ignore",
      "1": "normal",
      "2": "urgent",
      "3": "critical"
    },
    "probabilities": {
      "0": 0.0436,
      "1": 0.12,
      "2": 0.4692,
      "3": 0.3672
    },
    "confidence": 0.1965
  }
}
```

At that point the daemon goal was achieved. The more interesting question became:

> What kinds of decisions is Laya actually good at?

## 6. First decision experiment: raw state

The first experiments used states that looked like normal program telemetry from StateCarry.

For example:

```json
{
  "git_dirty": true,
  "source_changed": true,
  "last_analysis_age_minutes": 180,
  "last_analysis_git_sha_matches": false
}
```

The question was:

```text
Should the project analysis be refreshed before resuming work?
```

The result was:

```text
noul = 0.5260
```

That is effectively close to 50/50.

Changing only the age produced:

```text
5 minutes   → 0.5187
60 minutes  → 0.5206
240 minutes → 0.5326
```

The direction was sensible, but the movement was small.

This suggested an important limitation:

> Laya should not be expected to turn raw booleans and numbers into rich application meaning by itself.

## 7. Semantic state changed the behavior

The next experiment expressed the same underlying facts as short, explicit semantic statements.

### Analysis completed moments ago

```json
{
  "analysis": "The analysis was completed 30 seconds ago.",
  "source_changes_since_analysis": "none",
  "git_commit_matches_analysis": true,
  "project_state": "unchanged"
}
```

Result:

```text
reanalyze = 0.2376
```

### Large changes after an old analysis

```json
{
  "analysis": "The last analysis was completed three days ago.",
  "source_changes_since_analysis": "large architectural changes across many files",
  "git_commit_matches_analysis": false,
  "project_state": "substantially changed since the last analysis"
}
```

Result:

```text
reanalyze = 0.3414
```

The absolute value was still lower than expected, but the separation between the two cases became much clearer than with raw numeric telemetry.

That led to the second major conclusion:

> Laya responds better when observations are expressed as short, explicit semantic state rather than raw telemetry alone.

That semantic state does not need another LLM. A deterministic template is enough:

```ts
const state = {
  tests: testsFailing
    ? `${failedTests} tests are failing and should be investigated.`
    : "All tests are passing; there are no failing tests to investigate.",

  repository: hasUnknownChanges
    ? "There are unexplained repository changes that should be inspected."
    : "There are no unexplained repository changes to inspect.",

  analysis: analysisStale
    ? "The current analysis predates major changes and should be refreshed."
    : "The current project analysis is fresh and does not need to be refreshed.",
};
```

## 8. `choice` router experiment

The next experiment asked Laya to choose the next action for a StateCarry-like workflow.

The action space was intentionally small and fixed:

```text
resume
inspect
reanalyze
test
```

One obvious test case looked like this:

```text
47 tests are currently failing
feature implementation is complete
no unexplained working-tree changes
analysis is fresh
```

Laya returned:

```text
resume     22.21%
inspect    23.89%
reanalyze  18.83%
test       35.06%
```

It chose `test`, which was the expected action, although the probability separation was not large.

That led to a larger 16-case evaluation with four scenarios for each expected action.

### 16-case choice evaluation

Result:

```text
Top-1 accuracy: 14/16 = 87.5%
Average correct margin: ~0.110
```

Accuracy by expected action:

```text
resume     3/4 = 75%
inspect    3/4 = 75%
reanalyze  4/4 = 100%
test       4/4 = 100%
```

The two errors both drifted toward `reanalyze`:

```text
inspect-1
expected: inspect
actual:   reanalyze

resume-1
expected: resume
actual:   reanalyze
```

That may indicate a tendency to prefer reanalysis when the project state contains uncertainty.

### Margin was not a correctness guarantee

It was tempting to treat the gap between the top two probabilities as a confidence measure.

However, the incorrect `inspect-1` case had a margin of 0.1164, while the correct `resume-4` case had a margin of only 0.0182.

So:

> Top-1 margin can describe ambiguity, but it should not be treated as a guarantee that the decision is correct.

## 9. Decomposing the decision into multiple `noul` questions

A natural alternative for System 1-style decision models is to decompose one final action into several smaller binary judgments.

The same 16 cases were therefore evaluated with four questions:

```text
tests_blocking?
changes_need_inspection?
analysis_stale?
ready_to_resume?
```

The first attempt simply selected whichever `noul` value was largest.

Result:

```text
Top-signal accuracy: 11/16 = 68.8%
```

This was lower than the direct 4-way `choice` result.

But that comparison was conceptually flawed because these binary questions are not mutually exclusive.

For example, after a large refactor both of these can reasonably be true at once:

```text
analysis_stale = true
changes_need_inspection = true
```

Therefore independent `noul` values should not be compared as if they were probabilities from one shared categorical distribution.

## 10. Evaluating each `noul` as an independent classifier

The next experiment treated each question as its own binary classification problem.

The `changes_need_inspection` question was also narrowed to reduce semantic overlap.

Earlier wording:

```text
Are there unexplained repository changes that should be inspected?
```

Narrower wording:

```text
Are there local working-tree changes whose origin or purpose is unknown
and that should be inspected before continuing?
```

The 16 scenarios were then used to search for a best threshold for each signal.

Results:

| Signal | Best threshold | Balanced accuracy | Accuracy | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| `tests_blocking` | 0.3286 | 87.5% | 81.2% | 57.1% | 100.0% |
| `changes_need_inspection` | 0.3497 | 79.2% | 68.8% | 44.4% | 100.0% |
| `analysis_stale` | 0.3130 | 83.3% | 87.5% | 75.0% | 75.0% |
| `ready_to_resume` | 0.4102 | 91.7% | 87.5% | 66.7% | 100.0% |

Positive/negative average separation was:

```text
tests_blocking
positive = 0.4570
negative = 0.2993
delta    = +0.1577

changes_need_inspection
positive = 0.4518
negative = 0.3786
delta    = +0.0732

analysis_stale
positive = 0.3541
negative = 0.2492
delta    = +0.1049

ready_to_resume
positive = 0.4974
negative = 0.3471
delta    = +0.1503
```

The weakest signal was `changes_need_inspection`.

Even after narrowing the question to local unknown changes, it still produced relatively high values in some test-failure and large-refactor scenarios.

By comparison, `tests_blocking`, `analysis_stale`, and `ready_to_resume` showed more useful separation.

## 11. What the experiments suggest

### 11.1 Laya should not be asked to understand the whole project

Feeding raw repository telemetry and expecting the model to infer all hidden meaning produced weak separation.

For example:

```text
git_dirty=true
analysis_age_minutes=240
```

was less effective than an explicit semantic statement such as:

```text
The current analysis predates major architectural changes and is no longer trustworthy.
```

### 11.2 Laya behaves more like a small decision component

The useful pattern is closer to:

```text
complex project state
        ↓
deterministic semantic state builder
        ↓
       Laya
        ↓
small typed decision
```

Laya is better understood as a component for repeated small decisions than as a replacement for a large reasoning model.

### 11.3 `choice` was the most immediately practical primitive in this experiment

The 4-way router achieved 14/16 correct decisions on a small hand-built evaluation set.

That result should not be generalized as a benchmark, but it is encouraging for narrow action spaces such as:

```text
resume / inspect / reanalyze / test
```

### 11.4 `noul` values are per-question signals

Values such as:

```text
tests_blocking = 0.45
analysis_stale = 0.35
```

should not be interpreted as saying `test` is more likely than `reanalyze`.

Each question can have a different scale and calibration. Every signal needs its own evaluation set and threshold policy.

### 11.5 Deterministic facts should stay deterministic

If Git or StateCarry can directly determine that a local working-tree change is unknown, the application should keep that fact in code rather than asking Laya to rediscover it.

```ts
if (hasUnknownWorkingTreeChanges) {
  // deterministic fact
}
```

Laya is more useful after those facts have been observed, when the remaining decision is semantic or probabilistic.

## 12. Recommended integration pattern

For a project such as StateCarry, the most promising structure currently looks like this:

```text
1. Observe deterministic facts
   - git state
   - test state
   - known / unknown changes
   - analysis age and source changes
           ↓
2. Build semantic state
   - short deterministic text templates
           ↓
3. Ask Laya for a choice
   - resume
   - inspect
   - reanalyze
   - test
           ↓
4. Optionally collect independent noul signals
   - tests_blocking
   - analysis_stale
   - ready_to_resume
           ↓
5. Apply caller-owned policy or fallback
```

For example:

```text
choice → resume
ready_to_resume → 0.61

=> the categorical decision and the supporting signal agree
```

Or:

```text
choice → resume
ready_to_resume → 0.29

=> the signals are weakly inconsistent
=> use deterministic fallback or a more expensive decision path
```

Thresholds should be derived from product-specific evaluations rather than chosen arbitrarily.

## 13. Good and bad use cases

Based on the experiments so far, Laya appears well suited to narrow, repeated decision points.

### Good candidates

- choosing the next action from a small fixed set
- workflow routing such as retry / skip / inspect / escalate
- deciding whether a background event should be surfaced
- selecting analysis depth
- cheap pre-filtering
- gating a larger LLM call
- small decisions inside agent orchestration
- prioritizing actions from an already summarized state

### Less suitable candidates

- understanding an entire project from scratch
- generating long explanations
- inventing novel solutions
- complex multi-step reasoning
- deeply interpreting raw telemetry without semantic context
- treating one probability as a universal absolute confidence score

One additional failure mode became clear when comparing Laya with Jev: packing many unrelated states into one shared object and asking each question to inspect only one nested path is a poor fit for Laya. With one compact state per request, the 16-case `choice` router scored 14/16. With the same 16 cases multiplexed into one shared object in the style used for the Jev Playground test, Laya scored 4/16 and most answers collapsed toward `reanalyze`. Four smaller mixed batches showed the same 4/16 total result.

## 14. What `laya-local-api` adds

This project does not modify Laya itself.

Its value is operational: make Laya cheap and simple to reuse from local applications.

```text
model lifecycle
HTTP transport
localhost-only binding
input validation
health and readiness
one reusable process
```

Because the daemon owns those concerns, TypeScript, Electron, Node, and Python applications do not need to manage model loading or a PyTorch runtime directly.

## 15. Jev comparison snapshot

On September 23, 2026, I compared Laya and Jev across four product-shaped rounds: the original 16-case next-action router plus three additional 16-case fixtures for `noul`, `score`, and robustness/ambiguity.

Versions used:

```text
Laya package: 0.3.5
Laya checkpoint: convaiinnovations/laya / typed-decisions
Jev: 1.13.0
```

The four possible actions were identical in both tests:

```text
resume
inspect
reanalyze
test
```

Results:

| Model / input shape | Correct | Accuracy | Timing observed |
| --- | ---: | ---: | --- |
| Laya, one compact state per request | 14/16 | 87.5% | 35.3 ms/case average locally; most warm calls 31–33 ms |
| Jev 1.13.0, 16 questions in one Playground batch | 16/16 | 100% | 162.6 ms server evaluation; 449 ms network roundtrip to us-west |
| Laya, Jev-style multiplexed shared state | 4/16 | 25% | 3771.5 ms for the single 16-question request |

### Additional primitive and robustness rounds

| Round | Laya 0.3.5 | Jev 1.13.0 |
| --- | --- | --- |
| `noul` human escalation, 16 clear balanced cases | 10/16 at a 0.5 cutoff; Brier 0.1905; positive mean 0.4826 vs negative 0.3075 | 16/16 at a 0.5 cutoff; Brier 0.00695; positive mean 0.945 vs negative 0.100 |
| `score` urgency, 16 cases across four ordered levels | 8/16 expected level on top; score MAE 0.5404 | 14/16 expected level on top; score MAE 0.1356 |
| `choice` robustness, 12 strict paraphrase/order cases | 10/12; 2/4 paraphrase groups fully consistent | 12/12; 4/4 groups fully consistent |
| ambiguity diagnostic, four deliberately debatable cases | preferred action was not top-1 in 4/4; top probabilities were about 0.31–0.35 | preferred action was top-1 in 4/4, but confidence stayed 0.66–0.99 and was at least 0.97 in three cases |

The ambiguity labels are deliberately subjective and are not counted as accuracy. They exist to inspect whether the probability distribution becomes less decisive when more than one action is plausible.

For Laya `noul`, a fixed 0.5 threshold is also not the whole story. Fitting the threshold on this same 16-case fixture yields a best in-sample cutoff of about 0.463 and 14/16 accuracy. That fitted number is optimistic and should not be compared directly with a zero-shot cutoff, but it reinforces the practical requirement that Laya binary signals need product-specific calibration.

The speed numbers are not directly comparable. Laya ran locally on Apple Silicon with MPS, while Jev ran on TypeSafe infrastructure, and the successful Laya accuracy test used one compact state per request rather than one multiplexed batch.

The more useful behavioral result is the input-shape difference. Jev correctly followed instructions such as `Consider only state.case_07` across one large state object. Laya did not reliably isolate those independent nested states. This matches Laya's intended multi-question pattern more closely when multiple questions refer to the same state, rather than when one state object is being used as a container for many unrelated scenarios.

The typed-decisions checkpoint used here has `max_len: 1024`, which also makes very large shared states a poor fit. The four-case mixed test still showed the same collapse, however, so the issue was not explained by context length alone.

There is useful counter-evidence in Laya's own published typed-decisions benchmark. Upstream currently reports `laya-typed-decisions` at 0.766 accuracy and Jev 1.13.0 at 0.727 on its four synthetic workflows. My 16-case developer-tool experiment produced the opposite ordering. Those results are not contradictory: they use different tasks, data, and evaluation harnesses. The disagreement is a useful reminder that this page documents one product-shaped experiment rather than a general leaderboard.

### Maker's take

My current subjective conclusion is:

> Across these product-shaped tests, Jev is currently the stronger default for hosted typed decisions: it was more accurate on `choice`, much cleaner on `noul`, substantially better on `score`, and more robust to paraphrasing and option order. Laya remains interesting when decisions must stay local, avoid a network dependency, and run repeatedly over small controlled states — but I would preprocess the state aggressively, tune thresholds, and keep each decision narrow.

Jev's probability outputs still deserve separate calibration testing. In three of the four deliberately ambiguous cases it reported confidence of at least 0.97 even though the fixture was intentionally written so that another action remained plausible. High top-1 accuracy in this small sample should not be treated as evidence that those confidence values are calibrated probabilities.

This is a small product-oriented experiment, not a general model benchmark. Different domains, prompts, hardware, and future model versions can change the result.

## 16. Current conclusion

The original question was:

> Can a small local decision model be useful inside a real product?

The current answer is:

> Yes, potentially, as long as it is used as a small decision component rather than as a miniature general-purpose LLM.

When semantic state was provided, the 4-way `choice` router selected the expected action in 14 of 16 scenarios. Independent `noul` signals also showed useful separation when evaluated as their own binary classification problems.

The working rule is therefore:

```text
Code observes the raw facts.
Deterministic templates express their meaning.
Laya handles the small decision.
The caller owns the final policy.
```

Within that role, Laya looks like an interesting building block for local agents and developer tools.

## 17. Reproducing the experiments

Start the daemon:

```bash
LAYA_PORT=8790 laya-local-api
```

Run the basic smoke test:

```bash
LAYA_API_URL=http://127.0.0.1:8790 python scripts/smoke.py
```

Run the 16-case choice router evaluation:

```bash
LAYA_API_URL=http://127.0.0.1:8790 \
  python scripts/eval_choice_router.py
```

Run the independent binary-signal evaluation:

```bash
LAYA_API_URL=http://127.0.0.1:8790 \
  python scripts/eval_binary_signals.py
```

For installation, API usage, and port-collision handling, see the project [`README.md`](../README.md).

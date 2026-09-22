# StateCarry decision benchmark

This benchmark asks a practical question:

> If StateCarry gives a small decision model a clear description of the current project state, how reliably can it choose what should happen next?

[StateCarry](https://github.com/ThreeLightStudio/statecarry) is an open-source macOS app for returning to interrupted development work. It helps a developer understand where a project stands and choose what to do next, which makes its project-resume decisions a useful product-shaped test for Laya and Jev.

The run described here was completed on September 23, 2026 with:

- Laya 0.3.5 using the local typed-decisions checkpoint
- Jev through the TypeSafe hosted API using the jev-latest alias
- 20 hand-written synthetic StateCarry scenarios
- 377 generated test cases per provider
- 754 provider runs in total
- 0 request errors

The source scenarios are in [benchmarks/statecarry/scenarios.json](../benchmarks/statecarry/scenarios.json). The full machine-readable result is in [benchmarks/statecarry/results/latest.json](../benchmarks/statecarry/results/latest.json), and the compact summary is in [benchmarks/statecarry/results/summary.json](../benchmarks/statecarry/results/summary.json).

## Privacy

The benchmark does not copy a StateCarry checkout into the result set.

The scenarios are synthetic descriptions such as:

    {
      "work": "The current implementation task is unfinished and its next code change is known.",
      "tests": "All relevant tests are passing.",
      "working_tree": "Current local changes are expected and understood.",
      "analysis": "The project state was checked after the latest source changes."
    }

The runner does not save local repository paths, home directories, user names, source file names, session identifiers, environment values, or API keys.

Before writing a result file, it also checks the serialized output for common absolute-path markers and the current home/project directory. The run is rejected if one is found.

## What was tested

The 20 source scenarios cover situations such as:

- known unfinished work that can continue
- unexplained local changes
- a stale project understanding after a large change
- a result ready for review
- work waiting on a running check
- switching to independent work while another task is blocked
- a disconnected project
- several open work items with no current selection
- no confirmed direction
- a direction conflict
- a release problem
- a completion claim that needs review
- an old resume point after the project changed
- queued next work
- completed work with no next task selected

Each scenario is expanded into several controlled variants.

The Choice tests vary the number and order of actions, the shape of the state, irrelevant information, and language. All state-shape variants for the same scenario reuse the same eight Choice options. This keeps the option set fixed while the input representation changes.

The suite also tests:

- five independent Noul signals
- a five-level intervention Score
- repeated identical calls
- many questions about one shared state
- many independent states packed into one object
- Choice + Noul + Score in one request
- temporal wording
- negation
- older information versus current information
- overlapping action labels
- intentionally less clear cases

## Main result

| Test | Laya | Jev |
| --- | ---: | ---: |
| Choice accuracy | 40.0% | 96.4% |
| Same meaning, different state form stays on one answer | 10.0% | 95.0% |
| 10 targeted challenge cases | 3 / 10 | 10 / 10 |
| Score top-level accuracy | 50.0% | 70.0% |
| Score mean absolute error | 0.55 | 0.35 |
| Repeat stability | 100% | 100% |
| Request errors | 0 | 0 |
| Median request latency | 52.7 ms | 558.9 ms |
| 95th percentile latency | 296.5 ms | 721.0 ms |

The latency numbers are not a fair speed comparison. Laya ran locally on Apple Silicon while Jev used a hosted API over the network. The accuracy and behavior differences are more useful than the raw latency gap.

Across the 220 Choice and challenge cases that both providers answered:

| Outcome | Cases |
| --- | ---: |
| Both correct | 84 |
| Jev correct, Laya wrong | 128 |
| Laya correct, Jev wrong | 4 |
| Both wrong | 4 |

The providers returned different top choices in 134 of those 220 cases. Most of that disagreement came from cases where Jev matched the hand-written StateCarry expectation and Laya did not.

## Choice size matters a lot for Laya

The same StateCarry scenarios were tested with increasingly large action sets.

| Choice options | Laya | Jev |
| ---: | ---: | ---: |
| 2 | 75% | 95% |
| 4 | 50% | 100% |
| 8 | 40% | 95% |
| 15 | 10% | 90% |

Laya degrades quickly as the action list grows.

That suggests a narrow role for the local model: small decisions with a short option list are much more realistic than asking it to choose from the full StateCarry action vocabulary.

Jev remained strong as the option list grew. Its one 15-option miss in the core set chose review_plan instead of reanalyze after a branch change. Those two actions describe neighboring ideas: both say the saved project understanding should not be trusted as-is.

## State representation

The eight-option Choice set was kept fixed while only the state representation changed.

| State form | Laya | Jev |
| --- | ---: | ---: |
| Structured object | 40% | 95% |
| Same meaning as plain text | 60% | 100% |
| Nested object | 35% | 95% |
| Reversed field order | 35% | 100% |
| +8 unrelated fields | 35% | 95% |
| +32 unrelated fields | 35% | 95% |
| Korean state text | 10% | 100% |

The plain-text result is useful for Laya. It performed better when the project facts were already turned into one compact explanation instead of being left as a structured object.

For StateCarry, this suggests a simple language boundary: the UI can remain Korean or English, but model-facing semantic state for Laya should be generated in English. StateCarry already owns the underlying facts, so this does not require a translation model; deterministic English templates are enough.

The benchmark does not justify adding another Laya checkpoint only to handle Korean input. Keeping one decision model and normalizing its internal input language is simpler and matches the strongest observed Laya path in this run.

This matches the earlier observation from this project: small local decision models benefit when normal code gathers the facts first and a simple layer explains what those facts mean.

Jev was much less sensitive to these representation changes.

## Changing option order

With the same eight options in a different order:

- Laya: 40% → 45%
- Jev: 95% → 95%

There was no large aggregate order effect in this run.

Laya was still unstable across other meaning-preserving input changes, so this should not be read as general robustness. It only says that option order itself was not the main problem in this set.

## Repeated identical requests

Eight representative scenarios were each repeated three times.

Both providers returned the same top Choice on every repetition:

- Laya: 100% repeat consistency
- Jev: 100% repeat consistency

The main difference is therefore not random output between calls. It is which decision boundary each model learned.

## Same state, many questions

Four project states were tested with 1, 2, 4, 8, and 16 equivalent Choice questions in one request.

Jev kept 100% accuracy at every size.

Laya stayed at 25% accuracy at every size, but its answer was 100% consistent with its own one-question answer.

That distinction matters:

> Asking Laya more questions about the same small state did not make it worse in this test. It simply repeated the same decision it would already have made.

So same-state batching can still be reasonable for Laya when the underlying decision is one it handles well.

## Single requests versus one real batch

The earlier same-state test repeated equivalent Choice questions. To close the remaining question, a final A/B test used eight representative StateCarry states and seven genuinely different questions per state:

- one Choice question
- five Noul questions
- one Score question

For each state, the exact same seven questions were sent in two ways:

1. seven separate requests, one question per request
2. one request containing all seven questions

The state, question wording, criteria, and expected answers were identical between the two modes.

### Laya

| Metric | 7 separate requests | 1 batch request |
| --- | ---: | ---: |
| Choice accuracy | 37.5% | 37.5% |
| Noul accuracy at 0.5 | 77.5% | 77.5% |
| Score accuracy | 37.5% | 37.5% |
| Total latency across 8 states | 2,198.7 ms | 2,384.3 ms |
| Reported input tokens | 7,269 | 7,269 |

All 56 top-level decisions were identical between single and batch mode. The Noul values were also numerically identical, and the Score values were numerically identical.

So batching did not make Laya stronger. It also did not provide a measured latency or token advantage in this implementation. It reduced the number of localhost HTTP requests, but the batch run was slightly slower overall in this sample.

This changes the practical recommendation slightly:

> Use a Laya batch when several questions naturally share one small semantic state and reducing caller-side request count is convenient. Do not expect batching itself to improve decision quality or local inference speed.

### Jev

| Metric | 7 separate requests | 1 batch request |
| --- | ---: | ---: |
| Choice accuracy | 100% | 100% |
| Noul accuracy at 0.5 | 72.5% | 72.5% |
| Score accuracy | 62.5% | 62.5% |
| Total latency across 8 states | 32,685.6 ms | 4,695.6 ms |
| Reported input tokens | 23,677 | 7,783 |
| Reported output tokens | 1,694 | 1,510 |

All 56 top-level decisions were also identical for Jev. Its raw probability-like values moved slightly between modes: the mean absolute Noul change was 0.0158 and the mean absolute Score change was 0.0338.

For Jev, batching preserved the observed decision quality while reducing total sequential latency by about 6.96×. Reported input tokens fell by about 67%, and output tokens fell by about 11%.

This is the strongest batching result from the experiment:

> For several related decisions about one shared state, Jev batching is materially more efficient without an observed top-level quality loss in this test.

## Many unrelated states in one object

The harder batching test packs separate project states into one object:

    state.case_01
    state.case_02
    state.case_03
    ...

Each question then asks the provider to look only at its matching case.

| Independent cases in one state | Laya accuracy | Laya consistency with individual result | Jev accuracy |
| ---: | ---: | ---: | ---: |
| 2 | 0% | 100% | 100% |
| 4 | 25% | 50% | 100% |
| 8 | 0% | 25% | 100% |

This reproduces the earlier Laya failure mode in a cleaner automated test.

Laya should receive one small semantic state for one decision context. Packing unrelated cases into one large object and asking each question to isolate its own nested case is a poor fit.

Jev handled all three multiplexed sizes correctly in this run.

## Noul needs provider-specific thresholds

Noul returns a probability-like value rather than a final boolean. A caller must choose the cutoff.

Using 0.5 directly produced:

| Signal | Laya @ 0.5 | Jev @ 0.5 |
| --- | ---: | ---: |
| safe_to_continue | 75% | 100% |
| needs_reanalysis | 90% | 85% |
| needs_inspection | 80% | 60% |
| needs_review | 85% | 75% |
| must_wait | 90% | 75% |

The Jev result looks surprising until the thresholds are calibrated.

For needs_inspection:

- positive mean: 0.95
- negative mean: 0.458
- best cutoff in this synthetic set: 0.92
- balanced accuracy at that cutoff: 100%

For must_wait:

- positive mean: 0.95
- negative mean: 0.348
- best cutoff: 0.845
- balanced accuracy at that cutoff: 100%

So these Jev signals separated the positive and negative examples well, but 0.5 was the wrong operating point.

The same lesson applies to Laya. Its best synthetic thresholds also differed by signal.

The best in-sample cutoffs from this run were:

| Signal | Laya cutoff | Laya balanced accuracy | Jev cutoff | Jev balanced accuracy |
| --- | ---: | ---: | ---: | ---: |
| safe_to_continue | 0.391 | 75.0% | 0.530 | 100% |
| needs_reanalysis | 0.474 | 83.3% | 0.700 | 94.1% |
| needs_inspection | 0.514 | 72.2% | 0.920 | 100% |
| needs_review | 0.380 | 77.4% | 0.430 | 82.1% |
| must_wait | 0.504 | 94.7% | 0.845 | 100% |

The product should own the cutoff for every Noul use case and calibrate it from representative fixtures. A universal 0.5 threshold is not justified by this run.

These cutoffs were selected on the same synthetic cases used to report them. They describe this benchmark, not production thresholds.

## Choice confidence

Jev's Choice probabilities were strongly associated with correctness in this run.

For top choices with probability from 0.9 to 1.0:

- 150 cases
- 98.7% correct

Laya usually produced much flatter distributions. Most of its top probabilities fell between 0.2 and 0.4, where its observed accuracy was also low.

This suggests a useful future product policy for Jev: high-confidence actions may be eligible for automatic handling, while lower-confidence cases can fall back to a deterministic rule, another model, or user review.

That policy still needs a larger real product dataset before choosing production thresholds.

## Score

The five-level intervention score was harder than Choice for both providers.

| Metric | Laya | Jev |
| --- | ---: | ---: |
| Exact top level | 50% | 70% |
| Mean absolute level error | 0.55 | 0.35 |

The exact Jev Score result varied between benchmark runs. Most misses were near the hand-written level, but one waiting case selected level 3 instead of level 1 even though its continuous score was 1.69. That is another reason to treat Score as a soft signal rather than a hard policy value.

The Score labels are also more subjective than the main action labels. For example, deciding whether a ready result is low or medium attention is a product choice, not a universal fact.

For StateCarry, Score looks more useful as a soft ranking signal than as an exact policy value.

## Mixed questions in one request

Six states were sent with Choice, five Noul questions, and one Score question together.

| Question type | Laya | Jev |
| --- | ---: | ---: |
| Choice | 50.0% | 100% |
| Noul using 0.5 | 86.7% | 66.7% |
| Score | 33.3% | 83.3% |

Jev's lower mixed Noul number is consistent with the threshold issue above. It should not be interpreted as the model losing the ability to separate the signals.

## Where Jev still missed

Jev made eight hard Choice misses across the 220 scored Choice and challenge cases.

Six were variants of one scenario:

    No current work is selected.
    There is no confirmed active direction.

The expected action was define_direction, while Jev strongly preferred choose_work.

That is partly a useful benchmark result and partly a test-design warning. Those two actions overlap unless the state also makes it explicit that there is no unfinished work available to choose.

One of the two remaining misses was:

    expected: reanalyze
    actual: review_plan

after a branch switch invalidated an older saved understanding.

The other was a two-option stale-return-point case:

    expected: review_plan
    actual: choose_next_work

In that case the old resume point predated the current project state and had no explicit fresh match, so the benchmark expected the old plan to be re-checked before choosing further work.

This suggests that the next benchmark revision should make neighboring StateCarry action boundaries more explicit and keep a separate set for intentionally ambiguous cases.

## Where Laya struggled

Laya's main problem was not random output. It was the size and semantic overlap of the action vocabulary.

In the canonical eight-option set it handled reanalyze, choose_work, define_direction, review_release, wait, and some inspect/review-result cases, but missed all three continue scenarios and several specialized actions such as reconnect, review_completion, review_plan, start_work, and switch_work.

Its output distributions were usually flat, which is useful information: the model often looked uncertain when it was wrong.

The strongest practical Laya patterns from this run are:

- keep the choice list short
- prefer one compact semantic state
- plain explanatory text can work better than a larger structured object
- do not multiplex unrelated cases into one state
- treat Noul as a calibrated signal instead of a boolean

## What this means for StateCarry

For the current kind of project-resume decision:

1. Normal code should still gather deterministic facts first.
2. Model-facing semantic state for Laya should be generated in English regardless of the UI language.
3. Jev is a strong candidate for choosing among several StateCarry actions.
4. Laya is better suited to smaller local decisions, especially two-way choices or narrow signals.
5. Same-state multi-question requests are reasonable, but unrelated cases should remain separate for Laya.
6. Noul thresholds should be learned per signal from fixtures rather than fixed globally.
7. Close action labels should be simplified or given clearer criteria before model output is trusted automatically.
8. Confidence can be used as one input to an escalation policy, but the threshold should be validated on more product-shaped data.

A practical hybrid could look like:

    deterministic facts
          ↓
    small semantic state
          ↓
    simple deterministic rule when the answer is obvious
          ↓
    Jev for larger action routing
          ↓
    Laya for narrow local fallback decisions where network access is unavailable
          ↓
    user / larger model when the decision is still uncertain

This is a product hypothesis from the current synthetic benchmark. It is not yet a claim that this routing policy is optimal.

## Limits of this run

The benchmark is deliberately product-shaped, but it is still small.

- There are 20 hand-written source scenarios.
- All examples are synthetic.
- The labels reflect current StateCarry behavior and design intent.
- Some neighboring actions have semantic overlap.
- The Korean subset contains 10 translated states, not a full multilingual benchmark.
- The confidence and Noul calibration numbers are in-sample measurements.
- Latency depends on the local machine and current network/provider conditions.
- This run does not measure API cost.
- The results describe the tested model/API versions, not every future version.

The next useful step is to add anonymized product traces only after StateCarry has enough real repeated decisions to justify them.

## Reproduce the run

Start the daemon and wait for both providers to be available:

    curl http://127.0.0.1:8787/v1/providers

Then run:

    python3 scripts/run_statecarry_benchmark.py

The runner expands the synthetic source scenarios, runs both providers, collects raw responses, calculates summary metrics, compares provider disagreements, checks output for path leaks, and writes:

    benchmarks/statecarry/results/latest.json
    benchmarks/statecarry/results/summary.json

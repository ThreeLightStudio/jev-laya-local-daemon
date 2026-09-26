# jev-laya-local-daemon

[Project page →](https://threelightstudio.github.io/jev-laya-local-daemon/)

> **Status (September 2026):** [`typesafe/jev-router` is now available for free on OpenRouter](https://openrouter.ai/typesafe/jev-router). If you only need Jev-style model routing, calling OpenRouter directly is the simpler path and this daemon is no longer required. This project remains useful when you want typed decisions from the **local** Laya checkpoint, fully offline on your own machine.

`jev-laya-local-daemon` exposes one localhost API for typed decisions from either local Laya or hosted Jev.

```text
TypeScript / Python / other apps
             ↓ HTTP
      http://127.0.0.1:8787
             ↓
          jev-laya-local-daemon
          ↙       ↘
       Laya        Jev
       local       TypeSafe API
```

Callers use the same `state + questions` shape and select `"provider": "laya"` or `"provider": "jev"`. Laya runs entirely on the local machine. Jev requests are forwarded to TypeSafe using an API key read from the daemon environment; callers never send the key in request bodies.

The default Laya checkpoint is `convaiinnovations/laya` with the `typed-decisions` subfolder. The default Jev model alias is `jev-latest`.

> Do not expose this daemon directly to the public internet.

## Experiment notes

For the full background, evaluation process, results, and recommended usage patterns, see [Jev + Laya experiment: one localhost contract for typed decisions](docs/jev-laya-experiment.md).

For reproducible Jev Playground comparisons, see [`benchmarks/jev-playground/`](benchmarks/jev-playground/). Each round keeps `state.json`, `questions.json`, and the hidden-from-model `expected.json` answer key separate for easy copy/paste testing.

For the larger automated [StateCarry](https://github.com/ThreeLightStudio/statecarry) decision suite, see [StateCarry decision benchmark](docs/statecarry-benchmark.md). StateCarry is an open-source macOS app that helps developers return to interrupted work, understand the current project state, and choose what to do next. The benchmark expands 20 fully synthetic project-resume scenarios into 377 deterministic test cases per provider, runs Laya and Jev through the same localhost API, and records accuracy, robustness, single-vs-batch behavior, calibration, and latency results without storing local project paths.

## GitHub Pages site

The project landing page is a dependency-free static site in [`docs/`](docs/). GitHub Pages can publish it directly from the `main` branch `/docs` folder.

For a local preview:

```bash
python3 -m http.server 8808 --directory docs
```

Then open `http://127.0.0.1:8808/`.

## Quick start

From the project directory:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
jev-laya-local-daemon
```

`python3 --version` should report Python 3.11, 3.12, or 3.13. On systems where `python` is missing or points to another interpreter, use `python3` for every command in this project.
If your default `python3` is outside that range, create the virtual environment with an installed supported interpreter instead, for example `python3.13 -m venv .venv`.

Jev is optional. The simplest setup is a repo-root `.env` file. Start from the included example:

```bash
cp .env.example .env
```

If you have a Jev API key, open `.env` and set:

```dotenv
JEV_API_KEY=your-typesafe-api-key
```

Leave `JEV_API_KEY` empty if you only want local Laya. The daemon loads the repo-root `.env` automatically on startup:

```bash
jev-laya-local-daemon
```

Shell environment variables still take precedence over `.env`. `TYPESAFE_API_KEY` is also accepted as a fallback name. `.env` and `.env.*` are gitignored; `.env.example` is safe to commit.

The first run downloads the Laya checkpoint from Hugging Face, so model startup takes longer the first time. The tested `typed-decisions` checkpoint downloaded about 847 MB. Later starts reuse the local cache.

In another terminal, check that the process is alive:

```bash
curl http://127.0.0.1:8787/health
```

Then wait until the model is ready:

```bash
curl -i http://127.0.0.1:8787/ready
```

When the response changes to HTTP 200 with `"ready": true`, local Laya inference is available. Jev does not depend on Laya readiness; check provider availability with:

```bash
curl http://127.0.0.1:8787/v1/providers
```

Run the included end-to-end smoke test against Laya:

```bash
source .venv/bin/activate
python3 scripts/smoke.py
```

Or through Jev when `JEV_API_KEY` is configured:

```bash
DECISION_PROVIDER=jev python3 scripts/smoke.py
```

It checks `/health`, `/ready`, and real `noul`, `choice`, and `score` inference against the running daemon.

## Requirements

- macOS Apple Silicon is the primary tested platform.
- Python 3.11, 3.12, or 3.13.
- Internet access is needed the first time a Hugging Face checkpoint is downloaded. Inference is local after the model is cached.

Laya 0.3.5 automatically selects MPS on supported Apple Silicon Macs, then falls back to CPU if MPS is unavailable. `LAYA_DEVICE` can explicitly select a device accepted by Laya/PyTorch. Jev requires network access for every inference because it is called through TypeSafe's hosted API.

## Install

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development and tests:

```bash
pip install -e '.[dev]'
pytest
```

## Run

```bash
jev-laya-local-daemon
```

The module entry point works too:

```bash
python3 -m jev_laya_local_daemon
```

Startup begins listening immediately while the model loads once in a daemon thread. During that time `/health` is available and `/ready` returns HTTP 503. When loading finishes, `/ready` returns HTTP 200 and all subsequent requests reuse the same in-memory agent.

Typical startup output looks like this:

```text
jev-laya-local-daemon
Laya: convaiinnovations/laya/typed-decisions
Jev: jev-latest (configured)
Listening: http://127.0.0.1:8787
Laya status: loading
...
Status: ready
```

Keep this process running while other projects use the API. Press `Ctrl+C` to stop it cleanly.

Default configuration:

```text
LAYA_MODEL=convaiinnovations/laya
LAYA_SUBFOLDER=typed-decisions
DAEMON_HOST=127.0.0.1
DAEMON_PORT=8787
DAEMON_PORT_STRICT=0
LAYA_DEVICE=
JEV_API_KEY=
JEV_MODEL=jev-latest
JEV_API_URL=https://api.typesafe.ai
JEV_TIMEOUT_SECONDS=30
```

Example override:

```bash
DAEMON_PORT=8790 LAYA_DEVICE=mps jev-laya-local-daemon
# equivalent: jev-laya-local-daemon --port 8790
```

`DAEMON_HOST` is intentionally restricted to loopback addresses (`127.0.0.1`, `localhost`, or `::1`). `0.0.0.0` is rejected.

`JEV_API_KEY` stays inside the daemon process and is attached as a Bearer token only when the selected provider is Jev. The local caller sends no provider credentials.

`8787` is the default chosen by `jev-laya-local-daemon`; it is not a port assigned or recommended by upstream Laya. The upstream Python package exposes model-loading and prediction APIs rather than this project's HTTP daemon, so the port has no Laya protocol significance and can be changed with `DAEMON_PORT`. See the [upstream Laya project](https://github.com/NandhaKishorM/laya) and [model card](https://huggingface.co/convaiinnovations/laya) for the native package interface.

## Port already in use

The default port is `8787`. If another local service already listens on it — for example the Headroom proxy — the daemon falls back automatically instead of failing: it probes the configured port, then the next ports upward (up to 100 candidates), binds the first free one, and prints the resolved address together with a ready-to-paste `DECISION_API_URL` for callers:

```text
Port 8787 is in use by Python (pid 21844); falling back to 8788
Callers: DECISION_API_URL=http://127.0.0.1:8788
Listening: http://127.0.0.1:8788
```

Point every caller at the URL printed in the banner:

```bash
curl http://127.0.0.1:8788/health
curl http://127.0.0.1:8788/ready
DECISION_API_URL=http://127.0.0.1:8788 python3 scripts/smoke.py
```

The helper scripts in `scripts/` also honor `DAEMON_PORT`, so `DAEMON_PORT=8788 python3 scripts/smoke.py` works without `DECISION_API_URL`. For TypeScript or Python applications, change the endpoint from `http://127.0.0.1:8787` to the resolved URL as well.

A fallback port can change between runs. For a stable address, pin the port. `8790` is a convenient choice when `8787` is permanently occupied:

```bash
DAEMON_PORT=8790 jev-laya-local-daemon
# equivalent: jev-laya-local-daemon --port 8790
```

`--port` and `--host` flags override `DAEMON_PORT` and `DAEMON_HOST`, and `DAEMON_PORT=0` asks the OS for any free port.

To require the configured port and exit instead of falling back, set `DAEMON_PORT_STRICT=1`:

```bash
DAEMON_PORT_STRICT=1 jev-laya-local-daemon
```

```text
error: port 8787 on 127.0.0.1 is already in use by Python (pid 21844)
  lsof -nP -iTCP:8787 -sTCP:LISTEN   # who owns it
  DAEMON_PORT=8790 jev-laya-local-daemon   # or pick another port
  auto-fallback is disabled (DAEMON_PORT_STRICT=1)
```

### Identifying the process on the busy port

Check which process owns the port:

```bash
lsof -nP -iTCP:8787 -sTCP:LISTEN
```

For example, during development of this project, port `8787` was already occupied by a Headroom proxy:

```text
COMMAND   PID   ...  NAME
Python  21844   ...  TCP 127.0.0.1:8787 (LISTEN)
```

If that process is yours and you no longer need it, stop it normally. If necessary, use the PID reported by `lsof`:

```bash
kill PID
```

Replace `PID` with the actual number from the `lsof` output. Do not stop a process you do not recognize; running the daemon on another port is usually simpler (see above).

No output from `lsof` means there is currently no listening process on that port, and the next daemon start binds it directly.

## Health check

```bash
curl http://127.0.0.1:8787/health
```

```json
{"status":"ok"}
```

## Readiness

```bash
curl -i http://127.0.0.1:8787/ready
```

While loading:

```json
{
  "ready": false,
  "model": "convaiinnovations/laya/typed-decisions",
  "status": "loading"
}
```

After the checkpoint is ready:

```json
{
  "ready": true,
  "model": "convaiinnovations/laya/typed-decisions",
  "status": "ready"
}
```

## Providers

`/ready` intentionally describes the resident Laya model. To inspect both providers, use:

```bash
curl http://127.0.0.1:8787/v1/providers
```

Example without a Jev API key:

```json
{
  "laya": {
    "ready": true,
    "status": "ready",
    "model": "convaiinnovations/laya/typed-decisions"
  },
  "jev": {
    "configured": false,
    "model": "jev-latest",
    "api_url": "https://api.typesafe.ai"
  }
}
```

When `JEV_API_KEY` is present, `jev.configured` becomes `true`. The key itself is never returned.

## `POST /v1/decide`

The endpoint accepts the shared typed decision primitives `noul`, `choice`, and `score`. Choose the provider per request:

```json
{
  "provider": "laya",
  "state": {},
  "questions": {}
}
```

or:

```json
{
  "provider": "jev",
  "state": {},
  "questions": {}
}
```

`provider` defaults to `laya` for backward compatibility. Both providers return the same top-level `model`, `answers`, and `usage` shape, and the gateway adds the selected `provider` to the response.

### `noul`

`noul` returns a `P(true)`-style value. The server does not convert it to a boolean; the caller owns the threshold.

```bash
curl http://127.0.0.1:8787/v1/decide \
  -H 'content-type: application/json' \
  -d '{
    "state": {
      "build_failed": true,
      "user_is_active": false
    },
    "provider": "laya",
    "questions": {
      "notify_user": {
        "type": "noul",
        "instructions": "Should the user be notified?"
      }
    }
  }'
```

Laya 0.3.5 returns this shape:

```json
{
  "provider": "laya",
  "model": "laya-rl-agent",
  "answers": {
    "notify_user": {
      "type": "noul",
      "noul": 0.4011,
      "confidence": 0.5989,
      "action": {
        "act_probability": 1.0
      }
    }
  },
  "usage": {
    "input_tokens": 48,
    "output_tokens": 0
  }
}
```

The numeric values above are from one real smoke test and are examples, not fixed expected values.

Jev also accepts optional `true` / `false` criteria for `noul`. The unified request schema allows them; they are forwarded to Jev and ignored for Laya because Laya 0.3.5 does not expose that field.

### `choice`

For `choice`, `criteria` is an object whose keys are the option labels and whose values describe those options.

```bash
curl http://127.0.0.1:8787/v1/decide \
  -H 'content-type: application/json' \
  -d '{
    "provider": "laya",
    "state": {
      "git_dirty": true,
      "last_task": "fix project analysis"
    },
    "questions": {
      "next_action": {
        "type": "choice",
        "instructions": "What should happen next?",
        "criteria": {
          "resume": "Continue the unfinished work",
          "inspect": "Inspect repository changes",
          "reanalyze": "Run analysis again",
          "wait": "Do nothing yet"
        }
      }
    }
  }'
```

The response preserves the selected label, every option probability, confidence, action probability, and token usage:

```json
{
  "provider": "laya",
  "model": "laya-rl-agent",
  "answers": {
    "next_action": {
      "type": "choice",
      "choice": "inspect",
      "probabilities": {
        "resume": 0.2589,
        "inspect": 0.2975,
        "reanalyze": 0.2602,
        "wait": 0.1834
      },
      "confidence": 0.0104,
      "action": {
        "act_probability": 1.0
      }
    }
  },
  "usage": {
    "input_tokens": 57,
    "output_tokens": 0
  }
}
```

### `score`

Laya's current score schema uses an ordered list for `criteria`. The zero-based position in the list is the numeric score level.

```bash
curl http://127.0.0.1:8787/v1/decide \
  -H 'content-type: application/json' \
  -d '{
    "provider": "laya",
    "state": {
      "event": "build failed",
      "blocks_release": true
    },
    "questions": {
      "urgency": {
        "type": "score",
        "instructions": "How urgent is this event?",
        "criteria": ["ignore", "normal", "urgent", "critical"]
      }
    }
  }'
```

The result contains the expected ordinal score and the full distribution:

```json
{
  "provider": "laya",
  "model": "laya-rl-agent",
  "answers": {
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
      "confidence": 0.1965,
      "action": {
        "act_probability": 1.0
      }
    }
  },
  "usage": {
    "input_tokens": 47,
    "output_tokens": 0
  }
}
```

## TypeScript

```ts
const response = await fetch("http://127.0.0.1:8787/v1/decide", {
  method: "POST",
  headers: {
    "content-type": "application/json",
  },
  body: JSON.stringify({
    provider: "laya", // change to "jev" when JEV_API_KEY is configured
    state: {
      git_dirty: true,
      source_changed: true,
    },
    questions: {
      reanalyze: {
        type: "noul",
        instructions: "Should this project be reanalyzed?",
      },
    },
  }),
});

if (!response.ok) {
  throw new Error(`jev-laya-local-daemon failed: ${response.status} ${await response.text()}`);
}

const result = await response.json();
console.log(result.answers.reanalyze.noul);
```

## Python

This example uses only the standard library:

```python
import json
import urllib.request

payload = {
    "provider": "laya",  # change to "jev" when JEV_API_KEY is configured
    "state": {
        "git_dirty": True,
        "source_changed": True,
    },
    "questions": {
        "reanalyze": {
            "type": "noul",
            "instructions": "Should this project be reanalyzed?",
        }
    },
}

request = urllib.request.Request(
    "http://127.0.0.1:8787/v1/decide",
    data=json.dumps(payload).encode(),
    headers={"content-type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(request) as response:
    result = json.load(response)

print(result["answers"]["reanalyze"]["noul"])
```

## Model cache

Laya downloads Hub checkpoints with `huggingface_hub.snapshot_download()`. Do not assume the cache path; ask the installed Hugging Face library:

```bash
python3 - <<'PY'
from huggingface_hub.constants import HF_HUB_CACHE
print(HF_HUB_CACHE)
PY
```

Environment variables supported by Hugging Face can relocate that cache.

## Smoke test

Start the daemon, wait until `/ready` is HTTP 200, then run:

```bash
python3 scripts/smoke.py
```

If the daemon is on a non-default port:

```bash
DECISION_API_URL=http://127.0.0.1:8790 python3 scripts/smoke.py
```

The scripts also honor `DAEMON_PORT`, so `DAEMON_PORT=8790 python3 scripts/smoke.py` is equivalent.



The script calls `/health`, `/ready`, and real `noul`, `choice`, and `score` requests against the running daemon.

To use the same script through Jev:

```bash
DECISION_PROVIDER=jev python3 scripts/smoke.py
```

## Errors

Missing state, missing or empty questions, unknown providers/question types, malformed `choice`/`score` criteria, and malformed JSON return JSON 4xx responses. Laya inference failures return a generic JSON 500 response while the Python traceback stays in server logs. Missing Jev configuration returns 503; sanitized TypeSafe authentication/upstream failures return 502.

If model loading fails, `/health` remains 200 and `/ready` returns 503 with `status: "failed"`.

## Shutdown

`Ctrl+C` and `SIGTERM` use Uvicorn's normal graceful shutdown path. Laya 0.3.5 does not expose an Agent `close()` or `unload()` method, so the daemon drops its model reference during shutdown and lets Python/PyTorch release resources with the process.

## Current Laya package API used here

This project is pinned to `laya==0.3.5`. The implementation was checked against the installed package, where the relevant APIs are:

```python
laya.load(model_id_or_path, device=None, token=None, subfolder=None)
agent.predict(state, questions)
```

The default checkpoint is loaded as:

```python
laya.load("convaiinnovations/laya", subfolder="typed-decisions")
```

## Current Jev API used here

Jev uses TypeSafe's hosted System One API:

```text
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <JEV_API_KEY>
```

The gateway adds the configured `JEV_MODEL` (default `jev-latest`) to the forwarded request and returns TypeSafe's structured response without changing its decision values.

## Known limitations

- Laya is loaded at daemon startup even if a process only intends to use Jev. A future lazy-loading mode could remove that local memory cost for Jev-only use.
- Inference is serialized through one in-process lock so concurrent callers reuse the same Agent safely.
- Jev is hosted: selecting `provider: "jev"` sends the supplied state/questions to TypeSafe over the network. Use Laya when the decision input must remain entirely local.
- The Jev adapter currently performs one upstream HTTP request per gateway request and does not add retries or connection pooling.
- Laya 0.3.5 emits a runtime warning for the `choice:11+` calibration bucket in the typed-decisions checkpoint because the shipped temperature is outside Laya's accepted range and is clamped. Treat confidence for that affected bucket as uncalibrated unless upstream calibration changes.
- The first Hub download can be large. On the Apple Silicon smoke-test machine used for this implementation, Hugging Face reported about 847 MB downloaded for the typed-decisions checkpoint. Subsequent startup reported 0.00B additional download from the warm cache.

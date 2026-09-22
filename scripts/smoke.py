from __future__ import annotations

import json
import os
import urllib.request


BASE_URL = os.getenv("DECISION_API_URL", os.getenv("LAYA_API_URL", "http://127.0.0.1:8787"))
PROVIDER = os.getenv("DECISION_PROVIDER", "laya")


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}") as response:
        return json.load(response)


def post(path: str, payload: dict) -> dict:
    payload = {"provider": PROVIDER, **payload}
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def main() -> None:
    print("health:", json.dumps(get("/health"), indent=2))
    print("ready:", json.dumps(get("/ready"), indent=2))

    cases = {
        "noul": {
            "state": {"build_failed": True, "user_is_active": False},
            "questions": {
                "notify_user": {
                    "type": "noul",
                    "instructions": "Should the user be notified?",
                }
            },
        },
        "choice": {
            "state": {"git_dirty": True, "last_task": "fix project analysis"},
            "questions": {
                "next_action": {
                    "type": "choice",
                    "instructions": "What should happen next?",
                    "criteria": {
                        "resume": "Continue the unfinished work",
                        "inspect": "Inspect repository changes",
                        "reanalyze": "Run analysis again",
                        "wait": "Do nothing yet",
                    },
                }
            },
        },
        "score": {
            "state": {"event": "build failed", "blocks_release": True},
            "questions": {
                "urgency": {
                    "type": "score",
                    "instructions": "How urgent is this event?",
                    "criteria": ["ignore", "normal", "urgent", "critical"],
                }
            },
        },
    }

    for name, payload in cases.items():
        print(f"{name}:", json.dumps(post("/v1/decide", payload), indent=2))


if __name__ == "__main__":
    main()

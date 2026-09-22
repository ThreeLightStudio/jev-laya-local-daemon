from __future__ import annotations

import time

from fastapi.testclient import TestClient

from laya_local_api.app import create_app
from laya_local_api.config import Settings
from laya_local_api.jev import JevNotConfiguredError, JevUpstreamError
from laya_local_api.model import ModelRuntime


class FakeAgent:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0
        self.last_state = None
        self.last_questions = None

    def predict(self, state, questions):
        self.calls += 1
        self.last_state = state
        self.last_questions = questions
        if self.fail:
            raise RuntimeError("synthetic inference failure")

        answers = {}
        for question_id, question in questions.items():
            if question["type"] == "noul":
                answers[question_id] = {
                    "type": "noul",
                    "noul": 0.87,
                    "confidence": 0.87,
                    "action": {"act_probability": 0.42},
                }
            elif question["type"] == "choice":
                labels = list(question["criteria"])
                probabilities = {label: 0.0 for label in labels}
                probabilities[labels[0]] = 1.0
                answers[question_id] = {
                    "type": "choice",
                    "choice": labels[0],
                    "probabilities": probabilities,
                    "confidence": 1.0,
                    "action": {"act_probability": 0.42},
                }
            else:
                criteria = question["criteria"]
                answers[question_id] = {
                    "type": "score",
                    "score": 1.0,
                    "legend": {str(i): value for i, value in enumerate(criteria)},
                    "probabilities": {str(i): 1.0 / len(criteria) for i in range(len(criteria))},
                    "confidence": 0.5,
                    "action": {"act_probability": 0.42},
                }
        return {
            "model": "laya-rl-agent",
            "answers": answers,
            "usage": {"input_tokens": 12, "output_tokens": 0},
        }


class FakeJevClient:
    def __init__(self, *, configured: bool = True, failure: Exception | None = None) -> None:
        self.configured = configured
        self.failure = failure
        self.calls: list[tuple[object, dict]] = []

    def predict(self, state, questions):
        self.calls.append((state, questions))
        if self.failure:
            raise self.failure
        return {
            "model": "jev-1.13.0",
            "answers": {
                "decision": {
                    "type": "noul",
                    "noul": 0.91,
                    "stats": {},
                }
            },
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }


def wait_ready(client: TestClient) -> None:
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if client.get("/ready").status_code == 200:
            return
        time.sleep(0.01)
    raise AssertionError("fake model did not become ready")


def make_client(agent: FakeAgent | None = None, jev_client: FakeJevClient | None = None):
    settings = Settings()
    fake_agent = agent or FakeAgent()
    fake_jev = jev_client or FakeJevClient()
    loads = {"count": 0}

    def loader(_settings: Settings):
        loads["count"] += 1
        return fake_agent

    runtime = ModelRuntime(settings, loader=loader)
    return (
        TestClient(create_app(settings=settings, runtime=runtime, jev_client=fake_jev)),
        runtime,
        fake_agent,
        fake_jev,
        loads,
    )


def test_health_and_ready() -> None:
    client, runtime, _, _, _ = make_client()
    with client:
        assert client.get("/health").json() == {"status": "ok"}
        wait_ready(client)
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {
            "ready": True,
            "model": "convaiinnovations/laya/typed-decisions",
            "status": "ready",
        }
        assert runtime.load_count == 1

        providers = client.get("/v1/providers")
        assert providers.status_code == 200
        assert providers.json() == {
            "laya": {
                "ready": True,
                "status": "ready",
                "model": "convaiinnovations/laya/typed-decisions",
            },
            "jev": {
                "configured": True,
                "model": "jev-latest",
                "api_url": "https://api.typesafe.ai",
            },
        }


def test_noul_choice_score_and_single_load() -> None:
    client, runtime, agent, _, loads = make_client()
    with client:
        wait_ready(client)

        payloads = [
            {
                "state": {"build_failed": True},
                "questions": {
                    "notify": {"type": "noul", "instructions": "Should the user be notified?"}
                },
            },
            {
                "state": {"git_dirty": True},
                "questions": {
                    "next": {
                        "type": "choice",
                        "instructions": "What should happen next?",
                        "criteria": {"resume": "Continue work", "inspect": "Inspect changes"},
                    }
                },
            },
            {
                "state": {"event": "build failed"},
                "questions": {
                    "urgency": {
                        "type": "score",
                        "instructions": "How urgent is this event?",
                        "criteria": ["ignore", "normal", "urgent", "critical"],
                    }
                },
            },
        ]

        results = [client.post("/v1/decide", json=payload).json() for payload in payloads]
        assert all(result["provider"] == "laya" for result in results)
        assert results[0]["answers"]["notify"]["noul"] == 0.87
        assert results[1]["answers"]["next"]["choice"] == "resume"
        assert results[1]["answers"]["next"]["probabilities"] == {"resume": 1.0, "inspect": 0.0}
        assert results[2]["answers"]["urgency"]["score"] == 1.0
        assert set(results[2]["answers"]["urgency"]["probabilities"]) == {"0", "1", "2", "3"}
        assert loads["count"] == 1
        assert runtime.load_count == 1
        assert agent.calls == 3


def test_jev_provider_uses_same_endpoint_and_preserves_noul_criteria() -> None:
    fake_jev = FakeJevClient()
    client, _, agent, jev, _ = make_client(jev_client=fake_jev)
    with client:
        response = client.post(
            "/v1/decide",
            json={
                "provider": "jev",
                "state": {"event": "suspicious transfer"},
                "questions": {
                    "decision": {
                        "type": "noul",
                        "instructions": "Should this be escalated?",
                        "criteria": {
                            "true": "Human review is required.",
                            "false": "Automation may continue.",
                        },
                    }
                },
            },
        )

        assert response.status_code == 200
        assert response.json()["provider"] == "jev"
        assert response.json()["model"] == "jev-1.13.0"
        assert response.json()["answers"]["decision"]["noul"] == 0.91
        assert agent.calls == 0
        assert jev.calls == [
            (
                {"event": "suspicious transfer"},
                {
                    "decision": {
                        "type": "noul",
                        "instructions": "Should this be escalated?",
                        "criteria": {
                            "true": "Human review is required.",
                            "false": "Automation may continue.",
                        },
                    }
                },
            )
        ]


def test_laya_provider_strips_jev_only_noul_criteria() -> None:
    client, _, agent, _, _ = make_client()
    with client:
        wait_ready(client)
        response = client.post(
            "/v1/decide",
            json={
                "provider": "laya",
                "state": {"event": "build failed"},
                "questions": {
                    "notify": {
                        "type": "noul",
                        "instructions": "Should the user be notified?",
                        "criteria": {"true": "Yes", "false": "No"},
                    }
                },
            },
        )

        assert response.status_code == 200
        assert agent.calls == 1
        assert agent.last_questions == {
            "notify": {
                "type": "noul",
                "instructions": "Should the user be notified?",
            }
        }


def test_jev_provider_errors_are_sanitized() -> None:
    not_configured = FakeJevClient(configured=False, failure=JevNotConfiguredError("Jev provider is not configured; set JEV_API_KEY"))
    client, _, _, _, _ = make_client(jev_client=not_configured)
    with client:
        response = client.post(
            "/v1/decide",
            json={
                "provider": "jev",
                "state": {},
                "questions": {"decision": {"type": "noul", "instructions": "Proceed?"}},
            },
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "Jev provider is not configured; set JEV_API_KEY"}

    upstream_failure = FakeJevClient(failure=JevUpstreamError("Jev authentication failed"))
    client, _, _, _, _ = make_client(jev_client=upstream_failure)
    with client:
        response = client.post(
            "/v1/decide",
            json={
                "provider": "jev",
                "state": {},
                "questions": {"decision": {"type": "noul", "instructions": "Proceed?"}},
            },
        )
        assert response.status_code == 502
        assert response.json() == {"detail": "Jev authentication failed"}


def test_invalid_payloads_return_4xx() -> None:
    client, _, _, _, _ = make_client()
    with client:
        wait_ready(client)
        invalid_payloads = [
            {"questions": {"x": {"type": "noul", "instructions": "Question?"}}},
            {"state": {}, "questions": {}},
            {"state": {}, "questions": {"x": {"type": "wat", "instructions": "Question?"}}},
            {
                "state": {},
                "questions": {
                    "x": {
                        "type": "choice",
                        "instructions": "Pick one",
                        "criteria": {"only": "Only one option"},
                    }
                },
            },
            {
                "state": {},
                "questions": {
                    "x": {
                        "type": "score",
                        "instructions": "Rate it",
                        "criteria": ["only one level"],
                    }
                },
            },
        ]
        for payload in invalid_payloads:
            response = client.post("/v1/decide", json=payload)
            assert 400 <= response.status_code < 500
            assert response.headers["content-type"].startswith("application/json")

        malformed = client.post(
            "/v1/decide",
            content="{",
            headers={"content-type": "application/json"},
        )
        assert 400 <= malformed.status_code < 500
        assert malformed.headers["content-type"].startswith("application/json")


def test_model_failure_is_sanitized_500() -> None:
    client, _, _, _, _ = make_client(FakeAgent(fail=True))
    with client:
        wait_ready(client)
        response = client.post(
            "/v1/decide",
            json={
                "state": {"x": 1},
                "questions": {"x": {"type": "noul", "instructions": "Is x present?"}},
            },
        )
        assert response.status_code == 500
        assert response.json() == {"detail": "Laya inference failed"}
        assert "synthetic inference failure" not in response.text


def test_load_failure_keeps_health_up_and_ready_false() -> None:
    settings = Settings()

    def failing_loader(_settings: Settings):
        raise RuntimeError("synthetic load failure")

    runtime = ModelRuntime(settings, loader=failing_loader)
    client = TestClient(create_app(settings=settings, runtime=runtime, jev_client=FakeJevClient()))
    with client:
        deadline = time.monotonic() + 1.0
        response = client.get("/ready")
        while response.json()["status"] != "failed" and time.monotonic() < deadline:
            time.sleep(0.01)
            response = client.get("/ready")

        assert client.get("/health").status_code == 200
        assert response.status_code == 503
        assert response.json()["ready"] is False
        assert response.json()["status"] == "failed"

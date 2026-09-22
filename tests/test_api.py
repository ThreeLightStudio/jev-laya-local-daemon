from __future__ import annotations

import time

from fastapi.testclient import TestClient

from laya_local_api.app import create_app
from laya_local_api.config import Settings
from laya_local_api.model import ModelRuntime


class FakeAgent:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def predict(self, state, questions):
        self.calls += 1
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


def wait_ready(client: TestClient) -> None:
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if client.get("/ready").status_code == 200:
            return
        time.sleep(0.01)
    raise AssertionError("fake model did not become ready")


def make_client(agent: FakeAgent | None = None):
    settings = Settings()
    fake_agent = agent or FakeAgent()
    loads = {"count": 0}

    def loader(_settings: Settings):
        loads["count"] += 1
        return fake_agent

    runtime = ModelRuntime(settings, loader=loader)
    return TestClient(create_app(settings=settings, runtime=runtime)), runtime, fake_agent, loads


def test_health_and_ready() -> None:
    client, runtime, _, _ = make_client()
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


def test_noul_choice_score_and_single_load() -> None:
    client, runtime, agent, loads = make_client()
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
        assert results[0]["answers"]["notify"]["noul"] == 0.87
        assert results[1]["answers"]["next"]["choice"] == "resume"
        assert results[1]["answers"]["next"]["probabilities"] == {"resume": 1.0, "inspect": 0.0}
        assert results[2]["answers"]["urgency"]["score"] == 1.0
        assert set(results[2]["answers"]["urgency"]["probabilities"]) == {"0", "1", "2", "3"}
        assert loads["count"] == 1
        assert runtime.load_count == 1
        assert agent.calls == 3


def test_invalid_payloads_return_4xx() -> None:
    client, _, _, _ = make_client()
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
    client, _, _, _ = make_client(FakeAgent(fail=True))
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
    client = TestClient(create_app(settings=settings, runtime=runtime))
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

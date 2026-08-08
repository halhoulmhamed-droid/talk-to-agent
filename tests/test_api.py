import asyncio

import pytest


VALID_WEBRTC_ID = "123e4567-e89b-42d3-a456-426614174000"


class FakeStream:
    def __init__(self, connections=None):
        self.connections = connections or {}
        self.inputs = []

    def set_input(self, webrtc_id, voice_name):
        self.inputs.append((webrtc_id, voice_name))


def test_essential_routes_are_mounted(agent):
    paths = {route.path for route in agent.app.routes}

    assert {
        "/",
        "/static",
        "/webrtc/offer",
        "/input_hook",
        "/config/rtc",
    }.issubset(paths)


def test_rtc_config_uses_cloudflare_turn_with_hf_token(
    agent, monkeypatch
):
    expected = {"iceServers": [{"urls": ["turn:example.invalid:3478"]}]}
    calls = []

    async def fake_turn_credentials():
        calls.append(True)
        return expected

    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setattr(agent, "get_space", lambda: False)
    monkeypatch.setattr(
        agent, "get_cloudflare_turn_credentials_async", fake_turn_credentials
    )

    assert agent.select_rtc_configuration() is fake_turn_credentials
    assert asyncio.run(agent.rtc_config()) == expected
    assert calls == [True]


def test_rtc_config_returns_local_configuration_without_hf_token(
    agent, monkeypatch
):
    expected = {"iceServers": [{"urls": ["stun:example.invalid:3478"]}]}

    async def forbidden_turn_credentials():
        pytest.fail("Cloudflare TURN must not be requested without HF_TOKEN")

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(agent, "get_space", lambda: False)
    monkeypatch.setattr(agent, "rtc_configuration", expected)
    monkeypatch.setattr(
        agent,
        "get_cloudflare_turn_credentials_async",
        forbidden_turn_credentials,
    )

    assert agent.select_rtc_configuration() is expected
    assert asyncio.run(agent.rtc_config()) == expected


def test_set_voice_rejects_unknown_session(agent, monkeypatch):
    fake_stream = FakeStream()
    monkeypatch.setattr(agent, "stream", fake_stream)
    body = agent.InputData(
        webrtc_id=VALID_WEBRTC_ID,
        voice_name="Zephyr",
    )

    with pytest.raises(agent.HTTPException) as exc_info:
        asyncio.run(agent.set_voice(body))

    assert exc_info.value.status_code == 404
    assert fake_stream.inputs == []


def test_set_voice_passes_valid_input_to_known_session(agent, monkeypatch):
    fake_stream = FakeStream(connections={VALID_WEBRTC_ID: object()})
    monkeypatch.setattr(agent, "stream", fake_stream)
    body = agent.InputData(
        webrtc_id=VALID_WEBRTC_ID,
        voice_name="Kore",
    )

    response = asyncio.run(agent.set_voice(body))

    assert response == {"status": "ok"}
    assert fake_stream.inputs == [(VALID_WEBRTC_ID, "Kore")]

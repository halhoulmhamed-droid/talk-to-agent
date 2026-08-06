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


def test_rtc_config_returns_local_configuration_without_network(
    agent, monkeypatch
):
    expected = {"iceServers": [{"urls": ["stun:example.invalid:3478"]}]}
    monkeypatch.setattr(agent, "get_space", lambda: False)
    monkeypatch.setattr(agent, "rtc_configuration", expected)

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

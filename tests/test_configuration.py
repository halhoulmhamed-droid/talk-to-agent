import json

import pytest
from pydantic import ValidationError


VALID_WEBRTC_ID = "123e4567-e89b-42d3-a456-426614174000"


def test_load_rtc_configuration_uses_default_when_variable_is_absent(
    agent, monkeypatch
):
    monkeypatch.delenv("RTC_CONFIGURATION", raising=False)

    assert agent.load_rtc_configuration() == agent.DEFAULT_RTC_CONFIGURATION


def test_load_rtc_configuration_accepts_valid_json(agent, monkeypatch):
    expected = {
        "iceServers": [{"urls": ["stun:example.invalid:3478"]}],
        "iceTransportPolicy": "all",
    }
    monkeypatch.setenv("RTC_CONFIGURATION", json.dumps(expected))

    assert agent.load_rtc_configuration() == expected


def test_load_rtc_configuration_rejects_invalid_json(agent, monkeypatch):
    monkeypatch.setenv("RTC_CONFIGURATION", "{not-json}")

    with pytest.raises(RuntimeError, match="must be valid JSON"):
        agent.load_rtc_configuration()


def test_load_rtc_configuration_rejects_non_object_root(agent, monkeypatch):
    monkeypatch.setenv("RTC_CONFIGURATION", "[]")

    with pytest.raises(RuntimeError, match="must be a JSON object"):
        agent.load_rtc_configuration()


@pytest.mark.parametrize(
    "configuration",
    [{}, {"iceServers": None}, {"iceServers": {}}],
)
def test_load_rtc_configuration_requires_ice_servers_array(
    agent, monkeypatch, configuration
):
    monkeypatch.setenv("RTC_CONFIGURATION", json.dumps(configuration))

    with pytest.raises(RuntimeError, match="iceServers must be a JSON array"):
        agent.load_rtc_configuration()


def test_resolve_tls_files_accepts_no_configuration(agent, monkeypatch):
    monkeypatch.delenv("APP_PEM", raising=False)
    monkeypatch.delenv("APP_KEY", raising=False)

    assert agent.resolve_tls_files() == (None, None)


def test_resolve_tls_files_accepts_absolute_existing_pair(
    agent, monkeypatch, tmp_path
):
    pem = tmp_path / "app.pem"
    key = tmp_path / "app.key"
    pem.write_text("test certificate placeholder", encoding="utf-8")
    key.write_text("test key placeholder", encoding="utf-8")
    monkeypatch.setenv("APP_PEM", str(pem))
    monkeypatch.setenv("APP_KEY", str(key))

    assert agent.resolve_tls_files() == (str(pem), str(key))


def test_resolve_tls_files_resolves_relative_paths_from_project_root(
    agent, monkeypatch, tmp_path
):
    certificate_dir = tmp_path / "certificates"
    certificate_dir.mkdir()
    pem = certificate_dir / "app.pem"
    key = certificate_dir / "app.key"
    pem.write_text("test certificate placeholder", encoding="utf-8")
    key.write_text("test key placeholder", encoding="utf-8")
    monkeypatch.setattr(agent, "project_root", tmp_path)
    monkeypatch.setenv("APP_PEM", "certificates/app.pem")
    monkeypatch.setenv("APP_KEY", "certificates/app.key")

    assert agent.resolve_tls_files() == (str(pem), str(key))


def test_resolve_tls_files_rejects_partial_pair(agent, monkeypatch, tmp_path):
    pem = tmp_path / "app.pem"
    pem.write_text("test certificate placeholder", encoding="utf-8")
    monkeypatch.setenv("APP_PEM", str(pem))
    monkeypatch.delenv("APP_KEY", raising=False)

    with pytest.raises(RuntimeError, match="must be configured together"):
        agent.resolve_tls_files()


def test_resolve_tls_files_rejects_missing_file(agent, monkeypatch, tmp_path):
    pem = tmp_path / "app.pem"
    pem.write_text("test certificate placeholder", encoding="utf-8")
    monkeypatch.setenv("APP_PEM", str(pem))
    monkeypatch.setenv("APP_KEY", str(tmp_path / "missing.key"))

    with pytest.raises(RuntimeError, match="must both point to existing files"):
        agent.resolve_tls_files()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_resolve_app_host_accepts_loopback_without_tls(
    agent, monkeypatch, host
):
    monkeypatch.setattr(agent, "app_pem", None)
    monkeypatch.setattr(agent, "app_key", None)
    monkeypatch.setenv("APP_HOST", host)

    assert agent.resolve_app_host() == host


def test_resolve_app_host_rejects_non_loopback_without_tls(agent, monkeypatch):
    monkeypatch.setattr(agent, "app_pem", None)
    monkeypatch.setattr(agent, "app_key", None)
    monkeypatch.setenv("APP_HOST", "0.0.0.0")

    with pytest.raises(RuntimeError, match="only bind to a loopback host"):
        agent.resolve_app_host()


def test_resolve_app_host_rejects_empty_value(agent, monkeypatch):
    monkeypatch.setenv("APP_HOST", "   ")

    with pytest.raises(RuntimeError, match="must not be empty"):
        agent.resolve_app_host()


def test_resolve_app_port_uses_default(agent, monkeypatch):
    monkeypatch.delenv("APP_PORT", raising=False)

    assert agent.resolve_app_port() == 7860


def test_resolve_app_port_accepts_valid_integer(agent, monkeypatch):
    monkeypatch.setenv("APP_PORT", "8080")

    assert agent.resolve_app_port() == 8080


def test_resolve_app_port_rejects_non_numeric_value(agent, monkeypatch):
    monkeypatch.setenv("APP_PORT", "not-a-port")

    with pytest.raises(RuntimeError, match="must be an integer"):
        agent.resolve_app_port()


@pytest.mark.parametrize("port", ["0", "-1", "65536"])
def test_resolve_app_port_rejects_out_of_range_value(agent, monkeypatch, port):
    monkeypatch.setenv("APP_PORT", port)

    with pytest.raises(RuntimeError, match="must be between 1 and 65535"):
        agent.resolve_app_port()


@pytest.mark.parametrize(
    "voice_name", ["Zephyr", "Charon", "Kore", "Autonoe", "Alnilam"]
)
def test_input_data_accepts_valid_uuid_and_supported_voices(agent, voice_name):
    data = agent.InputData(webrtc_id=VALID_WEBRTC_ID, voice_name=voice_name)

    assert data.webrtc_id == VALID_WEBRTC_ID
    assert data.voice_name == voice_name


def test_input_data_rejects_invalid_uuid(agent):
    with pytest.raises(ValidationError):
        agent.InputData(webrtc_id="not-a-uuid", voice_name="Zephyr")


def test_input_data_rejects_unsupported_voice(agent):
    with pytest.raises(ValidationError):
        agent.InputData(webrtc_id=VALID_WEBRTC_ID, voice_name="Unsupported")

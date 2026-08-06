import ipaddress
import os
import socket
from unittest.mock import patch

import pytest


SENSITIVE_ENV_VARS = (
    "GEMINI_API_KEY",
    "APP_PEM",
    "APP_KEY",
    "RTC_CONFIGURATION",
    "APP_HOST",
    "APP_PORT",
)


os.environ["PYTHON_DOTENV_DISABLED"] = "1"
for variable in SENSITIVE_ENV_VARS:
    os.environ.pop(variable, None)


_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_ORIGINAL_SOCKET_CONNECT_EX = socket.socket.connect_ex


def _reject_network(*args, **kwargs):
    raise AssertionError("Network access is forbidden during the test suite.")


def _is_literal_loopback(address):
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if not isinstance(host, str):
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_create_connection(address, *args, **kwargs):
    if not _is_literal_loopback(address):
        _reject_network()
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def _guarded_socket_connect(sock, address):
    if not _is_literal_loopback(address):
        _reject_network()
    return _ORIGINAL_SOCKET_CONNECT(sock, address)


def _guarded_socket_connect_ex(sock, address):
    if not _is_literal_loopback(address):
        _reject_network()
    return _ORIGINAL_SOCKET_CONNECT_EX(sock, address)


with (
    patch("socket.create_connection", _guarded_create_connection),
    patch.object(socket.socket, "connect", _guarded_socket_connect),
    patch.object(socket.socket, "connect_ex", _guarded_socket_connect_ex),
):
    from src.app import agent as application


@pytest.fixture(scope="session")
def agent():
    return application


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", _guarded_create_connection)
    monkeypatch.setattr(socket.socket, "connect", _guarded_socket_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_socket_connect_ex)

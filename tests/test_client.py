"""Offline protocol, privacy and task-ownership checks for the controlled client."""

import asyncio
import json
import ssl
from collections import deque
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import aiohttp
import pytest
from aiohttp import web

from custom_components.fpa.api import (
    ApiError,
    AuthenticationError,
    CommandError,
    ConnectionError,
    FpaClient,
)
from custom_components.fpa.vendor import pybabyfpa as protocol

DISCOVERY = {
    "api": "api.synthetic.invalid",
    "websockets": "wss://push.synthetic.invalid/ws",
}
TOKENS = {"token": "synthetic-access", "refreshToken": "synthetic-refresh"}


class FakeResponse:
    """No real DNS, TLS, vendor account or machine is touched by these tests."""

    def __init__(self, payload=None, status=200, error=None):
        self.payload = payload
        self.status = status
        self.error = error
        self.json_calls = 0

    async def __aenter__(self):
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *args):
        return None

    async def json(self):
        self.json_calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return deepcopy(self.payload)


class FakeSocket:
    def __init__(self):
        self.messages = asyncio.Queue()
        self.closed = False

    async def receive(self):
        return await self.messages.get()

    async def close(self):
        self.closed = True

    def send(self, payload):
        self.messages.put_nowait(
            SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(payload))
        )

    def disconnect(self):
        self.messages.put_nowait(
            SimpleNamespace(type=aiohttp.WSMsgType.CLOSED, data=None)
        )


class FakeSession:
    def __init__(self, responses=()):
        self.responses = deque(responses)
        self.requests = []
        self.connections = []
        self.sockets = asyncio.Queue()
        self.closed = False

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        assert self.responses, "Unexpected cloud request"
        response = self.responses.popleft()
        return (
            response if isinstance(response, FakeResponse) else FakeResponse(response)
        )

    async def ws_connect(self, url, **kwargs):
        self.connections.append((url, kwargs))
        value = await self.sockets.get()
        if isinstance(value, Exception):
            raise value
        return value

    async def close(self):
        self.closed = True


async def spin_until(predicate):
    async with asyncio.timeout(1):
        while not predicate():  # noqa: ASYNC110 - bounded wait for mock task scheduling
            await asyncio.sleep(0)


async def logged_in_client(extra=(), token_callback=None):
    session = FakeSession([DISCOVERY, TOKENS, *extra])
    client = FpaClient(session, token_callback)
    await client.login("synthetic@example.invalid", "synthetic-password")
    return client, session


async def test_wire_reads_keep_presets_alerts_history_and_independent_snapshots(
    device_payload, identity
):
    """The boundary preserves data old pybabyfpa discarded or incorrectly typed."""
    account = {"id": 7, "email": "synthetic@example.invalid", "devices": [identity]}
    client, session = await logged_in_client([account, device_payload, device_payload])
    try:
        me = await client.get_me()
        first = await client.get_device_details(identity["deviceId"])
        assert (
            first["shadow"]["state"]["reported"]["hardware"]["alerts"]["tempHeating"]
            is not None
        )
        assert "lastBottle" in first["shadow"]["state"]["reported"]
        assert first["bottles"] == device_payload["bottles"]
        assert first["bottleCreationLog"] == device_payload["bottleCreationLog"]
        me["devices"][0]["title"] = "Changed by caller"
        first["bottles"].clear()
        second = await client.get_device_details(identity["deviceId"])
        assert second["bottles"] == device_payload["bottles"]
        assert client.devices[0]["title"] == identity["title"]
        assert client.account_id == "7"
        assert client.email == "synthetic@example.invalid"
        assert [request[0] for request in session.requests] == [
            "GET",
            "POST",
            "GET",
            "GET",
            "GET",
        ]
        assert session.requests[2][1].endswith("/authentication/me")
        assert session.requests[3][1].endswith(
            f"/devices/{identity['deviceId']}/details"
        )
        for _, _, kwargs in session.requests:
            assert kwargs["timeout"].total == 30
            assert kwargs["allow_redirects"] is False
            assert "ssl" not in kwargs  # Certificate verification remains enabled.
    finally:
        await client.close()


@pytest.mark.parametrize(
    "status,error_type",
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (400, ApiError),
        (429, ApiError),
        (503, ApiError),
    ],
)
async def test_http_failure_classification_does_not_parse_server_error(
    status, error_type
):
    response = FakeResponse({"message": "PRIVATE-EMAIL-AND-TOKEN"}, status=status)
    session = FakeSession([DISCOVERY, response])
    client = FpaClient(session)
    try:
        with pytest.raises(error_type) as raised:
            await client.login("synthetic@example.invalid", "synthetic-password")
        assert response.json_calls == 0
        assert raised.value.status == status
        assert "PRIVATE" not in str(raised.value)
        assert "synthetic" not in str(raised.value)
        if status not in (401, 403):
            assert not isinstance(raised.value, AuthenticationError)
    finally:
        await client.close()


@pytest.mark.parametrize(
    "error,category",
    [
        (TimeoutError("PRIVATE-TIMEOUT-URL"), "timeout"),
        (aiohttp.ClientConnectionError("PRIVATE-WEBSOCKET-URL"), "connection"),
        (OSError("PRIVATE-HOST"), "connection"),
        (
            aiohttp.ClientConnectorCertificateError(
                None, ssl.SSLCertVerificationError("PRIVATE-TLS-CREDENTIAL-URL")
            ),
            "tls",
        ),
    ],
)
async def test_network_errors_are_safe_and_not_bad_credentials(error, category):
    session = FakeSession([FakeResponse(error=error)])
    client = FpaClient(session)
    try:
        with pytest.raises(ConnectionError) as raised:
            await client.refresh("synthetic-refresh")
        assert raised.value.category == category
        assert "PRIVATE" not in str(raised.value)
        assert not isinstance(raised.value, AuthenticationError)
    finally:
        await client.close()


@pytest.mark.parametrize("response", [[], None, ValueError("PRIVATE-JSON-BODY")])
async def test_malformed_success_responses_are_safe_protocol_errors(response):
    session = FakeSession([response])
    client = FpaClient(session)
    try:
        with pytest.raises(ApiError, match="protocol"):
            await client.login("synthetic@example.invalid", "synthetic-password")
        assert client.authenticated is False
    finally:
        await client.close()


@pytest.mark.parametrize(
    "discovery",
    [
        {"api": "http://insecure.invalid", "websockets": "wss://push.invalid"},
        {"api": "api.invalid", "websockets": "ws://insecure.invalid"},
        {
            "api": "api.invalid",
            "websockets": "wss://push.invalid?Authorization=PRIVATE",
        },
        {"api": "person:PRIVATE@api.invalid", "websockets": "wss://push.invalid"},
        {"api": "[invalid", "websockets": "wss://push.invalid"},
    ],
)
async def test_discovery_refuses_insecure_or_credential_bearing_endpoints(discovery):
    client = FpaClient(FakeSession([discovery]))
    try:
        with pytest.raises(ApiError, match="protocol"):
            await client.login("synthetic@example.invalid", "synthetic-password")
    finally:
        await client.close()


async def test_rotated_token_callback_and_concurrent_refresh_serialization():
    callback = Mock()
    client, session = await logged_in_client(
        [
            {"token": "second-access", "refreshToken": "second-refresh"},
            {"token": "third-access", "refreshToken": "third-refresh"},
        ],
        token_callback=callback,
    )
    try:
        await asyncio.gather(
            client.refresh("synthetic-refresh"), client.refresh("synthetic-refresh")
        )
        assert callback.call_args_list == [
            (("synthetic-refresh",),),
            (("second-refresh",),),
            (("third-refresh",),),
        ]
        refresh_requests = [
            request for request in session.requests if request[1].endswith("/refresh")
        ]
        assert [request[2]["json"]["refreshToken"] for request in refresh_requests] == [
            "synthetic-refresh",
            "second-refresh",
        ]
        assert client.refresh_token == "third-refresh"
        assert client.authenticated is True
    finally:
        await client.close()
    assert session.closed is False


async def test_refresh_lock_covers_an_actually_overlapping_token_exchange():
    entered, release = asyncio.Event(), asyncio.Event()

    class BlockingResponse(FakeResponse):
        async def __aenter__(self):
            entered.set()
            await release.wait()
            return self

    client, session = await logged_in_client(
        [
            BlockingResponse(
                {"token": "second-access", "refreshToken": "second-refresh"}
            ),
            {"token": "third-access", "refreshToken": "third-refresh"},
        ]
    )
    first = asyncio.create_task(client.refresh("synthetic-refresh"))
    await entered.wait()
    second = asyncio.create_task(client.refresh("synthetic-refresh"))
    try:
        await asyncio.sleep(0)
        assert len(session.requests) == 3  # The second exchange is waiting on the lock.
        release.set()
        await asyncio.gather(first, second)
        assert [
            request[2]["json"]["refreshToken"] for request in session.requests[2:]
        ] == [
            "synthetic-refresh",
            "second-refresh",
        ]
    finally:
        release.set()
        await asyncio.gather(first, second, return_exceptions=True)
        await client.close()


async def test_account_read_authentication_retry_is_one_read_after_refresh():
    client, session = await logged_in_client(
        [
            FakeResponse(status=401),
            {"token": "new-access", "refreshToken": "new-refresh"},
            {"devices": []},
        ]
    )
    try:
        assert await client.get_me() == {"devices": []}
        assert [request[1].rsplit("/", 1)[-1] for request in session.requests] == [
            "info.babybrezzacloud.com",
            "login",
            "me",
            "refresh",
            "me",
        ]
        assert session.requests[-1][2]["headers"]["Authorization"] == "new-access"
    finally:
        await client.close()


@pytest.mark.parametrize(
    "response,error_type",
    [
        (FakeResponse(error=TimeoutError("PRIVATE-TOKEN-URL")), ConnectionError),
        (FakeResponse(status=401), AuthenticationError),
        (FakeResponse({"error": "PRIVATE"}, status=409), CommandError),
        (FakeResponse({"error": "PRIVATE"}, status=503), CommandError),
    ],
)
async def test_start_is_sent_once_and_never_automatically_replayed(
    response, error_type
):
    client, session = await logged_in_client([response])
    try:
        with pytest.raises(error_type):
            await client.start_bottle(123)
        starts = [request for request in session.requests if request[0] == "PUT"]
        assert len(starts) == 1
        assert starts[0][1].endswith("/bottles/123/start")
        assert len(session.requests) == 3
    finally:
        await client.close()


async def test_start_acceptance_does_not_require_undocumented_response_body():
    response = FakeResponse(ValueError("Unspecified command response"))
    client, _ = await logged_in_client([response])
    try:
        assert await client.start_bottle(123) == {}
        assert response.json_calls == 0
        for invalid in (0, -1, True, "123", None):
            with pytest.raises(CommandError):
                await client.start_bottle(invalid)
    finally:
        await client.close()


async def test_subscription_is_idempotent_validates_identity_and_keeps_raw_envelopes():
    client, session = await logged_in_client()
    socket = FakeSocket()
    session.sockets.put_nowait(socket)
    first_callback, messages, connection = Mock(), [], []
    try:
        await client.subscribe("device-one", first_callback, connection.append)
        await client.subscribe("device-one", messages.append, connection.append)
        await spin_until(lambda: connection == [True])
        assert client.subscription_count == 1
        assert client.reconnect_attempts == {"device-one": 0}
        assert len(session.connections) == 1
        envelope = {
            "subject": "shadow-update",
            "body": {
                "deviceId": "device-one",
                "state": {"reported": {"hardware": {"alerts": {"tempHeating": True}}}},
            },
        }
        socket.send(["malformed"])
        socket.messages.put_nowait(
            SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data="invalid JSON")
        )
        unknown = {"subject": "unknown", "body": {"deviceId": "device-one"}}
        socket.send(unknown)
        socket.send({"subject": "ping", "body": {"deviceId": "device-one"}})
        socket.send(
            {
                "subject": "authentication",
                "body": {"deviceId": "device-one", "token": "PRIVATE"},
            }
        )
        socket.send(
            {"subject": "shadow-update", "body": {"deviceId": "another-device"}}
        )
        socket.send(
            {
                "subject": "shadow-update",
                "body": {"deviceId": "device-one", "device_id": "another-device"},
            }
        )
        socket.send({"subject": "shadow-update", "body": {"state": {}}})
        socket.send(envelope)
        await spin_until(lambda: len(messages) == 2)
        assert messages == [unknown, envelope]
        assert first_callback.call_count == 0
        messages[1]["body"]["state"].clear()
        assert envelope["body"]["state"]
        assert session.connections[0][1]["heartbeat"] == 600
        assert "ssl" not in session.connections[0][1]
    finally:
        await client.close()
    assert socket.closed is True
    assert connection == [True]  # No runtime callbacks after unload starts.
    assert client.subscription_count == 0
    assert session.closed is False


async def test_establishment_failure_reconnects_refreshes_and_reconciles(monkeypatch):
    monkeypatch.setattr(protocol, "RECONNECT_INITIAL_DELAY", 0)
    client, session = await logged_in_client(
        [
            {"token": "reconnected-access", "refreshToken": "rotated-refresh"},
        ]
    )
    session.sockets.put_nowait(aiohttp.ClientConnectionError("PRIVATE-CREDENTIAL-URL"))
    socket = FakeSocket()
    session.sockets.put_nowait(socket)
    connections = []
    try:
        await client.subscribe("device-one", Mock(), connections.append)
        await spin_until(lambda: connections == [True])
        assert len(session.connections) == 2
        assert "reconnected-access" in session.connections[-1][0]
        assert client.refresh_token == "rotated-refresh"
        assert client.last_error is None
        assert client.reconnect_attempts == {"device-one": 1}
        await client.subscribe("device-one", Mock(), connections.append)
        assert client.reconnect_attempts == {"device-one": 1}
    finally:
        await client.close()
    assert socket.closed is True
    assert client.reconnect_attempts == {}


async def test_simultaneous_device_reconnects_share_one_token_rotation(monkeypatch):
    monkeypatch.setattr(protocol, "RECONNECT_INITIAL_DELAY", 0)
    client, session = await logged_in_client(
        [
            {"token": "reconnected-access", "refreshToken": "rotated-refresh"},
        ]
    )
    sockets = [FakeSocket() for _ in range(4)]
    for socket in sockets:
        session.sockets.put_nowait(socket)
    connections_one, connections_two = [], []
    try:
        await client.subscribe("device-one", Mock(), connections_one.append)
        await client.subscribe("device-two", Mock(), connections_two.append)
        await spin_until(
            lambda: connections_one == [True] and connections_two == [True]
        )
        sockets[0].disconnect()
        sockets[1].disconnect()
        await spin_until(
            lambda: connections_one == [True, False, True]
            and connections_two == [True, False, True]
        )
        assert (
            len(
                [
                    request
                    for request in session.requests
                    if request[1].endswith("/refresh")
                ]
            )
            == 1
        )
        assert len(session.connections) == 4
        assert client.reconnect_attempts == {"device-one": 1, "device-two": 1}
    finally:
        await client.close()
    assert all(socket.closed for socket in sockets)


async def test_rejected_reconnect_credentials_notify_runtime_and_invalidate_auth(
    monkeypatch,
):
    monkeypatch.setattr(protocol, "RECONNECT_INITIAL_DELAY", 0.01)
    client, session = await logged_in_client([FakeResponse(status=401)])
    socket = FakeSocket()
    session.sockets.put_nowait(socket)
    connections, errors = [], []
    client.error_callback = lambda device_id, error: errors.append((device_id, error))
    try:
        await client.subscribe("device-one", Mock(), connections.append)
        await spin_until(lambda: connections == [True])
        socket.disconnect()
        await spin_until(lambda: bool(errors))
        device_id, error = errors[0]
        assert device_id == "device-one"
        assert isinstance(error, AuthenticationError)
        assert error.status == 401
        assert client.authenticated is False
        assert client._token is None
    finally:
        await client.close()


async def test_socket_auth_rejection_attempts_refresh_before_reauthentication(
    monkeypatch,
):
    monkeypatch.setattr(protocol, "RECONNECT_INITIAL_DELAY", 0)
    client, session = await logged_in_client(
        [
            {"token": "recovered-access", "refreshToken": "rotated-refresh"},
        ]
    )
    session.sockets.put_nowait(aiohttp.WSServerHandshakeError(None, (), status=401))
    session.sockets.put_nowait(FakeSocket())
    connections, errors = [], []
    client.error_callback = lambda device_id, error: errors.append((device_id, error))
    try:
        await client.subscribe("device-one", Mock(), connections.append)
        await spin_until(lambda: connections == [True])
        assert errors
        assert all(not isinstance(error, AuthenticationError) for _, error in errors)
        assert errors[0][1].status == 401
        assert client.authenticated is True
        assert client.refresh_token == "rotated-refresh"
    finally:
        await client.close()


async def test_callback_failure_does_not_kill_listener_or_leak_logs(caplog):
    client, session = await logged_in_client()
    socket = FakeSocket()
    session.sockets.put_nowait(socket)
    bad_callback = Mock(side_effect=ValueError("PRIVATE-TOKEN-URL"))
    connections = Mock(side_effect=ValueError("PRIVATE-ACCOUNT"))
    try:
        await client.subscribe("device-one", bad_callback, connections)
        await spin_until(lambda: connections.call_count == 1)
        socket.send({"subject": "shadow-update", "body": {"deviceId": "device-one"}})
        socket.send({"subject": "shadow-update", "body": {"deviceId": "device-one"}})
        await spin_until(lambda: bad_callback.call_count == 2)
        assert "PRIVATE" not in caplog.text
        assert not client._subscriptions["device-one"].task.done()
    finally:
        await client.close()


async def test_unload_cancels_establishment_and_backoff_without_closing_session(
    monkeypatch,
):
    monkeypatch.setattr(protocol, "RECONNECT_INITIAL_DELAY", 300)
    client, session = await logged_in_client()
    session.sockets.put_nowait(aiohttp.ClientConnectionError("PRIVATE-TOKEN-URL"))
    await client.subscribe("device-one", Mock(), Mock())
    await spin_until(lambda: client.last_error is not None)
    assert str(client.last_error) == "connection"
    task = client._subscriptions["device-one"].task
    await asyncio.gather(client.close(), client.close())
    assert task.done()
    assert client.subscription_count == 0
    assert session.closed is False
    with pytest.raises(ConnectionError, match="closed"):
        await client.get_me()
    with pytest.raises(ConnectionError, match="closed"):
        await client.subscribe("device-one", Mock(), Mock())


def test_error_constructor_refuses_untrusted_text():
    for error_type in (ApiError, AuthenticationError, ConnectionError, CommandError):
        error = error_type("PRIVATE-SERVER-RESPONSE", status=9999)
        assert "PRIVATE" not in str(error)
        assert error.status is None


async def test_real_aiohttp_session_protocol_and_owned_socket_teardown(
    aiohttp_server, socket_enabled
):
    """Exercise actual aiohttp request/socket lifetimes against localhost only."""
    messages, connections, calls = [], [], []
    received = asyncio.Event()
    server_socket_closed = asyncio.Event()
    envelope = {
        "subject": "shadow-update",
        "body": {"deviceId": "device-one", "state": {"reported": {"connected": True}}},
    }

    async def refresh(request):
        calls.append((request.method, request.path, await request.json()))
        return web.json_response(TOKENS)

    async def me(request):
        assert request.headers["Authorization"] == TOKENS["token"]
        return web.json_response({"devices": [{"deviceId": "device-one"}]})

    async def details(request):
        return web.json_response(
            {"shadow": {"state": {"reported": {"connected": True}}}}
        )

    async def start(request):
        calls.append((request.method, request.path, None))
        return web.Response(text="Accepted")

    async def websocket(request):
        assert request.query["Authorization"] == TOKENS["token"]
        assert request.query["deviceId"] == "device-one"
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        try:
            await socket.send_json(envelope)
            async for _ in socket:
                pass
        finally:
            server_socket_closed.set()
        return socket

    app = web.Application()
    app.router.add_post("/authentication/refresh", refresh)
    app.router.add_get("/authentication/me", me)
    app.router.add_get("/devices/device-one/details", details)
    app.router.add_put("/bottles/123/start", start)
    app.router.add_get("/ws", websocket)
    server = await aiohttp_server(app)

    def message_received(value):
        messages.append(value)
        received.set()

    async with aiohttp.ClientSession() as session:
        client = FpaClient(session)
        # Only the synthetic server bypasses TLS discovery. Production discovery
        # remains HTTPS/WSS and certificate-verified, covered above.
        client.api_url = str(server.make_url("")).rstrip("/")
        client.websockets_url = str(server.make_url("/ws")).replace(
            "http://", "ws://", 1
        )
        try:
            await client.refresh("synthetic-refresh")
            assert await client.get_me() == {"devices": [{"deviceId": "device-one"}]}
            assert (await client.get_device_details("device-one"))["shadow"]["state"][
                "reported"
            ]["connected"]
            await client.subscribe("device-one", message_received, connections.append)
            async with asyncio.timeout(2):
                await received.wait()
            assert messages == [envelope]
            assert connections == [True]
            assert await client.start_bottle(123) == {}
        finally:
            await client.close()
        assert not session.closed
        async with asyncio.timeout(2):
            await server_socket_closed.wait()
        assert not [
            task for task in asyncio.all_tasks() if task.get_name() == "fpa_websocket"
        ]
    assert calls == [
        ("POST", "/authentication/refresh", {"refreshToken": "synthetic-refresh"}),
        ("PUT", "/bottles/123/start", None),
    ]

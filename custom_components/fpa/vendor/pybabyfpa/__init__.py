"""Controlled Baby Brezza cloud protocol client.

Derived from Jon Caruana's MIT-licensed pybabyfpa 0.0.7. See ORIGIN.md
and LICENSE in this directory. This module deliberately has no HA imports.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import aiohttp

DISCOVERY_URL = "https://info.babybrezzacloud.com"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
WEBSOCKET_CONNECT_TIMEOUT = 30
WEBSOCKET_CLOSE_TIMEOUT = 10
HEARTBEAT_INTERVAL = 600
RECONNECT_INITIAL_DELAY = 1
RECONNECT_MAX_DELAY = 300
MAX_MESSAGE_BYTES = 256 * 1024
_CONTROL_SUBJECTS = frozenset(
    {
        "auth",
        "authenticate",
        "authenticated",
        "authentication",
        "authorize",
        "authorization",
        "ping",
        "pong",
        "heartbeat",
        "keepalive",
        "keep-alive",
        "connect",
        "connected",
        "connection",
        "disconnect",
        "disconnected",
        "subscribe",
        "subscribed",
        "unsubscribe",
        "unsubscribed",
    }
)

# Error text is an allowlist, never a vendor response/URL/exception message.
_ERROR_CATEGORIES = frozenset(
    {
        "api_error",
        "authentication",
        "connection",
        "tls",
        "timeout",
        "http",
        "protocol",
        "command_rejected",
        "closed",
        "token_callback",
    }
)


class ApiError(Exception):
    """A safe error with machine-readable category and optional HTTP status."""

    default_category = "api_error"

    def __init__(self, category: str | None = None, status: int | None = None):
        self.category = (
            category if category in _ERROR_CATEGORIES else self.default_category
        )
        self.status = (
            status if isinstance(status, int) and 100 <= status <= 599 else None
        )
        message = self.category
        if self.status is not None:
            message = f"{message} (HTTP {self.status})"
        super().__init__(message)


class AuthenticationError(ApiError):
    """The cloud explicitly rejected authentication."""

    default_category = "authentication"


class ConnectionError(ApiError):
    """A network, timeout or TLS failure, with no private request details."""

    default_category = "connection"


class CommandError(ApiError):
    """The cloud rejected a command or its acknowledgement was malformed."""

    default_category = "command_rejected"


MessageCallback = Callable[[dict[str, Any]], None]
ConnectionCallback = Callable[[bool], None]
TokenCallback = Callable[[str], None]
ErrorCallback = Callable[[str, ApiError], None]


@dataclass
class _Subscription:
    on_message: MessageCallback
    on_connection: ConnectionCallback
    task: asyncio.Task[None] | None = None
    socket: aiohttp.ClientWebSocketResponse | None = None
    connected: bool = False


class FpaClient:
    """One account and its device subscriptions, using an injected session.

    Reads return independent wire dictionaries. Device normalization, merging,
    preparation policy and command safeguards belong to the integration.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token_callback: TokenCallback | None = None,
    ) -> None:
        self._session = session
        self._token_callback = token_callback
        self._initialize_lock = asyncio.Lock()
        self._auth_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._subscriptions: dict[str, _Subscription] = {}
        self._auth_generation = 0
        self._token: str | None = None
        self.refresh_token: str | None = None
        self.email: str | None = None
        self.account_id: str | None = None
        self.devices: list[dict[str, Any]] = []
        self.api_url: str | None = None
        self.websockets_url: str | None = None
        self.closed = False
        self.last_error: ApiError | None = None
        self.error_callback: ErrorCallback | None = None

    @property
    def authenticated(self) -> bool:
        """Whether account credentials have been established in this runtime."""
        return self._token is not None and not self.closed

    @property
    def subscription_count(self) -> int:
        """Number of owned device listeners, without exposing their identities."""
        return len(self._subscriptions)

    def _check_open(self) -> None:
        if self.closed:
            raise ConnectionError("closed")

    async def _request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        authenticated: bool = False,
        command: bool = False,
    ) -> dict[str, Any]:
        self._check_open()
        headers = (
            {"Authorization": self._token} if authenticated and self._token else {}
        )
        if authenticated and not self._token:
            raise AuthenticationError()
        try:
            async with self._session.request(
                method,
                url,
                json=payload,
                headers=headers,
                timeout=HTTP_TIMEOUT,
                allow_redirects=False,
            ) as response:
                # Do not parse or retain rejected response bodies: server free text
                # and even JSON error fields can contain personal data or secrets.
                if response.status in (401, 403):
                    raise AuthenticationError(status=response.status)
                if response.status != 200:
                    error_type = CommandError if command else ApiError
                    category = (
                        "http"
                        if command
                        and (
                            response.status < 400
                            or response.status == 408
                            or response.status >= 500
                        )
                        else None
                    )
                    raise error_type(category, status=response.status)
                if command:
                    # The existing start endpoint has no documented response
                    # schema. HTTP acceptance is all we can establish here;
                    # activity/completion is observed independently by runtime.
                    return {}
                try:
                    result = await response.json()
                except (ValueError, aiohttp.ContentTypeError):
                    error_type = CommandError if command else ApiError
                    raise error_type("protocol", status=response.status) from None
                if not isinstance(result, dict):
                    error_type = CommandError if command else ApiError
                    raise error_type("protocol", status=response.status)
                return deepcopy(result)
        except asyncio.CancelledError:
            raise
        except ApiError:
            raise
        except (aiohttp.ClientSSLError, aiohttp.ClientConnectorCertificateError):
            raise ConnectionError("tls") from None
        except TimeoutError:
            raise ConnectionError("timeout") from None
        except (aiohttp.ClientError, OSError):
            raise ConnectionError() from None

    async def _initialize(self) -> None:
        self._check_open()
        async with self._initialize_lock:
            if self.api_url is not None and self.websockets_url is not None:
                return
            response = await self._request("GET", DISCOVERY_URL)
            api_host = response.get("api")
            websocket_url = response.get("websockets")
            if not isinstance(api_host, str) or not isinstance(websocket_url, str):
                raise ApiError("protocol")
            # Preserve cloud discovery, while refusing insecure schemes,
            # credentials, query strings or fragments from discovery metadata.
            try:
                api = urlsplit(f"https://{api_host}")
                websocket = urlsplit(websocket_url)
            except ValueError:
                raise ApiError("protocol") from None
            if (
                api.scheme != "https"
                or not api.hostname
                or api.username is not None
                or api.password is not None
                or api.path not in ("", "/")
                or api.query
                or api.fragment
                or websocket.scheme != "wss"
                or not websocket.hostname
                or websocket.username is not None
                or websocket.password is not None
                or websocket.query
                or websocket.fragment
            ):
                raise ApiError("protocol")
            self.api_url = f"https://{api.netloc}"
            self.websockets_url = websocket_url

    def _apply_account(
        self, response: dict[str, Any], *, require_devices: bool
    ) -> None:
        devices = response.get("devices")
        if require_devices and (
            not isinstance(devices, list)
            or any(not isinstance(item, dict) for item in devices)
        ):
            raise ApiError("protocol")
        if isinstance(devices, list) and all(
            isinstance(item, dict) for item in devices
        ):
            self.devices = deepcopy(devices)
        if isinstance(response.get("email"), str):
            self.email = response["email"]
        for key in ("id", "accountId", "userId"):
            value = response.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                self.account_id = str(value)
                break

    def _apply_tokens(self, response: dict[str, Any]) -> None:
        token = response.get("token")
        refresh_token = response.get("refreshToken")
        if (
            not isinstance(token, str)
            or not token
            or not isinstance(refresh_token, str)
            or not refresh_token
        ):
            raise ApiError("protocol")
        changed = refresh_token != self.refresh_token
        self._token = token
        self.refresh_token = refresh_token
        self._auth_generation += 1
        if changed and self._token_callback is not None:
            try:
                self._token_callback(refresh_token)
            except Exception:
                raise ApiError("token_callback") from None

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate once; retain tokens and stable identity, never password."""
        await self._initialize()
        async with self._auth_lock:
            response = await self._request(
                "POST",
                f"{self.api_url}/authentication/login",
                payload={"email": email, "password": password},
            )
            self._apply_account(response, require_devices=False)
            self._apply_tokens(response)
            return deepcopy(response)

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        """Exchange the stored refresh token under the account-wide auth lock."""
        await self._initialize()
        async with self._auth_lock:
            # Another device may have rotated the token while this caller waited.
            return await self._refresh_locked(self.refresh_token or refresh_token)

    async def _refresh_locked(self, refresh_token: str) -> dict[str, Any]:
        try:
            response = await self._request(
                "POST",
                f"{self.api_url}/authentication/refresh",
                payload={"refreshToken": refresh_token},
            )
        except AuthenticationError:
            self._token = None
            raise
        self._apply_tokens(response)
        self._apply_account(response, require_devices=False)
        return deepcopy(response)

    async def _refresh_generation(self, generation: int) -> None:
        async with self._auth_lock:
            if self._auth_generation != generation:
                return
            if not self.refresh_token:
                raise AuthenticationError()
            await self._refresh_locked(self.refresh_token)

    async def _read(self, path: str) -> dict[str, Any]:
        await self._initialize()
        generation = self._auth_generation
        try:
            return await self._request(
                "GET", f"{self.api_url}{path}", authenticated=True
            )
        except AuthenticationError:
            await self._refresh_generation(generation)
            # A read is safe to retry after a definitive authentication rejection.
            return await self._request(
                "GET", f"{self.api_url}{path}", authenticated=True
            )

    async def get_me(self) -> dict[str, Any]:
        """Read account/device identities without replacing active subscriptions."""
        response = await self._read("/authentication/me")
        self._apply_account(response, require_devices=True)
        return deepcopy(response)

    async def get_device_details(self, device_id: str) -> dict[str, Any]:
        """Read the wire snapshot; never merge it into an object behind listeners."""
        return await self._read(f"/devices/{quote(device_id, safe='')}/details")

    async def start_bottle(self, bottle_id: int) -> dict[str, Any]:
        """Send one saved-preset start command, with no automatic replay."""
        if (
            isinstance(bottle_id, bool)
            or not isinstance(bottle_id, int)
            or bottle_id <= 0
        ):
            raise CommandError()
        await self._initialize()
        return await self._request(
            "PUT",
            f"{self.api_url}/bottles/{bottle_id}/start",
            authenticated=True,
            command=True,
        )

    async def subscribe(
        self,
        device_id: str,
        on_message: MessageCallback,
        on_connection: ConnectionCallback,
    ) -> None:
        """Install exactly one listener per device and return without waiting for I/O."""
        self._check_open()
        existing = self._subscriptions.get(device_id)
        if existing is not None:
            existing.on_message = on_message
            existing.on_connection = on_connection
            return
        subscription = _Subscription(on_message, on_connection)
        self._subscriptions[device_id] = subscription
        subscription.task = asyncio.create_task(
            self._listen(device_id, subscription),
            name="fpa_websocket",
        )

    def _connection_changed(self, subscription: _Subscription, connected: bool) -> None:
        if subscription.connected == connected:
            return
        subscription.connected = connected
        if not self.closed:
            try:
                subscription.on_connection(connected)
            except Exception:
                # A consumer failure must not terminate transport/reconnect.
                # Never log callback arguments, raw exceptions or credential URLs.
                return

    def _message_received(
        self, device_id: str, subscription: _Subscription, value: Any
    ) -> None:
        if not isinstance(value, dict) or not isinstance(value.get("subject"), str):
            return
        if value["subject"].casefold().replace("_", "-") in _CONTROL_SUBJECTS:
            return
        body = value.get("body")
        if not isinstance(body, dict):
            return
        identity = body.get("deviceId", body.get("device_id"))
        if identity != device_id or (
            "device_id" in body and body["device_id"] != device_id
        ):
            return
        if not self.closed:
            try:
                subscription.on_message(deepcopy(value))
            except Exception:
                return

    async def _listen(self, device_id: str, subscription: _Subscription) -> None:
        delay = RECONNECT_INITIAL_DELAY
        reconnect = False
        generation = self._auth_generation
        while not self.closed:
            try:
                await self._initialize()
                if reconnect:
                    await self._refresh_generation(generation)
                if not self._token:
                    raise AuthenticationError()
                generation = self._auth_generation
                query = urlencode({"Authorization": self._token, "deviceId": device_id})
                # The credential-bearing URL is used only here, never stored in
                # observations, task names, exceptions, messages or logs.
                async with asyncio.timeout(WEBSOCKET_CONNECT_TIMEOUT):
                    socket = await self._session.ws_connect(
                        f"{self.websockets_url}?{query}",
                        heartbeat=HEARTBEAT_INTERVAL,
                        max_msg_size=MAX_MESSAGE_BYTES,
                    )
                subscription.socket = socket
                self.last_error = None
                self._connection_changed(subscription, True)
                delay = RECONNECT_INITIAL_DELAY
                while not self.closed:
                    message = await socket.receive()
                    if message.type == aiohttp.WSMsgType.TEXT:
                        try:
                            value = json.loads(message.data)
                        except (ValueError, TypeError):
                            continue
                        self._message_received(device_id, subscription, value)
                    elif message.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                        aiohttp.WSMsgType.CLOSING,
                    ):
                        break
            except asyncio.CancelledError:
                raise
            except AuthenticationError as error:
                self._token = None
                self.last_error = error
            except (aiohttp.ClientSSLError, aiohttp.ClientConnectorCertificateError):
                self.last_error = ConnectionError("tls")
            except TimeoutError:
                self.last_error = ConnectionError("timeout")
            except aiohttp.WSServerHandshakeError as error:
                # A socket access token may have expired while refresh credentials
                # remain valid. Reconnect first exchanges the refresh token;
                # only a rejected refresh warrants account reauthentication.
                self.last_error = ConnectionError(status=error.status)
            except ApiError as error:
                self.last_error = error
            except (aiohttp.ClientError, OSError):
                self.last_error = ConnectionError()
            except Exception:
                # Unexpected wire/client shapes must not leave a dead listener.
                self.last_error = ApiError("protocol")
            finally:
                self._connection_changed(subscription, False)
                if (
                    self.last_error is not None
                    and not self.closed
                    and self.error_callback is not None
                ):
                    try:
                        self.error_callback(device_id, self.last_error)
                    except Exception:
                        pass
                socket = subscription.socket
                subscription.socket = None
                if socket is not None:
                    try:
                        async with asyncio.timeout(WEBSOCKET_CLOSE_TIMEOUT):
                            await socket.close()
                    except Exception:
                        # A close failure must not kill this reconnect loop.
                        # Cancellation still propagates (it is BaseException).
                        pass
            if not self.closed:
                reconnect = True
                await asyncio.sleep(delay)
                delay = min(RECONNECT_MAX_DELAY, delay * 2)

    async def close(self) -> None:
        """Cancel and await owned listeners/backoff/heartbeat; preserve HA's session."""
        async with self._close_lock:
            if self.closed:
                return
            self.closed = True
            tasks = [
                item.task
                for item in self._subscriptions.values()
                if item.task is not None
            ]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._subscriptions.clear()


__all__ = [
    "ApiError",
    "AuthenticationError",
    "CommandError",
    "ConnectionError",
    "FpaClient",
]

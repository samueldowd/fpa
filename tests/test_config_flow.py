"""Offline credentials, duplicate-account, reauth, and setup cleanup tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER, ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fpa.api import AuthenticationError, ConnectionError, FpaClient
from custom_components.fpa.config_flow import CannotConnect, InvalidAuth, validate_input


@pytest.fixture
async def flow_client():
    api = MagicMock(spec=FpaClient)
    api.email = "account@example.invalid"
    api.account_id = "test-account-id"
    api.refresh_token = "new-refresh-token"
    api.login = AsyncMock()
    api.get_me = AsyncMock(return_value={"devices": []})
    api.close = AsyncMock()
    with patch("custom_components.fpa.config_flow.FpaClient", return_value=api):
        yield api


async def test_user_form_and_success_only_stores_refresh_token(hass, flow_client):
    with patch("custom_components.fpa.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            "fpa", context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "account@example.invalid", "password": "never-store-this"},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "account@example.invalid"
    assert result["data"] == {"refresh_token": "new-refresh-token"}
    assert result["result"].unique_id == "test-account-id"
    flow_client.close.assert_awaited_once()


@pytest.mark.parametrize(
    "error,key",
    [
        (AuthenticationError(), "invalid_auth"),
        (ConnectionError("tls"), "cannot_connect"),
        (RuntimeError("secret-remote-url"), "unknown"),
    ],
)
async def test_user_errors_are_distinct_and_temporary_clients_close(
    hass, flow_client, caplog, error, key
):
    flow_client.login.side_effect = error
    result = await hass.config_entries.flow.async_init(
        "fpa",
        context={"source": SOURCE_USER},
        data={"email": "account@example.invalid", "password": "never-store-this"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    flow_client.close.assert_awaited_once()
    assert "secret-remote-url" not in caplog.text
    assert "never-store-this" not in caplog.text


@pytest.mark.parametrize("legacy", [False, True])
async def test_duplicate_new_and_legacy_accounts_do_not_recreate(
    hass, flow_client, legacy
):
    entry = MockConfigEntry(
        domain="fpa",
        unique_id=None if legacy else "test-account-id",
        title="account@example.invalid",
        data={"refresh_token": "existing-token"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "fpa",
        context={"source": SOURCE_USER},
        data={"email": "account@example.invalid", "password": "password"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == {"refresh_token": "existing-token"}
    assert entry.unique_id == (None if legacy else "test-account-id")


@pytest.mark.parametrize("legacy", [False, True])
async def test_reauth_updates_existing_entry_preserving_identity_and_title(
    hass, flow_client, legacy
):
    entry = MockConfigEntry(
        domain="fpa",
        unique_id=None if legacy else "test-account-id",
        title="User custom account label",
        data={"refresh_token": "old-token", "preserve": "value"},
    )
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload", return_value=True
    ) as reload:
        result = await hass.config_entries.flow.async_init(
            "fpa",
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "account@example.invalid", "password": "password"},
        )
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {"refresh_token": "new-refresh-token", "preserve": "value"}
    assert entry.title == "User custom account label"
    assert entry.unique_id == (None if legacy else "test-account-id")


async def test_reauth_rejects_established_different_account(hass, flow_client):
    entry = MockConfigEntry(
        domain="fpa",
        unique_id="different-account",
        title="Original account",
        data={"refresh_token": "existing-token"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "fpa",
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": "account@example.invalid", "password": "password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_account_mismatch"
    assert entry.data["refresh_token"] == "existing-token"


async def test_fallback_identity_is_validated_email_never_token(hass, flow_client):
    flow_client.account_id = None
    info = await validate_input(
        hass, {"email": "Account@example.invalid", "password": "password"}
    )
    assert info["identity"] == "account@example.invalid"
    assert info["identity"] != info["refresh_token"]


@pytest.mark.parametrize(
    "error,expected",
    [(AuthenticationError(), InvalidAuth), (ConnectionError("timeout"), CannotConnect)],
)
async def test_identity_fetch_failures_close_temporary_client(
    hass, flow_client, error, expected
):
    flow_client.get_me.side_effect = error
    with pytest.raises(expected):
        await validate_input(
            hass, {"email": "account@example.invalid", "password": "password"}
        )
    flow_client.close.assert_awaited_once()


@pytest.mark.parametrize(
    "error,state",
    [
        (AuthenticationError(), ConfigEntryState.SETUP_ERROR),
        (ConnectionError("tls"), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_entry_setup_auth_vs_connectivity_cleanup(hass, error, state):
    api = MagicMock(spec=FpaClient)
    api.refresh = AsyncMock(side_effect=error)
    api.close = AsyncMock()
    entry = MockConfigEntry(domain="fpa", data={"refresh_token": "old-token"})
    entry.add_to_hass(hass)
    with patch("custom_components.fpa.FpaClient", return_value=api):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is state
    assert entry.runtime_data.closed
    api.close.assert_awaited_once()


async def test_rotated_refresh_token_saved_without_password(hass):
    entry = MockConfigEntry(domain="fpa", data={"refresh_token": "old-token"})
    entry.add_to_hass(hass)
    api = MagicMock(spec=FpaClient)
    api.refresh = AsyncMock()
    api.get_me = AsyncMock(return_value={"devices": []})
    api.close = AsyncMock()

    def factory(session, token_callback):
        token_callback("rotated-token")
        return api

    with patch("custom_components.fpa.FpaClient", side_effect=factory):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.data == {"refresh_token": "rotated-token"}
        assert await hass.config_entries.async_unload(entry.entry_id)
    api.close.assert_awaited_once()

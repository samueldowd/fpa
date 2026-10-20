"""Credential validation and account reauthentication for Formula Pro."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiError, AuthenticationError, FpaClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
STEP_USER_DATA_SCHEMA = vol.Schema(
    {vol.Required("email"): str, vol.Required("password"): str}
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate with a temporary client and retain only the refresh credential."""
    api = FpaClient(async_get_clientsession(hass))
    try:
        await api.login(data["email"], data["password"])
        await api.get_me()
        email = api.email or data["email"].strip()
        identity = (
            str(api.account_id) if api.account_id is not None else email.casefold()
        )
        return {
            "title": email,
            "refresh_token": api.refresh_token,
            "identity": identity,
        }
    except AuthenticationError as err:
        raise InvalidAuth from err
    except ApiError as err:
        raise CannotConnect from err
    finally:
        await api.close()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Keep existing version-one refresh-token entries compatible."""

    VERSION = 1

    async def _async_validate(self, user_input: dict[str, Any], errors: dict[str, str]):
        try:
            return await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception as err:  # An unexpected library error must not expose secrets.
            _LOGGER.error(
                "Unexpected credential validation failure (%s)", type(err).__name__
            )
            errors["base"] = "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Authenticate an account without persisting its password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._async_validate(user_input, errors)
            if info is not None:
                await self.async_set_unique_id(info["identity"])
                self._abort_if_unique_id_configured()
                # Upstream entries had no unique ID; preserve them and recognize
                # their established account title without rewriting their identity.
                if any(
                    entry.unique_id is None
                    and entry.title.casefold() == info["title"].casefold()
                    for entry in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=info["title"], data={"refresh_token": info["refresh_token"]}
                )
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Ask for credentials when a stored refresh token is no longer valid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Replace only the existing entry's credential and reload it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._async_validate(user_input, errors)
            if info is not None:
                entry = self._get_reauth_entry()
                if entry.unique_id is not None and entry.unique_id != info["identity"]:
                    return self.async_abort(reason="reauth_account_mismatch")
                return self.async_update_reload_and_abort(
                    entry, data_updates={"refresh_token": info["refresh_token"]}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """The account service could not be reached."""


class InvalidAuth(HomeAssistantError):
    """The account credentials were rejected."""

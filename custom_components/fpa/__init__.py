"""Formula Pro Advanced WiFi integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiError, AuthenticationError, FpaClient
from .coordinator import FpaRuntime
from .diagnostics import attach_diagnostics

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.BUTTON]
type FpaConfigEntry = ConfigEntry[FpaRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: FpaConfigEntry) -> bool:
    """Authenticate, create account-owned runtime, and forward platforms."""

    def persist_refresh_token(token: str) -> None:
        if token and token != entry.data.get("refresh_token"):
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, "refresh_token": token}
            )

    api = FpaClient(async_get_clientsession(hass), token_callback=persist_refresh_token)
    runtime = FpaRuntime(hass, entry, api)
    attach_diagnostics(runtime)
    entry.runtime_data = runtime
    try:
        await runtime.async_setup()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except AuthenticationError as err:
        await runtime.async_close()
        raise ConfigEntryAuthFailed(
            translation_domain="fpa", translation_key="invalid_auth"
        ) from err
    except ApiError as err:
        await runtime.async_close()
        raise ConfigEntryNotReady(
            translation_domain="fpa", translation_key="cannot_connect"
        ) from err
    except BaseException:
        await runtime.async_close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FpaConfigEntry) -> bool:
    """Unload platforms and close only this entry's tasks and connections."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_close()
    return True

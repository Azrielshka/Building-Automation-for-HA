"""Интеграция «Building Automation» (Оркестратор здания).

Тонкая обвязка жизненного цикла config entry. Вся логика — в пакете `domain`
(чистые функции без `hass`); связывание с Home Assistant — в `adapters` и
`coordinator`. См. SPEC §2.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настроить config entry.

    Каркас этапа 0: платформы и координатор появляются на этапе 1.
    """
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузить config entry."""
    return True

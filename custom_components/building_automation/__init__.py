"""Интеграция «Building Automation» (Оркестратор здания).

Тонкая обвязка жизненного цикла config entry. Вся логика — в пакете `domain`
(чистые функции без `hass`); связывание с Home Assistant — в `adapters` и
`coordinator`. См. SPEC §2.

Импорты Home Assistant здесь — только под `TYPE_CHECKING` или **отложенные внутри
функций**. Причина: пакет `homeassistant` не установлен в среде разработки
(SPEC §2.1), а этот модуль неизбежно загружается при импорте любого подмодуля
`domain` — ядро должно оставаться импортируемым без HA. Обвязочные модули
(`coordinator`, платформы) грузятся отложенно, только когда HA реально вызывает
setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настроить config entry: координатор и платформа sensor (этап 1)."""
    # Отложенные импорты — разрыв зависимости ядра от HA (см. docstring модуля).
    from homeassistant.const import Platform  # noqa: PLC0415

    from .coordinator import BuildingCoordinator  # noqa: PLC0415

    coordinator = BuildingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузить config entry и его платформы."""
    from homeassistant.const import Platform  # noqa: PLC0415

    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])

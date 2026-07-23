"""Платформа sensor: режим расписания здания (SPEC §10, этап 1).

Платформенные модули лежат в корне пакета — Home Assistant загружает их по
имени `<интеграция>/<platform>.py`; подпапки loader не сканирует. Грузится
только в среде HA; ядро её не импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BuildingCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Создать сущности платформы sensor."""
    coordinator: BuildingCoordinator = entry.runtime_data
    async_add_entities([ScheduleModeSensor(coordinator)])


class ScheduleModeSensor(CoordinatorEntity[BuildingCoordinator], SensorEntity):
    """Текущий режим расписания здания (Урок / Перемена / …)."""

    _attr_has_entity_name = True
    _attr_translation_key = "schedule_mode"

    def __init__(self, coordinator: BuildingCoordinator) -> None:
        """Привязать сущность к координатору."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_schedule_mode"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": "Building Automation",
        }

    @property
    def native_value(self) -> str:
        """Значение режима расписания."""
        return self.coordinator.data.mode.value

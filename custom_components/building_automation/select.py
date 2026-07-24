"""Платформа select: режим управления зданием — Авто / Ручной (ТЗ §10).

Здание переключают редко и осознанно — потому `select` с явными метками, а не
тумблер. Грузится только в среде HA; ядро её не импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BuildingCoordinator
from .domain.types import ControlMode

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

_OPTION_AUTO = "auto"
_OPTION_MANUAL = "manual"
_TO_MODE = {_OPTION_AUTO: ControlMode.AUTO, _OPTION_MANUAL: ControlMode.MANUAL}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Создать сущность платформы select."""
    coordinator: BuildingCoordinator = entry.runtime_data
    async_add_entities([BuildingControlSelect(coordinator)])


class BuildingControlSelect(CoordinatorEntity[BuildingCoordinator], SelectEntity):
    """Режим управления зданием: Авто (по расписанию) / Ручной."""

    _attr_has_entity_name = True
    _attr_name = "Режим управления зданием"
    _attr_options: ClassVar[list[str]] = [_OPTION_AUTO, _OPTION_MANUAL]

    def __init__(self, coordinator: BuildingCoordinator) -> None:
        """Привязать сущность к координатору."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_building_control"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": "Оркестратор здания",
        }

    @property
    def current_option(self) -> str:
        """Текущий режим управления зданием."""
        return self.coordinator.data.control.building.value

    async def async_select_option(self, option: str) -> None:
        """Переключить режим управления зданием."""
        await self.coordinator.async_set_building_mode(_TO_MODE[option])

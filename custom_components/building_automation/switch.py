"""Платформа switch: режим управления этажа тумблером (ТЗ §10).

По одному тумблеру на Floor: ON = этаж следует расписанию, OFF = ручной стоп.
Полярность совпадает с legacy `input_boolean.regim_auto_<N>`; сущность работает
кликабельным бейджом на дашборде. Грузится только в среде HA; ядро её не
импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BuildingCoordinator
from .domain.types import FloorControl

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .domain.types import FloorId


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Создать по тумблеру на каждый этаж."""
    coordinator: BuildingCoordinator = entry.runtime_data
    async_add_entities(
        FloorAutomaticSwitch(coordinator, floor_id)
        for floor_id in coordinator.data.topology.floors
    )


class FloorAutomaticSwitch(CoordinatorEntity[BuildingCoordinator], SwitchEntity):
    """Тумблер этажа: ON = следует расписанию, OFF = ручной стоп."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BuildingCoordinator, floor_id: FloorId) -> None:
        """Привязать сущность к координатору и этажу."""
        super().__init__(coordinator)
        self._floor_id = floor_id
        self._attr_name = f"Автоматика · этаж {floor_id}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_floor_{floor_id}_switch"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": "Оркестратор здания",
        }

    @property
    def is_on(self) -> bool:
        """Этаж следует расписанию (ON), если не переведён в ручной стоп."""
        control = self.coordinator.data.control.floors.get(
            self._floor_id, FloorControl.BY_BUILDING
        )
        return control is FloorControl.BY_BUILDING

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Вернуть этаж под расписание."""
        await self.coordinator.async_set_floor_mode(
            self._floor_id, FloorControl.BY_BUILDING
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Перевести этаж в ручной стоп."""
        await self.coordinator.async_set_floor_mode(self._floor_id, FloorControl.MANUAL)

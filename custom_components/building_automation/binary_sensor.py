"""Платформа binary_sensor: доступность источника и гейты по этажам (ТЗ §10, §6).

Гейт этажа — **цель fail-open**: blueprint датчика читает его шаблоном
`{{ states(gate) != 'off' }}`. `on` = датчики разрешены, `off` = запрещены;
отсутствие сущности (выгрузка интеграции) blueprint трактует как «разрешено».
Грузится только в среде HA; ядро её не импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BuildingCoordinator

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
    """Создать сущность доступности источника и по гейту на каждый этаж."""
    coordinator: BuildingCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [SourceAvailableBinarySensor(coordinator)]
    entities.extend(
        FloorGateBinarySensor(coordinator, floor_id)
        for floor_id in coordinator.data.topology.floors
    )
    async_add_entities(entities)


def _device_info(entry_id: str) -> dict[str, Any]:
    """Единое устройство «Оркестратор здания» (ТЗ §10)."""
    return {"identifiers": {(DOMAIN, entry_id)}, "name": "Оркестратор здания"}


class SourceAvailableBinarySensor(
    CoordinatorEntity[BuildingCoordinator], BinarySensorEntity
):
    """Доступность источника расписания (ON = источник доступен)."""

    _attr_has_entity_name = True
    _attr_name = "Источник расписания доступен"

    def __init__(self, coordinator: BuildingCoordinator) -> None:
        """Привязать сущность к координатору."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_source_available"
        self._attr_device_info = _device_info(coordinator.entry.entry_id)

    @property
    def is_on(self) -> bool:
        """Источник расписания доступен."""
        return self.coordinator.data.source_available


class FloorGateBinarySensor(CoordinatorEntity[BuildingCoordinator], BinarySensorEntity):
    """Гейт этажа: ON = датчики движения разрешены (§6)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BuildingCoordinator, floor_id: FloorId) -> None:
        """Привязать сущность к координатору и этажу."""
        super().__init__(coordinator)
        self._floor_id = floor_id
        self._attr_name = f"Датчики разрешены · этаж {floor_id}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_floor_{floor_id}_gate"
        self._attr_device_info = _device_info(coordinator.entry.entry_id)

    @property
    def is_on(self) -> bool:
        """Датчики движения на этаже разрешены (гейт открыт)."""
        return self.coordinator.gate_for(self._floor_id)

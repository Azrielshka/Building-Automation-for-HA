"""Платформа sensor: режим расписания, отложенный переход, применённый режим.

Платформенные модули лежат в корне пакета — Home Assistant загружает их по
имени `<интеграция>/<platform>.py`; подпапки loader не сканирует. Грузится
только в среде HA; ядро её не импортирует. Все сущности читают состояние из
координатора (`CoordinatorEntity`); источник истины — состояние, не события
(ТЗ §10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_APPLY_AT, DOMAIN
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
    """Создать сущности платформы sensor."""
    coordinator: BuildingCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        ScheduleModeSensor(coordinator),
        PendingTransitionSensor(coordinator),
    ]
    entities.extend(
        FloorAppliedModeSensor(coordinator, floor_id)
        for floor_id in coordinator.data.topology.floors
    )
    async_add_entities(entities)


def _device_info(entry_id: str) -> dict[str, Any]:
    """Единое устройство «Оркестратор здания» для всех сущностей (ТЗ §10)."""
    return {
        "identifiers": {(DOMAIN, entry_id)},
        "name": "Оркестратор здания",
    }


class ScheduleModeSensor(CoordinatorEntity[BuildingCoordinator], SensorEntity):
    """Текущий режим расписания здания (Урок / Перемена / …)."""

    _attr_has_entity_name = True
    _attr_name = "Режим расписания"

    def __init__(self, coordinator: BuildingCoordinator) -> None:
        """Привязать сущность к координатору."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_schedule_mode"
        self._attr_device_info = _device_info(coordinator.entry.entry_id)

    @property
    def native_value(self) -> str:
        """Значение режима расписания."""
        return self.coordinator.data.schedule_mode.value


class PendingTransitionSensor(CoordinatorEntity[BuildingCoordinator], SensorEntity):
    """Отложенный переход: целевой режим и момент применения (атрибут)."""

    _attr_has_entity_name = True
    _attr_name = "Отложенный переход"

    def __init__(self, coordinator: BuildingCoordinator) -> None:
        """Привязать сущность к координатору."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_pending"
        self._attr_device_info = _device_info(coordinator.entry.entry_id)

    @property
    def native_value(self) -> str:
        """Целевой режим отложенного перехода или `idle`, если его нет."""
        pending = self.coordinator.data.pending
        return pending.target_mode.value if pending is not None else "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Момент применения отложенного перехода (монотонное время)."""
        pending = self.coordinator.data.pending
        return {ATTR_APPLY_AT: pending.apply_at if pending is not None else None}


class FloorAppliedModeSensor(CoordinatorEntity[BuildingCoordinator], SensorEntity):
    """Применённый режим на этаже (общий по зданию режим применения)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BuildingCoordinator, floor_id: FloorId) -> None:
        """Привязать сущность к координатору и этажу."""
        super().__init__(coordinator)
        self._floor_id = floor_id
        self._attr_name = f"Применённый режим · этаж {floor_id}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_floor_{floor_id}_applied"
        self._attr_device_info = _device_info(coordinator.entry.entry_id)

    @property
    def native_value(self) -> str:
        """Применённый режим или `none`, если ещё ничего не применено."""
        applied = self.coordinator.data.applied_mode
        return applied.value if applied is not None else "none"

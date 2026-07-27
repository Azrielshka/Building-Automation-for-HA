"""Адаптер реестров HA → снимок топологии ядра (SPEC §2.3, этап 2).

Собирает `TopologySnapshot` из Floor/Area/Entity/Device реестров:
- агрегатная Area этажа — по метке `ba_floor_area` (§3.2 ТЗ);
- тип помещения — по метке `ba_type_<RoomType>`;
- opt-out — по метке `ba_optout`;
- статус инварианта — по числу световых сущностей Area с учётом
  device-наследования (сервисный вызов по area_id разворачивается и в них).

Грузится только в среде HA; ядро его не импортирует.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    floor_registry as fr,
)

from ..const import LABEL_FLOOR_AREA, LABEL_TYPE_PREFIX
from ..domain.topology import TopologySnapshot, evaluate_area
from ..domain.types import Floor, Room, RoomType

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.core import HomeAssistant


def _room_type(labels: Iterable[str]) -> RoomType | None:
    """Определить тип помещения по метке `ba_type_*`; неизвестный → None."""
    for label in labels:
        if label.startswith(LABEL_TYPE_PREFIX):
            value = label.removeprefix(LABEL_TYPE_PREFIX)
            try:
                return RoomType(value)
            except ValueError:
                return None
    return None


def _lights_by_area(hass: HomeAssistant) -> dict[str, list[str]]:
    """Световые сущности каждой Area с учётом device-наследования."""
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    result: dict[str, list[str]] = defaultdict(list)
    for entity in entities.entities.values():
        if entity.domain != "light":
            continue
        area_id = entity.area_id
        if area_id is None and entity.device_id is not None:
            device = devices.async_get(entity.device_id)
            area_id = device.area_id if device is not None else None
        if area_id is not None:
            result[area_id].append(entity.entity_id)
    return result


def build_topology_snapshot(hass: HomeAssistant) -> TopologySnapshot:
    """Построить снимок топологии из реестров HA."""
    areas = ar.async_get(hass)
    floors_reg = fr.async_get(hass)
    lights = _lights_by_area(hass)

    aggregate_by_floor: dict[str, str] = {}
    rooms: dict[str, Room] = {}
    for area in areas.async_list_areas():
        if area.floor_id is None:
            continue  # Area вне периметра здания
        if LABEL_FLOOR_AREA in area.labels:
            aggregate_by_floor[area.floor_id] = area.id
            continue
        rooms[area.id] = Room(
            area_id=area.id,
            floor_id=area.floor_id,
            room_type=_room_type(area.labels),
            # opt-out — политика Оркестратора из .storage (Q3=C), не метка реестра;
            # накладывается координатором через topology.apply_opt_out.
            opt_out=False,
            status=evaluate_area(lights.get(area.id, [])),
        )

    floors = {
        floor.floor_id: Floor(
            floor_id=floor.floor_id,
            aggregate_area_id=aggregate_by_floor.get(floor.floor_id),
        )
        for floor in floors_reg.async_list_floors()
    }
    return TopologySnapshot(floors=floors, rooms=rooms)

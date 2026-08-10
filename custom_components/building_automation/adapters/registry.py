"""Адаптер реестров HA → снимок топологии ядра (SPEC §2.3, этап 2).

Собирает `TopologySnapshot` из Floor/Area/Entity/Device реестров:
- агрегатная Area этажа — по метке `ba_floor_area` (§3.2 ТЗ);
- тип помещения — по метке `ba_type_<RoomType>`;
- opt-out — НЕ метка: политика Оркестратора в `.storage` (Q3=C), накладывается
  координатором через `topology.apply_opt_out`;
- групповой свет Area и статус инварианта (этап 12) — по световым сущностям с
  меткой `ba_area_light`: ровно одна → `OK` + её `entity_id` в `light_entity_id`,
  0 → `NO_LIGHT`, ≥2 → `MULTIPLE_LIGHTS`. Прочий свет в Area игнорируется, поэтому
  в Area можно держать любые светильники.

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

from ..const import LABEL_AREA_LIGHT, LABEL_FLOOR_AREA, LABEL_TYPE_PREFIX
from ..domain.topology import TopologySnapshot, evaluate_area
from ..domain.types import AreaStatus, Floor, Room, RoomType

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


def _area_lights_by_area(hass: HomeAssistant) -> dict[str, list[str]]:
    """Помеченные `ba_area_light` световые сущности каждой Area (этап 12).

    Метка — на сущности; Area берётся у сущности или наследуется от устройства.
    Непомеченный свет игнорируется — его можно держать в Area для других нужд.
    """
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    result: dict[str, list[str]] = defaultdict(list)
    for entity in entities.entities.values():
        if entity.domain != "light" or LABEL_AREA_LIGHT not in entity.labels:
            continue
        area_id = entity.area_id
        if area_id is None and entity.device_id is not None:
            device = devices.async_get(entity.device_id)
            area_id = device.area_id if device is not None else None
        if area_id is not None:
            result[area_id].append(entity.entity_id)
    return result


def _light_of(labeled: list[str], status: AreaStatus) -> str | None:
    """Единственный помеченный свет Area, если инвариант соблюдён (`OK`)."""
    return labeled[0] if status is AreaStatus.OK else None


def build_topology_snapshot(hass: HomeAssistant) -> TopologySnapshot:
    """Построить снимок топологии из реестров HA."""
    areas = ar.async_get(hass)
    floors_reg = fr.async_get(hass)
    area_lights = _area_lights_by_area(hass)

    aggregate_by_floor: dict[str, str] = {}
    aggregate_light_by_floor: dict[str, str | None] = {}
    rooms: dict[str, Room] = {}
    for area in areas.async_list_areas():
        if area.floor_id is None:
            continue  # Area вне периметра здания
        labeled = area_lights.get(area.id, [])
        if LABEL_FLOOR_AREA in area.labels:
            aggregate_by_floor[area.floor_id] = area.id
            aggregate_light_by_floor[area.floor_id] = _light_of(
                labeled, evaluate_area(labeled)
            )
            continue
        status = evaluate_area(labeled)
        rooms[area.id] = Room(
            area_id=area.id,
            floor_id=area.floor_id,
            room_type=_room_type(area.labels),
            # opt-out — политика Оркестратора из .storage (Q3=C), не метка реестра;
            # накладывается координатором через topology.apply_opt_out.
            opt_out=False,
            status=status,
            light_entity_id=_light_of(labeled, status),
        )

    floors = {
        floor.floor_id: Floor(
            floor_id=floor.floor_id,
            aggregate_area_id=aggregate_by_floor.get(floor.floor_id),
            light_entity_id=aggregate_light_by_floor.get(floor.floor_id),
        )
        for floor in floors_reg.async_list_floors()
    }
    return TopologySnapshot(floors=floors, rooms=rooms)

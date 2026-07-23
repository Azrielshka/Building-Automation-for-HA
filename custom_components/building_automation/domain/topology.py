"""Снимок топологии и проверка инварианта Area (SPEC §2.2.2, §3 ТЗ)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .types import AreaId, AreaStatus, Floor, FloorId, Room


@dataclass(frozen=True)
class TopologySnapshot:
    """Неизменяемый снимок топологии из реестра HA (SPEC §2.2.2).

    Агрегатные Area этажей хранятся в `Floor.aggregate_area_id` и в `rooms` не
    входят — `rooms` содержит только помещения.
    """

    floors: Mapping[FloorId, Floor]
    rooms: Mapping[AreaId, Room]

    def rooms_of(self, floor: FloorId) -> Sequence[Room]:
        """Помещения этажа (без агрегатной Area)."""
        return [room for room in self.rooms.values() if room.floor_id == floor]

    def aggregate_area_of(self, floor: FloorId) -> AreaId | None:
        """Агрегатная Area этажа, если задана."""
        known = self.floors.get(floor)
        return known.aggregate_area_id if known is not None else None


def evaluate_area(light_entities: Sequence[str]) -> AreaStatus:
    """Проверить инвариант «в Area ровно одна световая сущность».

    Вход — световые сущности (домен `light`), уже отобранные для Area.
    """
    if len(light_entities) == 1:
        return AreaStatus.OK
    if not light_entities:
        return AreaStatus.NO_LIGHT
    return AreaStatus.MULTIPLE_LIGHTS

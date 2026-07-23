"""Разрешение эффективного профиля с наследованием (SPEC §2.2.3, §5.1 ТЗ).

Для каждого помещения вычисляет набор действий по приоритету источников:
помещение → тип помещения → этаж → объект. Первый заданный уровень побеждает.
"""

from __future__ import annotations

from collections.abc import Mapping

from .topology import TopologySnapshot
from .types import ActionSet, AreaId, Config, Room, ScheduleMode


def _effective(config: Config, room: Room, mode: ScheduleMode) -> ActionSet:
    """Набор действий по приоритету: помещение → тип → этаж."""
    area_key = (room.area_id, mode)
    if area_key in config.actions_by_area:
        return config.actions_by_area[area_key]
    if room.room_type is not None:
        type_key = (room.room_type, mode)
        if type_key in config.actions_by_room_type:
            return config.actions_by_room_type[type_key]
    floor_key = (room.floor_id, mode)
    if floor_key in config.actions_by_floor:
        return config.actions_by_floor[floor_key]
    return config.actions_object.get(mode, ())


def resolve_actions(
    config: Config,
    topology: TopologySnapshot,
    mode: ScheduleMode,
) -> Mapping[AreaId, ActionSet]:
    """Эффективный набор действий для каждого помещения в снимке."""
    return {
        area_id: _effective(config, room, mode)
        for area_id, room in topology.rooms.items()
    }

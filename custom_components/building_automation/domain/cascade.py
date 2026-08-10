"""Планировщик каскада: схлопывание и пропуски (SPEC §2.2.4, §5.3 ТЗ).

Разворачивает эффективные наборы действий помещений в команды, выбирая самый
высокий однородный уровень (агрегатная Area этажа против отдельных помещений).

Два потока:
- **свет** (`light`/`switch`) целится по **конкретной световой сущности** (этап
  12): помеченный `ba_area_light` свет помещения (`Room.light_entity_id`), а при
  однородном этаже схлопывается в свет агрегатной Area (`Floor.light_entity_id`).
  Одно и то же световое действие не уходит на свет агрегата и свет помещения разом;
- **автояркость** (`is_room_pinned`, этап 11) адресует датчики помещения по
  `area_id` — сервис сам отбирает датчики. Агрегатной цели у неё нет: всегда по
  Area помещения. В однородности света не участвует и может соседствовать с
  командой света на агрегат (разные устройства, двойного воздействия нет).
"""

import json
from collections.abc import Iterable, Mapping
from typing import cast

from .topology import TopologySnapshot
from .types import (
    ActionSet,
    AreaId,
    AreaStatus,
    CascadePlan,
    Command,
    ControlMode,
    ControlState,
    FloorControl,
    Room,
    SkipEntry,
    SkipReason,
    TargetKind,
    is_room_pinned,
)


def _homogeneity_key(actions: ActionSet) -> str:
    """Каноничный ключ однородности набора (SPEC §4.1).

    `Action.data` может содержать списки (например `rgb_color`) и нехешируем,
    поэтому однородность определяется JSON-представлением, а не хешем.
    """
    return json.dumps(
        [[action.domain, action.service, action.data] for action in actions],
        sort_keys=True,
        ensure_ascii=False,
    )


def _skip_reason(room: Room, control: ControlState) -> SkipReason | None:
    """Причина пропуска помещения в фиксированном порядке (SPEC §2.2.4).

    ORPHANED здесь не проверяется — сирота это area из конфигурации, которой нет
    в снимке топологии; такие помещения в обход не попадают.
    """
    if control.building is ControlMode.MANUAL:
        return SkipReason.BUILDING_MANUAL
    if control.floors.get(room.floor_id) is FloorControl.MANUAL:
        return SkipReason.FLOOR_MANUAL
    if room.opt_out:
        return SkipReason.OPT_OUT
    if room.status is not AreaStatus.OK:
        return SkipReason.INVARIANT_BROKEN
    return None


def plan_cascade(
    topology: TopologySnapshot,
    actions: Mapping[AreaId, ActionSet],
    control: ControlState,
    orphaned_area_ids: Iterable[AreaId] = (),
) -> CascadePlan:
    """Построить план каскада из снимка топологии и наборов действий.

    `orphaned_area_ids` — area из конфигурации, отсутствующие в снимке
    (осиротевшие профили, §3.7 ТЗ); их вычисляет вызывающий и они попадают в
    отчёт с причиной ORPHANED.
    """
    commands: list[Command] = []
    skipped: list[SkipEntry] = [
        SkipEntry(area_id=area_id, reason=SkipReason.ORPHANED)
        for area_id in orphaned_area_ids
    ]
    for floor_id, floor in topology.floors.items():
        rooms = topology.rooms_of(floor_id)
        active: list[Room] = []
        for room in rooms:
            reason = _skip_reason(room, control)
            if reason is not None:
                skipped.append(SkipEntry(area_id=room.area_id, reason=reason))
            else:
                active.append(room)
        if not active:
            continue
        # Поток автояркости: всегда по Area помещения (сервис сам отбирает датчики).
        commands.extend(
            Command(
                target=room.area_id, target_kind=TargetKind.AREA, action=action
            )
            for room in active
            for action in actions.get(room.area_id, ())
            if is_room_pinned(action)
        )
        # Поток света: набор без действий-автояркости — он и решает однородность.
        # Цель — конкретная световая сущность (этап 12), а не area_id.
        collapsible: dict[AreaId, ActionSet] = {
            room.area_id: tuple(
                action
                for action in actions.get(room.area_id, ())
                if not is_room_pinned(action)
            )
            for room in active
        }
        keys = {_homogeneity_key(collapsible[room.area_id]) for room in active}
        # Схлопывание в свет агрегатной Area — только если ни одно помещение этажа
        # не пропущено, набор света однороден (SPEC §4.1) и у этажа есть помеченный
        # свет агрегата. Любой пропуск/разнородность/отсутствие света → по помещениям.
        if (
            len(active) == len(rooms)
            and len(keys) == 1
            and floor.light_entity_id is not None
        ):
            floor_light = floor.light_entity_id  # локал: сужение к str для genexpr
            commands.extend(
                Command(
                    target=floor_light, target_kind=TargetKind.ENTITY, action=action
                )
                for action in collapsible[active[0].area_id]
            )
        else:
            commands.extend(
                Command(
                    # active ⟹ status OK ⟹ light_entity_id задан (инвариант адаптера)
                    target=cast(str, room.light_entity_id),
                    target_kind=TargetKind.ENTITY,
                    action=action,
                )
                for room in active
                for action in collapsible[room.area_id]
            )
    return CascadePlan(commands=tuple(commands), skipped=tuple(skipped))

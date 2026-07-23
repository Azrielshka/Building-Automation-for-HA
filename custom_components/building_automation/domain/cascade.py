"""Планировщик каскада: схлопывание и пропуски (SPEC §2.2.4, §5.3 ТЗ).

Разворачивает эффективные наборы действий помещений в команды, выбирая самый
высокий однородный уровень (агрегатная Area этажа против отдельных помещений) и
не отправляя команду родительской и дочерней Area одновременно.
"""

import json
from collections.abc import Iterable, Mapping

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
    for floor_id in topology.floors:
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
        keys = {_homogeneity_key(actions.get(room.area_id, ())) for room in active}
        aggregate = topology.aggregate_area_of(floor_id)
        # Агрегатная — только если ни одно помещение этажа не пропущено и набор
        # однороден (SPEC §4.1). Любой пропуск разворачивает этаж до помещений.
        if len(active) == len(rooms) and len(keys) == 1 and aggregate is not None:
            commands.extend(
                Command(target_area_id=aggregate, action=action)
                for action in actions.get(active[0].area_id, ())
            )
        else:
            commands.extend(
                Command(target_area_id=room.area_id, action=action)
                for room in active
                for action in actions.get(room.area_id, ())
            )
    return CascadePlan(commands=tuple(commands), skipped=tuple(skipped))

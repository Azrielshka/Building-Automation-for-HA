"""Тесты планировщика каскада: схлопывание, пропуски, инвариант (SPEC §5.4).

Этап 12: цель светового потока — конкретная световая сущность
(`Room.light_entity_id`; при схлопывании — `Floor.light_entity_id`); автояркость
(room-pinned) — по `area_id`.
"""

from __future__ import annotations

import time

from custom_components.building_automation.domain.cascade import plan_cascade
from custom_components.building_automation.domain.topology import TopologySnapshot
from custom_components.building_automation.domain.types import (
    Action,
    AreaStatus,
    ControlMode,
    ControlState,
    Floor,
    FloorControl,
    Room,
    SkipReason,
    TargetKind,
    is_room_pinned,
)

_ACTION = Action("light", "turn_off")
_AUTO_OFF = Action("arvid_dali_center", "set_autobrightness", {"enabled": False})
_AUTO_ON = Action("arvid_dali_center", "set_autobrightness", {"enabled": True})
_AUTO = ControlState(building=ControlMode.AUTO, floors={})


def _by_target(plan) -> dict:
    """Действия по цели команды (для проверки двух потоков)."""
    result: dict = {}
    for cmd in plan.commands:
        result.setdefault(cmd.target, []).append(cmd.action)
    return result


def _floor_snapshot() -> TopologySnapshot:
    """Этаж f1: свет агрегата light.af1, два помещения со своим светом."""
    return TopologySnapshot(
        floors={
            "f1": Floor(
                floor_id="f1", aggregate_area_id="af1", light_entity_id="light.af1"
            )
        },
        rooms={
            "a1": Room(area_id="a1", floor_id="f1", light_entity_id="light.a1"),
            "a2": Room(area_id="a2", floor_id="f1", light_entity_id="light.a2"),
        },
    )


def _snapshot_with(a1: Room, a2: Room) -> TopologySnapshot:
    return TopologySnapshot(
        floors={
            "f1": Floor(
                floor_id="f1", aggregate_area_id="af1", light_entity_id="light.af1"
            )
        },
        rooms={a1.area_id: a1, a2.area_id: a2},
    )


def _reasons(plan) -> dict:
    return {s.area_id: s.reason for s in plan.skipped}


# --- Схлопывание светового потока по сущности ---


def test_homogeneous_floor_collapses_to_aggregate_light() -> None:
    """Однородный этаж → одна команда на свет агрегатной Area (сущность)."""
    actions = {"a1": (_ACTION,), "a2": (_ACTION,)}
    plan = plan_cascade(_floor_snapshot(), actions, _AUTO)
    assert {c.target for c in plan.commands} == {"light.af1"}
    assert len(plan.commands) == 1
    assert plan.commands[0].action == _ACTION
    assert plan.commands[0].target_kind is TargetKind.ENTITY


def test_override_expands_to_room_lights() -> None:
    """Разные наборы → команды по свету помещений, не на свет агрегата."""
    other = Action("light", "turn_on", {"brightness_pct": 100})
    actions = {"a1": (_ACTION,), "a2": (other,)}
    plan = plan_cascade(_floor_snapshot(), actions, _AUTO)
    targets = {c.target for c in plan.commands}
    assert targets == {"light.a1", "light.a2"}
    assert "light.af1" not in targets


def test_floor_without_aggregate_light_expands_to_rooms() -> None:
    """Однородный этаж без света агрегата → разворот до света помещений."""
    snapshot = TopologySnapshot(
        floors={"f1": Floor(floor_id="f1", aggregate_area_id="af1")},  # light=None
        rooms={
            "a1": Room(area_id="a1", floor_id="f1", light_entity_id="light.a1"),
            "a2": Room(area_id="a2", floor_id="f1", light_entity_id="light.a2"),
        },
    )
    plan = plan_cascade(snapshot, {"a1": (_ACTION,), "a2": (_ACTION,)}, _AUTO)
    assert {c.target for c in plan.commands} == {"light.a1", "light.a2"}


# --- Пропуски ---


def test_building_manual_skips_all() -> None:
    """Ручной режим здания — все помещения пропущены, команд нет."""
    control = ControlState(building=ControlMode.MANUAL, floors={})
    plan = plan_cascade(
        _floor_snapshot(), {"a1": (_ACTION,), "a2": (_ACTION,)}, control
    )
    assert plan.commands == ()
    assert set(_reasons(plan).values()) == {SkipReason.BUILDING_MANUAL}


def test_floor_manual_skips_floor() -> None:
    """Ручной режим этажа пропускает все его помещения."""
    control = ControlState(
        building=ControlMode.AUTO, floors={"f1": FloorControl.MANUAL}
    )
    plan = plan_cascade(
        _floor_snapshot(), {"a1": (_ACTION,), "a2": (_ACTION,)}, control
    )
    assert plan.commands == ()
    assert set(_reasons(plan).values()) == {SkipReason.FLOOR_MANUAL}


def test_opt_out_skips_and_expands_floor() -> None:
    """Помещение с opt-out пропущено; этаж разворачивается до света помещений."""
    a1 = Room(area_id="a1", floor_id="f1", opt_out=True, light_entity_id="light.a1")
    a2 = Room(area_id="a2", floor_id="f1", light_entity_id="light.a2")
    plan = plan_cascade(
        _snapshot_with(a1, a2), {"a1": (_ACTION,), "a2": (_ACTION,)}, _AUTO
    )
    assert _reasons(plan) == {"a1": SkipReason.OPT_OUT}
    assert {c.target for c in plan.commands} == {"light.a2"}  # не свет агрегата


def test_invariant_broken_skips_room() -> None:
    """Помещение с нарушенным инвариантом (нет помеченного света) пропущено."""
    a1 = Room(area_id="a1", floor_id="f1", status=AreaStatus.MULTIPLE_LIGHTS)
    a2 = Room(area_id="a2", floor_id="f1", light_entity_id="light.a2")
    plan = plan_cascade(
        _snapshot_with(a1, a2), {"a1": (_ACTION,), "a2": (_ACTION,)}, _AUTO
    )
    assert _reasons(plan) == {"a1": SkipReason.INVARIANT_BROKEN}
    assert {c.target for c in plan.commands} == {"light.a2"}


def test_opt_out_takes_priority_over_invariant() -> None:
    """opt-out проверяется раньше инварианта (§2.2.4)."""
    a1 = Room(area_id="a1", floor_id="f1", opt_out=True, status=AreaStatus.NO_LIGHT)
    a2 = Room(area_id="a2", floor_id="f1", light_entity_id="light.a2")
    plan = plan_cascade(
        _snapshot_with(a1, a2), {"a1": (_ACTION,), "a2": (_ACTION,)}, _AUTO
    )
    assert _reasons(plan)["a1"] is SkipReason.OPT_OUT


def test_orphaned_profiles_reported() -> None:
    """Осиротевшие профили попадают в отчёт с причиной ORPHANED."""
    plan = plan_cascade(
        _floor_snapshot(),
        {"a1": (_ACTION,), "a2": (_ACTION,)},
        _AUTO,
        orphaned_area_ids=["ghost1", "ghost2"],
    )
    reasons = _reasons(plan)
    assert reasons["ghost1"] is SkipReason.ORPHANED
    assert reasons["ghost2"] is SkipReason.ORPHANED


# --- Инвариант плана и краевые случаи ---


def test_plan_invariant_no_parent_and_child_light_together() -> None:
    """Свет не уходит на свет агрегата и свет помещения этажа разом."""
    a1 = Room(area_id="a1", floor_id="f1", light_entity_id="light.a1")
    a2 = Room(area_id="a2", floor_id="f1", light_entity_id="light.a2")
    snapshot = _snapshot_with(a1, a2)
    other = Action("light", "turn_on", {"brightness_pct": 50})
    scenarios = [
        {"a1": (_ACTION,), "a2": (_ACTION,)},  # однородно → свет агрегата
        {"a1": (_ACTION,), "a2": (other,)},  # разнородно → свет помещений
        {"a1": (), "a2": (_ACTION,)},  # частично пусто
        {"a1": (_ACTION,)},  # a2 без набора
    ]
    room_lights = {"light.a1", "light.a2"}
    for actions in scenarios:
        plan = plan_cascade(snapshot, actions, _AUTO)
        targets = {c.target for c in plan.commands}
        parent_used = "light.af1" in targets
        child_used = bool(targets & room_lights)
        assert not (parent_used and child_used), (actions, targets)


def test_plan_performance_50_rooms() -> None:
    """Планирование на 50 помещений укладывается в 5 мс (SPEC §6)."""
    floors = {
        f"f{f}": Floor(
            floor_id=f"f{f}", aggregate_area_id=f"af{f}", light_entity_id=f"light.af{f}"
        )
        for f in range(5)
    }
    rooms = {}
    actions = {}
    for f in range(5):
        for r in range(10):
            aid = f"a_{f}_{r}"
            rooms[aid] = Room(
                area_id=aid, floor_id=f"f{f}", light_entity_id=f"light.{aid}"
            )
            actions[aid] = (Action("light", "turn_off", {"n": r % 3}),)
    snapshot = TopologySnapshot(floors=floors, rooms=rooms)
    start = time.perf_counter()
    plan_cascade(snapshot, actions, _AUTO)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.005, f"{elapsed * 1000:.2f} мс"


def test_collapse_ignores_data_key_order() -> None:
    """Однородность не зависит от порядка ключей data (sort_keys)."""
    a = Action("light", "turn_on", {"brightness_pct": 100, "transition": 2})
    b = Action("light", "turn_on", {"transition": 2, "brightness_pct": 100})
    plan = plan_cascade(_floor_snapshot(), {"a1": (a,), "a2": (b,)}, _AUTO)
    assert {c.target for c in plan.commands} == {"light.af1"}


def test_break_would_skip_later_floor() -> None:
    """Пустой этаж не прерывает обработку последующих (continue, не break)."""
    floors = {
        "f_empty": Floor(
            floor_id="f_empty", aggregate_area_id="afe", light_entity_id="light.afe"
        ),
        "f1": Floor(
            floor_id="f1", aggregate_area_id="af1", light_entity_id="light.af1"
        ),
    }
    rooms = {  # помещения только у f1; f_empty идёт первым
        "a1": Room(area_id="a1", floor_id="f1", light_entity_id="light.a1"),
        "a2": Room(area_id="a2", floor_id="f1", light_entity_id="light.a2"),
    }
    snapshot = TopologySnapshot(floors=floors, rooms=rooms)
    plan = plan_cascade(snapshot, {"a1": (_ACTION,), "a2": (_ACTION,)}, _AUTO)
    assert {c.target for c in plan.commands} == {"light.af1"}


def test_all_empty_sets_collapse_no_commands() -> None:
    """Однородно пустые наборы → ветка агрегата без команд, без падения."""
    plan = plan_cascade(_floor_snapshot(), {}, _AUTO)
    assert plan.commands == ()


def test_expanded_commands_carry_their_actions() -> None:
    """При развороте каждая команда несёт действие своего помещения."""
    other = Action("light", "turn_on", {"brightness_pct": 100})
    plan = plan_cascade(_floor_snapshot(), {"a1": (_ACTION,), "a2": (other,)}, _AUTO)
    by_target = {c.target: c.action for c in plan.commands}
    assert by_target == {"light.a1": _ACTION, "light.a2": other}


# --- Двухпоточный каскад: автояркость по area, свет по сущности ---


def test_autobrightness_never_collapses_to_aggregate() -> None:
    """Свет — на свет агрегата, автояркость — по Area помещений того же этажа."""
    actions = {"a1": (_ACTION, _AUTO_OFF), "a2": (_ACTION, _AUTO_OFF)}
    by_target = _by_target(plan_cascade(_floor_snapshot(), actions, _AUTO))
    assert by_target["light.af1"] == [_ACTION]  # свет — одной командой на агрегат
    assert by_target["a1"] == [_AUTO_OFF]  # автояркость — по Area помещения
    assert by_target["a2"] == [_AUTO_OFF]


def test_autobrightness_only_no_light_command() -> None:
    """Профиль лишь из автояркости → команды по Area помещений, света нет."""
    actions = {"a1": (_AUTO_OFF,), "a2": (_AUTO_OFF,)}
    targets = {
        c.target for c in plan_cascade(_floor_snapshot(), actions, _AUTO).commands
    }
    assert targets == {"a1", "a2"}
    assert "light.af1" not in targets


def test_collapse_uses_light_only_ignoring_autobrightness() -> None:
    """Однородность света не зависит от различий автояркости между помещениями."""
    actions = {"a1": (_ACTION, _AUTO_ON), "a2": (_ACTION, _AUTO_OFF)}
    by_target = _by_target(plan_cascade(_floor_snapshot(), actions, _AUTO))
    assert by_target["light.af1"] == [_ACTION]  # свет всё равно схлопнулся
    assert by_target["a1"] == [_AUTO_ON]
    assert by_target["a2"] == [_AUTO_OFF]


def test_autobrightness_expands_with_light_when_room_skipped() -> None:
    """Пропуск помещения разворачивает свет; автояркость и так по Area."""
    a1 = Room(area_id="a1", floor_id="f1", opt_out=True, light_entity_id="light.a1")
    a2 = Room(area_id="a2", floor_id="f1", light_entity_id="light.a2")
    plan = plan_cascade(
        _snapshot_with(a1, a2),
        {"a1": (_ACTION, _AUTO_OFF), "a2": (_ACTION, _AUTO_OFF)},
        _AUTO,
    )
    assert _reasons(plan) == {"a1": SkipReason.OPT_OUT}
    by_target = _by_target(plan)
    assert set(by_target) == {"light.a2", "a2"}  # свет и автояркость a2, агрегата нет
    assert by_target["light.a2"] == [_ACTION]
    assert by_target["a2"] == [_AUTO_OFF]


def test_target_kinds_split_light_and_autobrightness() -> None:
    """Свет — ENTITY по свету агрегата; автояркость — AREA по area_id."""
    actions = {"a1": (_ACTION, _AUTO_OFF), "a2": (_ACTION, _AUTO_OFF)}
    plan = plan_cascade(_floor_snapshot(), actions, _AUTO)
    light = {c.target for c in plan.commands if c.target_kind is TargetKind.ENTITY}
    area = {c.target for c in plan.commands if c.target_kind is TargetKind.AREA}
    assert light == {"light.af1"}
    assert area == {"a1", "a2"}
    assert all(
        is_room_pinned(c.action)
        for c in plan.commands
        if c.target_kind is TargetKind.AREA
    )

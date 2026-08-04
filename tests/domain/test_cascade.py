"""Тесты планировщика каскада: схлопывание, пропуски, инвариант (SPEC §5.4)."""

from __future__ import annotations

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
    is_room_pinned,
)

_ACTION = Action("light", "turn_off")
_AUTO_OFF = Action("arvid_dali_center", "set_autobrightness", {"enabled": False})
_AUTO_ON = Action("arvid_dali_center", "set_autobrightness", {"enabled": True})
_AUTO = ControlState(building=ControlMode.AUTO, floors={})


def _by_target(plan) -> dict:
    """Действия по целевой Area (для проверки двух потоков каскада)."""
    result: dict = {}
    for cmd in plan.commands:
        result.setdefault(cmd.target_area_id, []).append(cmd.action)
    return result


def _floor_snapshot() -> TopologySnapshot:
    """Этаж f1 с агрегатной Area af1 и двумя помещениями a1, a2."""
    return TopologySnapshot(
        floors={"f1": Floor(floor_id="f1", aggregate_area_id="af1")},
        rooms={
            "a1": Room(area_id="a1", floor_id="f1"),
            "a2": Room(area_id="a2", floor_id="f1"),
        },
    )


def test_homogeneous_floor_collapses_to_aggregate() -> None:
    """Все помещения этажа с одинаковым набором → одна команда на агрегатную."""
    actions = {"a1": (_ACTION,), "a2": (_ACTION,)}
    plan = plan_cascade(_floor_snapshot(), actions, _AUTO)
    targets = {cmd.target_area_id for cmd in plan.commands}
    assert targets == {"af1"}
    assert len(plan.commands) == 1
    assert plan.commands[0].action == _ACTION


def test_override_expands_to_rooms() -> None:
    """Разные наборы у помещений → команды по помещениям, не на агрегатную."""
    other = Action("light", "turn_on", {"brightness_pct": 100})
    actions = {"a1": (_ACTION,), "a2": (other,)}
    plan = plan_cascade(_floor_snapshot(), actions, _AUTO)
    targets = {cmd.target_area_id for cmd in plan.commands}
    assert targets == {"a1", "a2"}
    assert "af1" not in targets


def _reasons(plan) -> dict:
    return {s.area_id: s.reason for s in plan.skipped}


def test_building_manual_skips_all() -> None:
    """Ручной режим здания — все помещения пропущены, команд нет."""
    actions = {"a1": (_ACTION,), "a2": (_ACTION,)}
    control = ControlState(building=ControlMode.MANUAL, floors={})
    plan = plan_cascade(_floor_snapshot(), actions, control)
    assert plan.commands == ()
    assert _reasons(plan) == {
        "a1": SkipReason.BUILDING_MANUAL,
        "a2": SkipReason.BUILDING_MANUAL,
    }


def _snapshot_with(a1: Room, a2: Room) -> TopologySnapshot:
    return TopologySnapshot(
        floors={"f1": Floor(floor_id="f1", aggregate_area_id="af1")},
        rooms={a1.area_id: a1, a2.area_id: a2},
    )


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
    """Помещение с opt-out пропущено; этаж разворачивается до помещений."""
    a1 = Room(area_id="a1", floor_id="f1", opt_out=True)
    a2 = Room(area_id="a2", floor_id="f1")
    plan = plan_cascade(
        _snapshot_with(a1, a2), {"a1": (_ACTION,), "a2": (_ACTION,)}, _AUTO
    )
    assert _reasons(plan) == {"a1": SkipReason.OPT_OUT}
    targets = {c.target_area_id for c in plan.commands}
    assert targets == {"a2"}  # не агрегатная af1


def test_invariant_broken_skips_room() -> None:
    """Помещение с нарушенным инвариантом пропущено, остальные обработаны."""
    a1 = Room(area_id="a1", floor_id="f1", status=AreaStatus.MULTIPLE_LIGHTS)
    a2 = Room(area_id="a2", floor_id="f1")
    plan = plan_cascade(
        _snapshot_with(a1, a2), {"a1": (_ACTION,), "a2": (_ACTION,)}, _AUTO
    )
    assert _reasons(plan) == {"a1": SkipReason.INVARIANT_BROKEN}
    assert {c.target_area_id for c in plan.commands} == {"a2"}


def test_opt_out_takes_priority_over_invariant() -> None:
    """opt-out проверяется раньше инварианта (§2.2.4)."""
    a1 = Room(area_id="a1", floor_id="f1", opt_out=True, status=AreaStatus.NO_LIGHT)
    a2 = Room(area_id="a2", floor_id="f1")
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


import time  # noqa: E402


def _floor_ids(topology) -> set:
    return set(topology.floors)


def test_plan_invariant_no_parent_and_child_together() -> None:
    """Инвариант плана: цели не содержат агрегатную этажа и его помещение разом."""
    a1 = Room(area_id="a1", floor_id="f1")
    a2 = Room(area_id="a2", floor_id="f1")
    snapshot = _snapshot_with(a1, a2)
    other = Action("light", "turn_on", {"brightness_pct": 50})
    scenarios = [
        {"a1": (_ACTION,), "a2": (_ACTION,)},  # однородно → агрегатная
        {"a1": (_ACTION,), "a2": (other,)},  # разнородно → помещения
        {"a1": (), "a2": (_ACTION,)},  # частично пусто
        {"a1": (_ACTION,)},  # a2 без набора
    ]
    for actions in scenarios:
        plan = plan_cascade(snapshot, actions, _AUTO)
        targets = {c.target_area_id for c in plan.commands}
        aggregate = snapshot.aggregate_area_of("f1")
        rooms = {r.area_id for r in snapshot.rooms_of("f1")}
        parent_used = aggregate in targets
        child_used = bool(targets & rooms)
        assert not (parent_used and child_used), (actions, targets)


def test_plan_performance_50_rooms() -> None:
    """Планирование на 50 помещений укладывается в 5 мс (SPEC §6)."""
    floors = {
        f"f{f}": Floor(floor_id=f"f{f}", aggregate_area_id=f"af{f}") for f in range(5)
    }
    rooms = {}
    actions = {}
    for f in range(5):
        for r in range(10):
            aid = f"a_{f}_{r}"
            rooms[aid] = Room(area_id=aid, floor_id=f"f{f}")
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
    assert {c.target_area_id for c in plan.commands} == {"af1"}


def test_break_would_skip_later_floor() -> None:
    """Пустой этаж не прерывает обработку последующих (continue, не break)."""
    floors = {
        "f_empty": Floor(floor_id="f_empty", aggregate_area_id="afe"),
        "f1": Floor(floor_id="f1", aggregate_area_id="af1"),
    }
    rooms = {  # помещения только у f1; f_empty идёт первым
        "a1": Room(area_id="a1", floor_id="f1"),
        "a2": Room(area_id="a2", floor_id="f1"),
    }
    snapshot = TopologySnapshot(floors=floors, rooms=rooms)
    plan = plan_cascade(snapshot, {"a1": (_ACTION,), "a2": (_ACTION,)}, _AUTO)
    assert {c.target_area_id for c in plan.commands} == {"af1"}


def test_all_empty_sets_collapse_no_commands() -> None:
    """Однородно пустые наборы → агрегатная ветка без команд, без падения."""
    plan = plan_cascade(_floor_snapshot(), {}, _AUTO)
    assert plan.commands == ()


def test_expanded_commands_carry_their_actions() -> None:
    """При развороте каждая команда несёт действие своего помещения."""
    other = Action("light", "turn_on", {"brightness_pct": 100})
    plan = plan_cascade(_floor_snapshot(), {"a1": (_ACTION,), "a2": (other,)}, _AUTO)
    by_target = {c.target_area_id: c.action for c in plan.commands}
    assert by_target == {"a1": _ACTION, "a2": other}


# --- Двухпоточный каскад: автояркость не схлопывается (этап 11) ---


def test_autobrightness_never_collapses_to_aggregate() -> None:
    """Свет схлопывается в агрегатную, автояркость — по помещениям того же этажа."""
    actions = {"a1": (_ACTION, _AUTO_OFF), "a2": (_ACTION, _AUTO_OFF)}
    by_target = _by_target(plan_cascade(_floor_snapshot(), actions, _AUTO))
    assert by_target["af1"] == [_ACTION]  # свет — одной командой на агрегатную
    assert by_target["a1"] == [_AUTO_OFF]  # автояркость — по помещению
    assert by_target["a2"] == [_AUTO_OFF]


def test_autobrightness_only_no_aggregate_command() -> None:
    """Профиль лишь из автояркости → команды по помещениям, агрегатной нет."""
    actions = {"a1": (_AUTO_OFF,), "a2": (_AUTO_OFF,)}
    plan = plan_cascade(_floor_snapshot(), actions, _AUTO)
    targets = {c.target_area_id for c in plan.commands}
    assert targets == {"a1", "a2"}
    assert "af1" not in targets


def test_collapse_uses_light_only_ignoring_autobrightness() -> None:
    """Однородность света не зависит от различий автояркости между помещениями."""
    actions = {"a1": (_ACTION, _AUTO_ON), "a2": (_ACTION, _AUTO_OFF)}
    by_target = _by_target(plan_cascade(_floor_snapshot(), actions, _AUTO))
    assert by_target["af1"] == [_ACTION]  # свет всё равно схлопнулся
    assert by_target["a1"] == [_AUTO_ON]  # автояркость — своя у каждого
    assert by_target["a2"] == [_AUTO_OFF]


def test_autobrightness_expands_with_light_when_room_skipped() -> None:
    """Пропуск помещения разворачивает свет; автояркость и так по помещениям."""
    a1 = Room(area_id="a1", floor_id="f1", opt_out=True)
    a2 = Room(area_id="a2", floor_id="f1")
    plan = plan_cascade(
        _snapshot_with(a1, a2),
        {"a1": (_ACTION, _AUTO_OFF), "a2": (_ACTION, _AUTO_OFF)},
        _AUTO,
    )
    assert _reasons(plan) == {"a1": SkipReason.OPT_OUT}
    by_target = _by_target(plan)
    assert set(by_target) == {"a2"}  # a1 пропущено целиком, агрегатной нет
    assert _ACTION in by_target["a2"]
    assert _AUTO_OFF in by_target["a2"]


def test_light_stream_invariant_holds_with_autobrightness() -> None:
    """Инвариант: свет — единая цель; автояркость — только помещения."""
    actions = {"a1": (_ACTION, _AUTO_OFF), "a2": (_ACTION, _AUTO_OFF)}
    plan = plan_cascade(_floor_snapshot(), actions, _AUTO)
    light_targets = {c.target_area_id for c in plan.commands if c.action == _ACTION}
    auto_targets = {c.target_area_id for c in plan.commands if is_room_pinned(c.action)}
    assert light_targets == {"af1"}  # свет — единая цель
    assert auto_targets == {"a1", "a2"}  # автояркость — только помещения
    assert "af1" not in auto_targets

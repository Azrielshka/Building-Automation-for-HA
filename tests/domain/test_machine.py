"""Тесты машины состояний decide (SPEC §5.5, domain/machine.py)."""

from __future__ import annotations

from custom_components.building_automation.domain.machine import decide
from custom_components.building_automation.domain.topology import TopologySnapshot
from custom_components.building_automation.domain.types import (
    Action,
    Config,
    ControlMode,
    ControlModeChanged,
    ControlState,
    EventSource,
    Floor,
    FloorControl,
    ModeChanged,
    ModeSettings,
    ModeWarning,
    NoTimerOp,
    OrchestratorState,
    PendingTransition,
    Room,
    ScheduleChanged,
    ScheduleMode,
    ScheduleResolution,
    SetTimer,
    Started,
    TimerFired,
    TransitionCancelled,
)

_LESSON = ScheduleMode.LESSON
_OFF = ScheduleMode.OFF
_ACTION = Action("light", "turn_off")


def _topology() -> TopologySnapshot:
    return TopologySnapshot(
        floors={"f1": Floor(floor_id="f1", aggregate_area_id="af1")},
        rooms={
            "a1": Room(area_id="a1", floor_id="f1"),
            "a2": Room(area_id="a2", floor_id="f1"),
        },
    )


_BREAK = ScheduleMode.BREAK


def _config(lesson_delay: int = 0, break_delay: int = 0) -> Config:
    return Config(
        modes={
            _LESSON: ModeSettings(delay_seconds=lesson_delay, sensors_allowed=True),
            _BREAK: ModeSettings(delay_seconds=break_delay, sensors_allowed=False),
            _OFF: ModeSettings(delay_seconds=0, sensors_allowed=True),
        },
        actions_object={},
        actions_by_floor={
            ("f1", _LESSON): (_ACTION,),
            ("f1", _BREAK): (Action("light", "turn_on"),),
        },
        actions_by_room_type={},
        actions_by_area={},
        fallback_mode=_OFF,
    )


def _state(**overrides: object) -> OrchestratorState:
    base: dict[str, object] = {
        "config": _config(),
        "topology": _topology(),
        "control": ControlState(building=ControlMode.AUTO, floors={}),
        "schedule_mode": _OFF,
        "source_available": True,
        "applied_mode": _OFF,
        "pending": None,
    }
    base.update(overrides)
    return OrchestratorState(**base)  # type: ignore[arg-type]


def test_schedule_change_no_delay_applies_immediately() -> None:
    """Смена режима без задержки: план применяется сразу, событие смены."""
    inp = ScheduleChanged(ScheduleResolution(_LESSON, source_available=True))
    decision = decide(_state(), inp, now=100.0)
    assert decision.state.applied_mode is _LESSON
    assert decision.plan is not None
    # план строится для применённого режима: команды несут действие lesson
    assert decision.plan.commands
    assert all(c.action == _ACTION for c in decision.plan.commands)
    assert isinstance(decision.timer_op, NoTimerOp)
    assert decision.events == (ModeChanged(_LESSON, _OFF, EventSource.SCHEDULE),)


def test_schedule_change_with_delay_defers() -> None:
    """Смена с задержкой: SetTimer + предупреждение, каскад не применяется."""
    state = _state(config=_config(lesson_delay=300))
    inp = ScheduleChanged(ScheduleResolution(_LESSON, source_available=True))
    decision = decide(state, inp, now=100.0)
    assert decision.plan is None
    assert isinstance(decision.timer_op, SetTimer)
    assert decision.timer_op.apply_at == 400.0
    assert decision.timer_op.target_mode is _LESSON
    assert any(
        isinstance(e, ModeWarning) and e.target_mode is _LESSON for e in decision.events
    )
    assert decision.state.applied_mode is _OFF  # ещё не применён
    assert decision.state.pending == PendingTransition(_LESSON, 400.0)


def test_timer_fired_applies_pending() -> None:
    """Срабатывание таймера применяет отложенный режим."""

    state = _state(
        config=_config(lesson_delay=300),
        pending=PendingTransition(_LESSON, 400.0),
        applied_mode=_OFF,
    )
    decision = decide(state, TimerFired(), now=400.0)
    assert decision.state.applied_mode is _LESSON
    assert decision.plan is not None
    assert all(c.action == _ACTION for c in decision.plan.commands)
    assert decision.state.pending is None
    assert decision.events == (ModeChanged(_LESSON, _OFF, EventSource.SCHEDULE),)
    assert isinstance(decision.timer_op, NoTimerOp)
    assert decision.gates["f1"] is True  # lesson sensors_allowed


def test_new_change_during_delay_cancels_previous() -> None:
    """Новая смена во время задержки: отмена прежнего + новый таймер."""

    state = _state(
        config=_config(lesson_delay=300, break_delay=300),
        pending=PendingTransition(_LESSON, 400.0),
        applied_mode=_OFF,
    )
    inp = ScheduleChanged(ScheduleResolution(_BREAK, source_available=True))
    decision = decide(state, inp, now=200.0)
    assert isinstance(decision.timer_op, SetTimer)
    assert decision.timer_op.target_mode is _BREAK
    assert decision.state.pending == PendingTransition(_BREAK, 500.0)
    assert any(
        isinstance(e, TransitionCancelled) and e.cancelled_mode is _LESSON
        for e in decision.events
    )


def _started(mode: ScheduleMode):

    return Started(ScheduleResolution(mode, source_available=True))


def test_start_with_divergence_applies_without_delay() -> None:
    """Старт при расхождении: применить актуальный режим без задержки."""
    state = _state(config=_config(lesson_delay=300), applied_mode=_OFF)
    decision = decide(state, _started(_LESSON), now=100.0)
    assert decision.state.applied_mode is _LESSON
    assert decision.state.schedule_mode is _LESSON
    assert decision.plan is not None
    assert all(c.action == _ACTION for c in decision.plan.commands)
    assert decision.events == (ModeChanged(_LESSON, _OFF, EventSource.SCHEDULE),)
    assert isinstance(decision.timer_op, NoTimerOp)


def test_start_with_match_applies_nothing() -> None:
    """Старт при совпадении: состояние восстановлено, действий нет."""
    state = _state(applied_mode=_LESSON)
    decision = decide(state, _started(_LESSON), now=100.0)
    assert decision.plan is None
    assert decision.state.applied_mode is _LESSON


def test_start_does_not_restore_pending() -> None:
    """Незавершённая задержка не восстанавливается после старта (§8.2)."""
    state = _state(pending=PendingTransition(_BREAK, 400.0), applied_mode=_LESSON)
    decision = decide(state, _started(_LESSON), now=100.0)
    assert decision.state.pending is None
    assert decision.plan is None  # режим совпал, pending отброшен


def _sched(mode: ScheduleMode) -> ScheduleChanged:
    return ScheduleChanged(ScheduleResolution(mode, source_available=True))


def test_gate_reflects_mode_sensors_allowed() -> None:
    """Гейт этажа = флаг sensors_allowed применённого режима."""
    on = decide(_state(), _sched(_LESSON), now=100.0)  # lesson: True
    assert on.gates["f1"] is True
    off = decide(_state(), _sched(_BREAK), now=100.0)  # break: False
    assert off.gates["f1"] is False


def test_gate_floor_override() -> None:
    """Переопределение sensors_allowed_by_floor перекрывает флаг режима."""
    config = Config(
        modes={
            _LESSON: ModeSettings(
                delay_seconds=0,
                sensors_allowed=True,
                sensors_allowed_by_floor={"f1": False},
            ),
            _OFF: ModeSettings(delay_seconds=0, sensors_allowed=True),
        },
        actions_object={},
        actions_by_floor={},
        actions_by_room_type={},
        actions_by_area={},
        fallback_mode=_OFF,
    )
    decision = decide(_state(config=config), _sched(_LESSON), now=100.0)
    assert decision.gates["f1"] is False  # переопределение этажа


def test_schedule_change_in_manual_computes_not_applies() -> None:
    """В Ручном режиме здания расписание вычисляется, но не применяется."""
    state = _state(
        control=ControlState(building=ControlMode.MANUAL, floors={}),
        applied_mode=_OFF,
    )
    decision = decide(state, _sched(_LESSON), now=100.0)
    assert decision.state.schedule_mode is _LESSON  # вычислен
    assert decision.state.applied_mode is _OFF  # не применён
    assert decision.plan is None
    assert decision.events == ()
    assert all(not g for g in decision.gates.values())  # гейты закрыты


def test_building_manual_event_closes_gates_no_plan() -> None:
    """Событие «здание в Ручной» закрывает гейты, каскад не применяется."""

    state = _state(applied_mode=_LESSON)
    decision = decide(state, ControlModeChanged(building=ControlMode.MANUAL), now=1.0)
    assert decision.state.control.building is ControlMode.MANUAL
    assert decision.plan is None
    assert decision.events == ()
    assert all(not g for g in decision.gates.values())


def test_floor_return_to_auto_applies_current_schedule() -> None:
    """Возврат этажа в авто применяет ТЕКУЩИЙ режим расписания без задержки.

    Если за время ручного расписание уехало (schedule_mode ≠ applied_mode),
    возврат должен догнать расписание, а не восстановить устаревший applied.
    """

    state = _state(
        control=ControlState(
            building=ControlMode.AUTO, floors={"f1": FloorControl.MANUAL}
        ),
        schedule_mode=_LESSON,  # расписание уехало за время ручного этажа
        applied_mode=_OFF,  # устаревший применённый режим
    )
    decision = decide(
        state,
        ControlModeChanged(floor_id="f1", floor_control=FloorControl.BY_BUILDING),
        now=1.0,
    )
    assert decision.state.applied_mode is _LESSON  # догнал расписание
    assert decision.plan is not None
    assert all(c.action == _ACTION for c in decision.plan.commands)  # действия lesson
    assert decision.gates["f1"] is True  # датчики разрешены (lesson)
    assert decision.state.control.floors["f1"] is FloorControl.BY_BUILDING
    assert isinstance(decision.timer_op, NoTimerOp)


def test_building_return_to_auto_applies_current_schedule() -> None:
    """Возврат здания в авто применяет текущий режим расписания сразу."""

    state = _state(
        control=ControlState(building=ControlMode.MANUAL, floors={}),
        schedule_mode=_LESSON,  # расписание уехало за время ручного
        applied_mode=_OFF,  # устаревший применённый режим
    )
    decision = decide(state, ControlModeChanged(building=ControlMode.AUTO), now=1.0)
    assert decision.state.applied_mode is _LESSON  # догнал расписание
    assert decision.plan is not None
    assert all(c.action == _ACTION for c in decision.plan.commands)
    assert all(decision.gates.values())  # гейты открыты (lesson sensors_allowed)
    assert isinstance(decision.timer_op, NoTimerOp)


def test_floor_manual_does_not_affect_other_floors() -> None:
    """Ручной этаж закрывает свой гейт, не трогая другие."""

    two_floors = TopologySnapshot(
        floors={
            "f1": Floor(floor_id="f1", aggregate_area_id="af1"),
            "f2": Floor(floor_id="f2", aggregate_area_id="af2"),
        },
        rooms={
            "a1": Room(area_id="a1", floor_id="f1"),
            "a2": Room(area_id="a2", floor_id="f2"),
        },
    )
    state = _state(
        topology=two_floors,
        control=ControlState(
            building=ControlMode.AUTO, floors={"f1": FloorControl.MANUAL}
        ),
        applied_mode=_LESSON,
    )
    gates = decide(state, _sched(_LESSON), now=1.0).gates
    assert gates["f1"] is False  # ручной
    assert gates["f2"] is True  # не затронут


def test_decide_is_deterministic() -> None:
    """Повторный decide на тех же данных даёт тот же результат."""
    state = _state()
    inp = _sched(_LESSON)
    assert decide(state, inp, now=100.0) == decide(state, inp, now=100.0)


def test_gate_closed_when_nothing_applied() -> None:
    """Пока режим не применён (applied_mode=None), гейт этажа закрыт."""
    # Авто + задержка: applied_mode остаётся None до применения → гейт False.
    state = _state(config=_config(lesson_delay=300), applied_mode=None)
    decision = decide(state, _sched(_LESSON), now=100.0)
    assert decision.gates["f1"] is False


def test_gate_closed_when_mode_unconfigured() -> None:
    """Гейт закрыт, если применённый режим отсутствует в конфигурации."""
    config = Config(
        modes={_OFF: ModeSettings(delay_seconds=0, sensors_allowed=True)},
        actions_object={},
        actions_by_floor={},
        actions_by_room_type={},
        actions_by_area={},
        fallback_mode=_OFF,
    )
    # Расписание = WINDOW (нет в modes). Возврат в авто применяет schedule_mode
    # WINDOW → settings None → gate False.
    state = _state(config=config, schedule_mode=ScheduleMode.WINDOW, applied_mode=_OFF)
    decision = decide(state, ControlModeChanged(building=ControlMode.AUTO), now=1.0)
    assert decision.state.applied_mode is ScheduleMode.WINDOW
    assert decision.gates["f1"] is False


def test_timer_fired_without_pending_is_noop() -> None:
    """Срабатывание таймера без отложенного перехода — без действий."""
    state = _state(pending=None)
    decision = decide(state, TimerFired(), now=1.0)
    assert decision.plan is None
    assert decision.state == state
    assert decision.events == ()
    assert isinstance(decision.timer_op, NoTimerOp)


def test_unconfigured_mode_has_zero_delay() -> None:
    """Режим без настроек применяется немедленно (задержка 0)."""
    config = Config(
        modes={},  # ни один режим не настроен
        actions_object={_LESSON: (_ACTION,)},
        actions_by_floor={},
        actions_by_room_type={},
        actions_by_area={},
        fallback_mode=_OFF,
    )
    decision = decide(_state(config=config), _sched(_LESSON), now=100.0)
    assert decision.plan is not None  # применён немедленно, не отложен
    assert isinstance(decision.timer_op, NoTimerOp)

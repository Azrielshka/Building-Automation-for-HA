"""Машина состояний: единственная точка политики «что делать сейчас» (SPEC §2.2.5).

`decide` — чистая функция: снимок состояния + вход + время → новое состояние и
описание того, что исполнить (план каскада, операция с таймером, события,
значения гейтов). Ничего не выполняет.
"""

from __future__ import annotations

from dataclasses import replace

from .cascade import plan_cascade
from .profiles import resolve_actions
from .types import (
    CancelTimer,
    CascadePlan,
    ControlMode,
    ControlModeChanged,
    Decision,
    DomainEvent,
    EventSource,
    FloorControl,
    FloorId,
    Input,
    Instant,
    ModeChanged,
    ModeWarning,
    NoTimerOp,
    OrchestratorState,
    PendingTransition,
    ScheduleMode,
    SetTimer,
    Started,
    TimerFired,
    TransitionCancelled,
)


def _build_plan(state: OrchestratorState, mode: ScheduleMode) -> CascadePlan:
    """Построить план каскада для режима из снимков состояния."""
    actions = resolve_actions(state.config, state.topology, mode)
    return plan_cascade(state.topology, actions, state.control)


def _gate_for_floor(state: OrchestratorState, floor_id: FloorId) -> bool:
    """Разрешены ли датчики на этаже (значение гейта, SPEC §6, §4.1 ТЗ).

    Ручной режим здания или этажа закрывает гейт. Иначе — флаг режима с учётом
    переопределения на этаже.
    """
    if state.control.building is ControlMode.MANUAL:
        return False
    if state.control.floors.get(floor_id) is FloorControl.MANUAL:
        return False
    if state.applied_mode is None:
        return False
    settings = state.config.modes.get(state.applied_mode)
    if settings is None:
        return False
    override = settings.sensors_allowed_by_floor.get(floor_id)
    return override if override is not None else settings.sensors_allowed


def _gates(state: OrchestratorState) -> dict[FloorId, bool]:
    """Значения гейтов по всем этажам снимка."""
    return {fid: _gate_for_floor(state, fid) for fid in state.topology.floors}


def _delay_of(state: OrchestratorState, mode: ScheduleMode) -> int:
    """Задержка перехода в режим (0, если режим не настроен)."""
    settings = state.config.modes.get(mode)
    return settings.delay_seconds if settings is not None else 0


def _on_timer(state: OrchestratorState, now: Instant) -> Decision:
    """Применить отложенный переход по срабатыванию таймера."""
    if state.pending is None:
        return Decision(state, None, NoTimerOp(), (), _gates(state))
    mode = state.pending.target_mode
    applied = replace(state, applied_mode=mode, pending=None)
    return Decision(
        state=applied,
        plan=_build_plan(state, mode),
        timer_op=NoTimerOp(),
        events=(ModeChanged(mode, state.applied_mode, EventSource.SCHEDULE),),
        gates=_gates(applied),
    )


def _on_start(state: OrchestratorState, inp: Started) -> Decision:
    """Сверить сохранённый режим с вычисленным на старте (TZ §8.1).

    Незавершённый отложенный переход не восстанавливается (TZ §8.2): `pending`
    сбрасывается. Совпал режим — только восстановление; разошёлся — применение
    без задержки.
    """
    computed = inp.resolution.mode
    base = replace(
        state,
        schedule_mode=computed,
        source_available=inp.resolution.source_available,
        pending=None,
    )
    if computed == state.applied_mode:
        return Decision(base, None, NoTimerOp(), (), _gates(base))
    applied = replace(base, applied_mode=computed)
    return Decision(
        state=applied,
        plan=_build_plan(state, computed),
        timer_op=NoTimerOp(),
        events=(ModeChanged(computed, state.applied_mode, EventSource.SCHEDULE),),
        gates=_gates(applied),
    )


def _on_control(state: OrchestratorState, inp: ControlModeChanged) -> Decision:
    """Переключить режим управления; возврат в авто применяет режим без задержки."""
    control = state.control
    if inp.building is not None:
        control = replace(control, building=inp.building)
    if inp.floor_id is not None and inp.floor_control is not None:
        control = replace(
            control, floors={**control.floors, inp.floor_id: inp.floor_control}
        )
    new_state = replace(state, control=control)

    going_manual = (
        inp.building is ControlMode.MANUAL or inp.floor_control is FloorControl.MANUAL
    )
    if going_manual:
        return Decision(new_state, None, NoTimerOp(), (), _gates(new_state))

    # Возврат в авто — догнать ТЕКУЩЕЕ расписание немедленно, без задержки (§4.1):
    # «Авто» означает следовать расписанию. Если за время ручного режим уехал,
    # применяем schedule_mode, а не устаревший applied_mode.
    mode = state.schedule_mode
    applied = replace(new_state, applied_mode=mode)
    return Decision(
        applied, _build_plan(applied, mode), NoTimerOp(), (), _gates(applied)
    )


def decide(state: OrchestratorState, inp: Input, now: Instant) -> Decision:
    """Вычислить решение по текущему состоянию и входу."""
    if isinstance(inp, TimerFired):
        return _on_timer(state, now)
    if isinstance(inp, Started):
        return _on_start(state, inp)
    if isinstance(inp, ControlModeChanged):
        return _on_control(state, inp)
    new_mode = inp.resolution.mode
    base_state = replace(
        state,
        schedule_mode=new_mode,
        source_available=inp.resolution.source_available,
    )

    # В Ручном режиме здания расписание вычисляется, но не применяется (§3.2 ТЗ).
    if state.control.building is ControlMode.MANUAL:
        return Decision(base_state, None, NoTimerOp(), (), _gates(base_state))

    delay = _delay_of(state, new_mode)

    # Новая смена во время отсчёта отменяет прежний отложенный переход (§4.3).
    cancel: tuple[DomainEvent, ...] = ()
    if state.pending is not None:
        cancel = (TransitionCancelled(state.pending.target_mode),)

    if delay > 0:
        apply_at = now + delay
        return Decision(
            state=replace(base_state, pending=PendingTransition(new_mode, apply_at)),
            plan=None,
            timer_op=SetTimer(apply_at, new_mode),
            events=(*cancel, ModeWarning(new_mode, apply_at)),
            gates=_gates(base_state),
        )

    applied = replace(base_state, applied_mode=new_mode, pending=None)
    return Decision(
        state=applied,
        plan=_build_plan(state, new_mode),
        timer_op=CancelTimer() if state.pending is not None else NoTimerOp(),
        events=(
            *cancel,
            ModeChanged(new_mode, state.applied_mode, EventSource.SCHEDULE),
        ),
        gates=_gates(applied),
    )

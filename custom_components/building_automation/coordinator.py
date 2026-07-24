"""Координатор: связывает снимки HA с ядром и исполняет решения (SPEC §2.3, §2.4).

Оболочка. Держит текущее состояние Оркестратора (`OrchestratorState`), собирает
снимки через адаптеры, прогоняет чистую `decide` и исполняет её решение:
сервисные вызовы (executor), таймер отложенного перехода (timers), события на
шину (publisher). Сущности читают состояние как `CoordinatorEntity`.

Один цикл — `_dispatch(inp)`: снимок топологии (лениво пересобирается по
изменению реестра) → `decide` → исполнение → рассылка сущностям. Диспетчеризация
сериализована локом: перекрывающиеся события не гонятся за состоянием.

Грузится только в среде HA; ядро её не импортирует.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from homeassistant.core import callback
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
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .adapters.executor import execute_plan
from .adapters.publisher import publish_events
from .adapters.registry import build_topology_snapshot
from .adapters.schedule import read_schedule_events
from .adapters.store import ConfigStore
from .adapters.timers import DelayedTransitionTimer
from .const import CONF_FALLBACK, CONF_SCHEDULE_SOURCE, DOMAIN
from .domain.machine import decide
from .domain.schedule import resolve_schedule_mode
from .domain.types import (
    Config,
    ControlMode,
    ControlModeChanged,
    ControlState,
    FloorControl,
    ModeSettings,
    OrchestratorState,
    ScheduleChanged,
    ScheduleMode,
    Started,
    TimerFired,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import Event, EventStateChangedData, HomeAssistant

    from .domain.types import FloorId, Input, ScheduleResolution

_LOGGER = logging.getLogger(__name__)


def _default_config(fallback: ScheduleMode) -> Config:
    """Пустая, но валидная конфигурация: все режимы без задержки, датчики открыты.

    Используется, пока `.storage` не наполнен панелью (этап 9): каскад не даёт
    команд (профили пусты), но переходы режимов, гейты и события работают.
    """
    return Config(
        modes={
            mode: ModeSettings(delay_seconds=0, sensors_allowed=True)
            for mode in ScheduleMode
        },
        actions_object={},
        actions_by_floor={},
        actions_by_room_type={},
        actions_by_area={},
        fallback_mode=fallback,
    )


class BuildingCoordinator(DataUpdateCoordinator[OrchestratorState]):
    """Держит состояние Оркестратора и исполняет решения машины."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Инициализировать координатор из конфигурации entry."""
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.entry = entry
        self._source_ids: list[str] = list(entry.data[CONF_SCHEDULE_SOURCE])
        self._fallback = ScheduleMode(entry.data[CONF_FALLBACK])
        self._config_store = ConfigStore(hass)
        self._timer = DelayedTransitionTimer()
        self._lock = asyncio.Lock()
        self._topology_dirty = False
        self.gates: dict[FloorId, bool] = {}

    # --- Снимки ---------------------------------------------------------

    def _read_resolution(self) -> ScheduleResolution:
        """Пересчитать режим расписания из текущих состояний источника."""
        events = read_schedule_events(self.hass, self._source_ids)
        return resolve_schedule_mode(events, self._fallback)

    async def _async_update_data(self) -> OrchestratorState:
        """Собрать начальный снимок состояния (без применения; см. Started)."""
        config = await self._config_store.async_load()
        if config is None:
            config = _default_config(self._fallback)
        topology = build_topology_snapshot(self.hass)
        resolution = self._read_resolution()
        return OrchestratorState(
            config=config,
            topology=topology,
            control=ControlState(building=ControlMode.AUTO, floors={}),
            schedule_mode=resolution.mode,
            source_available=resolution.source_available,
            applied_mode=None,
            pending=None,
        )

    # --- Жизненный цикл -------------------------------------------------

    async def async_config_entry_first_refresh(self) -> None:
        """Первый снимок, подписки и старт (применение вычисленного режима)."""
        await super().async_config_entry_first_refresh()
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self._source_ids, self._handle_source_change
            )
        )
        self._subscribe_registry()
        self.entry.async_on_unload(self._timer.cancel)
        await self._dispatch(Started(self._read_resolution()))

    def _subscribe_registry(self) -> None:
        """Помечать снимок топологии устаревшим при изменении реестров.

        Лениво: снимок пересобирается на следующем реальном событии (или по
        сервису `reapply`), а не на каждое изменение реестра — без лишних
        повторных каскадов.
        """
        registry_events = (
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            ar.EVENT_AREA_REGISTRY_UPDATED,
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            fr.EVENT_FLOOR_REGISTRY_UPDATED,
        )
        for event_type in registry_events:
            self.entry.async_on_unload(
                self.hass.bus.async_listen(event_type, self._handle_registry_change)
            )

    # --- Обработчики событий HA (sync callbacks) ------------------------

    @callback
    def _handle_source_change(self, event: Event[EventStateChangedData]) -> None:
        """Изменился источник расписания — пересчитать и применить."""
        self._schedule_dispatch(ScheduleChanged(self._read_resolution()))

    @callback
    def _handle_registry_change(self, event: Event) -> None:
        """Изменился реестр — пометить снимок топологии устаревшим."""
        self._topology_dirty = True

    @callback
    def _on_timer_fire(self) -> None:
        """Сработал таймер отложенного перехода."""
        self._schedule_dispatch(TimerFired())

    def _schedule_dispatch(self, inp: Input) -> None:
        """Запустить цикл диспетчеризации задачей (из sync-callback)."""
        self.hass.async_create_task(self._dispatch(inp), name=f"{DOMAIN}_dispatch")

    # --- Публичный API для сущностей и сервисов -------------------------

    async def async_set_building_mode(self, mode: ControlMode) -> None:
        """Переключить режим управления зданием (Авто/Ручной)."""
        await self._dispatch(ControlModeChanged(building=mode))

    async def async_set_floor_mode(
        self, floor_id: FloorId, control: FloorControl
    ) -> None:
        """Переключить режим управления этажа (следует расписанию / ручной стоп)."""
        await self._dispatch(
            ControlModeChanged(floor_id=floor_id, floor_control=control)
        )

    async def async_reapply(self) -> None:
        """Пересобрать снимки и применить каскад заново (сервис `reapply`)."""
        self._topology_dirty = True
        await self._dispatch(ScheduleChanged(self._read_resolution()))

    def gate_for(self, floor_id: FloorId) -> bool:
        """Значение гейта этажа (True = датчики разрешены); по умолчанию открыт."""
        return self.gates.get(floor_id, True)

    # --- Ядро цикла -----------------------------------------------------

    async def _dispatch(self, inp: Input) -> None:
        """Один цикл: снимок → decide → исполнение → рассылка сущностям."""
        async with self._lock:
            state = self.data
            if self._topology_dirty:
                state = replace(state, topology=build_topology_snapshot(self.hass))
                self._topology_dirty = False
            now = self.hass.loop.time()
            decision = decide(state, inp, now)

            if decision.plan is not None:
                await execute_plan(self.hass, decision.plan)
            self._timer.apply(self.hass, decision.timer_op, now, self._on_timer_fire)
            publish_events(self.hass, decision.events)
            self.gates = dict(decision.gates)
            self.async_set_updated_data(decision.state)

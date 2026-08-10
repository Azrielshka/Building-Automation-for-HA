"""WebSocket API: мониторинг и точечные операции панели (ТЗ §9.2, §9.3, §11.1).

**Точечность.** Панель меняет конфигурацию по одному узлу (`scope`+`key`+`mode`),
а не отправкой всего документа: при пусконаладке она штатно открыта в двух
местах, и сохранение целиком означало бы, что устаревшая вкладка молча затрёт
чужие правки. Read-modify-write сериализован локом координатора.

**Идемпотентность.** Повторный вызов с теми же аргументами даёт то же состояние.

**Наследование.** `set_actions` с пустым списком — это явное «ничего не делать»
на данном уровне (обрывает наследование); чтобы вернуть наследование, узел надо
удалить через `clear_actions`. Разрешение профиля смотрит на **наличие** ключа
(`domain/profiles._effective`), а не на его пустоту.

**Права (ТЗ §9.3).** Чтение и переключение Авто/Ручной — любому авторизованному;
правка профилей — только администратору (`require_admin`).

Валидация недоверенного входа переиспользует ядро: результат мутации прогоняется
через `dump_config`/`load_config` (белый список доменов и сервисов).

Грузится только в среде HA; ядро её не импортирует.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback

from .adapters.autobrightness import read_autobrightness_by_area
from .const import DOMAIN
from .domain.storage_schema import ConfigValidationError, dump_config
from .domain.types import (
    Action,
    ActionSet,
    Config,
    ControlMode,
    FloorControl,
    ModeSettings,
    RoomType,
    ScheduleMode,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

    from .coordinator import BuildingCoordinator

    type Mutation = Callable[[Config], Config]
    type Connection = websocket_api.ActiveConnection

_MODES = tuple(mode.value for mode in ScheduleMode)
_SCOPES = ("object", "floor", "room_type", "area")
_KEYED_SCOPES = ("floor", "room_type", "area")

_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required("domain"): str,
        vol.Required("service"): str,
        vol.Optional("data", default=dict): dict,
    }
)

_REGISTERED = f"{DOMAIN}_ws_registered"


def async_register_commands(hass: HomeAssistant) -> None:
    """Зарегистрировать команды панели (один раз на инстанс HA)."""
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True
    for command in (
        ws_get_state,
        ws_get_config,
        ws_set_control_mode,
        ws_set_mode_settings,
        ws_set_actions,
        ws_clear_actions,
        ws_set_opt_out,
    ):
        websocket_api.async_register_command(hass, command)


def _coordinator(hass: HomeAssistant) -> BuildingCoordinator | None:
    """Найти координатор загруженного config entry (объект — один entry)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            return coordinator
    return None


def _to_actions(raw: list[dict[str, Any]]) -> ActionSet:
    return tuple(
        Action(domain=a["domain"], service=a["service"], data=dict(a.get("data", {})))
        for a in raw
    )


# --- Мутации конфигурации (чистые: Config → Config) ---------------------


def _node_setter(
    scope: str, key: str | None, mode: ScheduleMode, actions: ActionSet
) -> Mutation:
    """Вернуть функцию, ставящую действия в один узел конфигурации.

    `key` уже проверен `_require_key` для keyed-областей, поэтому здесь он
    приводится к `str` без дополнительной ветви.
    """
    node = str(key)

    def _apply(config: Config) -> Config:
        if scope == "object":
            return replace(
                config, actions_object={**config.actions_object, mode: actions}
            )
        if scope == "floor":
            return replace(
                config,
                actions_by_floor={**config.actions_by_floor, (node, mode): actions},
            )
        if scope == "room_type":
            return replace(
                config,
                actions_by_room_type={
                    **config.actions_by_room_type,
                    (RoomType(node), mode): actions,
                },
            )
        return replace(
            config, actions_by_area={**config.actions_by_area, (node, mode): actions}
        )

    return _apply


def _node_clearer(scope: str, key: str | None, mode: ScheduleMode) -> Mutation:
    """Вернуть функцию, удаляющую узел (возвращает наследование)."""
    node = str(key)

    def _apply(config: Config) -> Config:
        if scope == "object":
            by_mode = {m: a for m, a in config.actions_object.items() if m is not mode}
            return replace(config, actions_object=by_mode)
        if scope == "floor":
            by_floor = {
                k: a for k, a in config.actions_by_floor.items() if k != (node, mode)
            }
            return replace(config, actions_by_floor=by_floor)
        if scope == "room_type":
            target = (RoomType(node), mode)
            by_type = {
                k: a for k, a in config.actions_by_room_type.items() if k != target
            }
            return replace(config, actions_by_room_type=by_type)
        by_area = {k: a for k, a in config.actions_by_area.items() if k != (node, mode)}
        return replace(config, actions_by_area=by_area)

    return _apply


def _require_key(connection: Connection, msg: dict[str, Any]) -> bool:
    """Проверить, что для keyed-областей передан `key`."""
    if msg["scope"] in _KEYED_SCOPES and not msg.get("key"):
        connection.send_error(
            msg["id"],
            websocket_api.const.ERR_INVALID_FORMAT,
            f"key обязателен для scope={msg['scope']}",
        )
        return False
    return True


async def _mutate(
    hass: HomeAssistant,
    connection: Connection,
    msg: dict[str, Any],
    mutate: Mutation,
) -> None:
    """Применить мутацию через координатор, отдав ошибки валидации в панель."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_NOT_FOUND, "интеграция не загружена"
        )
        return
    try:
        await coordinator.async_mutate_config(mutate)
    except ConfigValidationError as err:
        connection.send_error(
            msg["id"], "invalid_config", f"{err.location}: {err.message}"
        )
        return
    except ValueError as err:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_INVALID_FORMAT, str(err)
        )
        return
    connection.send_result(msg["id"], {"config": dump_config(coordinator.config)})


# --- Чтение (любой авторизованный пользователь) -------------------------


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_state"})
@callback
def ws_get_state(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Снимок мониторинга: режимы, гейты, помещения, последний каскад, сироты."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_NOT_FOUND, "интеграция не загружена"
        )
        return

    state = coordinator.data
    config = coordinator.config
    topology = state.topology
    # Свет агрегатных Area этажей — для пометки команды уровнем «этаж» (этап 12:
    # цель светового потока — сущность, схлопывание целит свет агрегата).
    floor_lights = {
        floor.light_entity_id
        for floor in topology.floors.values()
        if floor.light_entity_id is not None
    }
    # Живое состояние автояркости по помещениям (switch.il_*, этап 11). Только
    # чтение для индикации; управление идёт через каскад и от этого не зависит.
    autobrightness, autobrightness_entities = read_autobrightness_by_area(
        hass, topology.rooms
    )

    plan = coordinator.last_plan
    transition = coordinator.last_transition
    last_plan: dict[str, Any] | None = None
    if plan is not None:
        commands = [
            {
                "target": c.target,
                "target_kind": c.target_kind.value,
                "domain": c.action.domain,
                "service": c.action.service,
                "level": "floor" if c.target in floor_lights else "area",
            }
            for c in plan.commands
        ]
        last_plan = {
            "commands": commands,
            "skipped": [
                {"area_id": s.area_id, "reason": s.reason.value} for s in plan.skipped
            ],
            "collapse": {
                "floor": sum(1 for c in commands if c["level"] == "floor"),
                "area": sum(1 for c in commands if c["level"] == "area"),
            },
            "previous_mode": (
                transition[0].value
                if transition is not None and transition[0] is not None
                else None
            ),
            "applied_mode": (
                transition[1].value
                if transition is not None and transition[1] is not None
                else None
            ),
        }

    connection.send_result(
        msg["id"],
        {
            "building_control": state.control.building.value,
            "schedule_source": list(coordinator.schedule_source),
            "schedule_mode": state.schedule_mode.value,
            "applied_mode": (
                state.applied_mode.value if state.applied_mode is not None else None
            ),
            "source_available": state.source_available,
            "pending": (
                {
                    "target_mode": state.pending.target_mode.value,
                    "apply_at": state.pending.apply_at,
                }
                if state.pending is not None
                else None
            ),
            "floors": [
                {
                    "floor_id": floor_id,
                    "aggregate_area_id": floor.aggregate_area_id,
                    "control": state.control.floors.get(
                        floor_id, FloorControl.BY_BUILDING
                    ).value,
                    "gate": coordinator.gate_for(floor_id),
                }
                for floor_id, floor in topology.floors.items()
            ],
            "rooms": [
                {
                    "area_id": room.area_id,
                    "floor_id": room.floor_id,
                    "room_type": (
                        room.room_type.value if room.room_type is not None else None
                    ),
                    "opt_out": room.opt_out,
                    "status": room.status.value,
                    "autobrightness": autobrightness.get(room.area_id),
                }
                for room in topology.rooms.values()
            ],
            "autobrightness_entities": autobrightness_entities,
            "last_plan": last_plan,
            "orphaned": {
                "areas": sorted(
                    {a for (a, _m) in config.actions_by_area if a not in topology.rooms}
                ),
                "floors": sorted(
                    {
                        f
                        for (f, _m) in config.actions_by_floor
                        if f not in topology.floors
                    }
                ),
            },
        },
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_config"})
@callback
def ws_get_config(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Текущая конфигурация профилей (матрица режимов)."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_NOT_FOUND, "интеграция не загружена"
        )
        return
    connection.send_result(msg["id"], {"config": dump_config(coordinator.config)})


# --- Переключение Авто/Ручной (любой авторизованный пользователь) -------


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_control_mode",
        vol.Required("target"): vol.In(("building", "floor")),
        vol.Required("mode"): vol.In(("auto", "manual")),
        vol.Optional("floor_id"): str,
    }
)
@websocket_api.async_response
async def ws_set_control_mode(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Перевести здание или этаж в Авто/Ручной."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_NOT_FOUND, "интеграция не загружена"
        )
        return
    if msg["target"] == "building":
        await coordinator.async_set_building_mode(ControlMode(msg["mode"]))
    else:
        floor_id = msg.get("floor_id")
        if not floor_id:
            connection.send_error(
                msg["id"],
                websocket_api.const.ERR_INVALID_FORMAT,
                "floor_id обязателен при target=floor",
            )
            return
        control = (
            FloorControl.BY_BUILDING if msg["mode"] == "auto" else FloorControl.MANUAL
        )
        await coordinator.async_set_floor_mode(floor_id, control)
    connection.send_result(msg["id"], {"ok": True})


# --- Правка профилей (только администратор) -----------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_mode_settings",
        vol.Required("mode"): vol.In(_MODES),
        vol.Required("delay_seconds"): vol.All(int, vol.Range(min=0)),
        vol.Required("sensors_allowed"): bool,
        vol.Optional("sensors_allowed_by_floor"): {str: bool},
    }
)
@websocket_api.async_response
async def ws_set_mode_settings(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Задать задержку и флаг датчиков для одного режима (точечно)."""
    mode = ScheduleMode(msg["mode"])
    settings = ModeSettings(
        delay_seconds=msg["delay_seconds"],
        sensors_allowed=msg["sensors_allowed"],
        sensors_allowed_by_floor=dict(msg.get("sensors_allowed_by_floor", {})),
    )

    def _apply(config: Config) -> Config:
        return replace(config, modes={**config.modes, mode: settings})

    await _mutate(hass, connection, msg, _apply)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_actions",
        vol.Required("scope"): vol.In(_SCOPES),
        vol.Optional("key"): str,
        vol.Required("mode"): vol.In(_MODES),
        vol.Required("actions"): [_ACTION_SCHEMA],
    }
)
@websocket_api.async_response
async def ws_set_actions(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Задать действия одного узла. Пустой список — явное «ничего не делать»."""
    if not _require_key(connection, msg):
        return
    mutate = _node_setter(
        msg["scope"],
        msg.get("key"),
        ScheduleMode(msg["mode"]),
        _to_actions(msg["actions"]),
    )
    await _mutate(hass, connection, msg, mutate)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/clear_actions",
        vol.Required("scope"): vol.In(_SCOPES),
        vol.Optional("key"): str,
        vol.Required("mode"): vol.In(_MODES),
    }
)
@websocket_api.async_response
async def ws_clear_actions(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Удалить узел — вернуть наследование с вышестоящего уровня."""
    if not _require_key(connection, msg):
        return
    mutate = _node_clearer(msg["scope"], msg.get("key"), ScheduleMode(msg["mode"]))
    await _mutate(hass, connection, msg, mutate)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_opt_out",
        vol.Required("area_id"): str,
        vol.Required("opted"): bool,
    }
)
@websocket_api.async_response
async def ws_set_opt_out(
    hass: HomeAssistant, connection: Connection, msg: dict[str, Any]
) -> None:
    """Исключить помещение из управления по расписанию или вернуть (Q3=C)."""
    area_id = msg["area_id"]
    opted = msg["opted"]

    def _apply(config: Config) -> Config:
        current = set(config.opted_out_areas)
        if opted:
            current.add(area_id)
        else:
            current.discard(area_id)
        return replace(config, opted_out_areas=frozenset(current))

    await _mutate(hass, connection, msg, _apply)

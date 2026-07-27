"""Сериализация, валидация и миграция конфигурации (SPEC §2.2.6, §3.2).

Чистые преобразования данных, без `hass`. `load_config` считает вход
недоверенным (его пишет UI и правит рука) и либо возвращает валидную `Config`,
либо бросает `ConfigValidationError` с указанием места.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .types import (
    Action,
    ActionSet,
    Config,
    ModeSettings,
    RoomType,
    ScheduleMode,
)

type RawConfig = dict[str, Any]

# Белый список для действий профиля (SPEC §4.2 ТЗ): только идемпотентные
# turn_on/turn_off в доменах light/switch; toggle запрещён.
_ALLOWED_DOMAINS = frozenset({"light", "switch"})
_ALLOWED_SERVICES = frozenset({"turn_on", "turn_off"})


class ConfigValidationError(Exception):
    """Недоверенный вход конфигурации не прошёл валидацию.

    `location` — путь к месту ошибки (например `actions.object.off[0].domain`).
    """

    def __init__(self, location: str, message: str) -> None:
        """Создать ошибку с указанием места и причины."""
        self.location = location
        self.message = message
        super().__init__(f"{location}: {message}")


def _dump_action(action: Action) -> RawConfig:
    return {
        "domain": action.domain,
        "service": action.service,
        "data": dict(action.data),
    }


def _dump_actions(actions: ActionSet) -> list[RawConfig]:
    return [_dump_action(action) for action in actions]


def _dump_by_mode(by_mode: Mapping[ScheduleMode, ActionSet]) -> RawConfig:
    return {mode.value: _dump_actions(actions) for mode, actions in by_mode.items()}


def _dump_keyed(
    keyed: Mapping[tuple[Any, ScheduleMode], ActionSet],
) -> RawConfig:
    """Плоские ключи (key, mode) → вложенный словарь {key: {mode: actions}}.

    Ключ — `str` (floor_id/area_id) либо `RoomType` (StrEnum, сериализуется как
    строка); тип принимаем как `Any`, кортеж инвариантен по ключу.
    """
    result: RawConfig = {}
    for (key, mode), actions in keyed.items():
        result.setdefault(str(key), {})[mode.value] = _dump_actions(actions)
    return result


def dump_config(config: Config) -> RawConfig:
    """Сериализовать конфигурацию в JSON-совместимый словарь."""
    return {
        "fallback_mode": config.fallback_mode.value,
        "modes": {
            mode.value: {
                "delay_seconds": settings.delay_seconds,
                "sensors_allowed": settings.sensors_allowed,
                "sensors_allowed_by_floor": dict(settings.sensors_allowed_by_floor),
            }
            for mode, settings in config.modes.items()
        },
        "actions": {
            "object": _dump_by_mode(config.actions_object),
            "floor": _dump_keyed(config.actions_by_floor),
            "room_type": _dump_keyed(config.actions_by_room_type),
            "area": _dump_keyed(config.actions_by_area),
        },
        "opted_out_areas": sorted(config.opted_out_areas),
    }


def migrate(major: int, minor: int, data: RawConfig) -> RawConfig:
    """Мигрировать сырые данные схемы к текущей версии (SPEC §2.2.6).

    Версия 1 — единственная; будущие миграции добавляются здесь ветвями по
    `major`. Сигнатура — три аргумента (`_async_migrate_func` в обёртке `Store`).
    """
    return data


def _load_action(raw: RawConfig, location: str) -> Action:
    domain = raw["domain"]
    service = raw["service"]
    if domain not in _ALLOWED_DOMAINS:
        raise ConfigValidationError(
            f"{location}.domain",
            f"домен {domain!r} вне белого списка light/switch",
        )
    if service not in _ALLOWED_SERVICES:
        raise ConfigValidationError(
            f"{location}.service",
            f"сервис {service!r} запрещён (только turn_on/turn_off)",
        )
    return Action(domain=domain, service=service, data=dict(raw.get("data", {})))


def _load_actions(raw: Sequence[RawConfig], location: str) -> ActionSet:
    return tuple(
        _load_action(item, f"{location}[{index}]") for index, item in enumerate(raw)
    )


def _load_by_mode(raw: RawConfig, location: str) -> dict[ScheduleMode, ActionSet]:
    return {
        ScheduleMode(mode): _load_actions(actions, f"{location}.{mode}")
        for mode, actions in raw.items()
    }


def _load_keyed(
    raw: RawConfig, key_type: type[Any], location: str
) -> dict[tuple[Any, ScheduleMode], ActionSet]:
    result: dict[tuple[Any, ScheduleMode], ActionSet] = {}
    for key, by_mode in raw.items():
        typed_key = key_type(key)
        for mode, actions in by_mode.items():
            result[typed_key, ScheduleMode(mode)] = _load_actions(
                actions, f"{location}.{key}.{mode}"
            )
    return result


def _require(value: Any, expected: type, location: str) -> Any:
    """Проверить тип значения; иначе — ConfigValidationError с местом."""
    # bool — подкласс int: int-поле не должно молча принимать True/False.
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise ConfigValidationError(
            location, f"ожидался {expected.__name__}, получен {type(value).__name__}"
        )
    return value


def _load_mode_settings(raw: RawConfig, location: str) -> ModeSettings:
    return ModeSettings(
        delay_seconds=_require(raw["delay_seconds"], int, f"{location}.delay_seconds"),
        sensors_allowed=_require(
            raw["sensors_allowed"], bool, f"{location}.sensors_allowed"
        ),
        sensors_allowed_by_floor=dict(raw.get("sensors_allowed_by_floor", {})),
    )


def load_config(raw: RawConfig) -> Config:
    """Разобрать и провалидировать конфигурацию из хранилища."""
    actions = raw.get("actions", {})
    return Config(
        modes={
            ScheduleMode(mode): _load_mode_settings(settings, f"modes.{mode}")
            for mode, settings in raw.get("modes", {}).items()
        },
        actions_object=_load_by_mode(actions.get("object", {}), "actions.object"),
        actions_by_floor=_load_keyed(actions.get("floor", {}), str, "actions.floor"),
        actions_by_room_type=_load_keyed(
            actions.get("room_type", {}), RoomType, "actions.room_type"
        ),
        actions_by_area=_load_keyed(actions.get("area", {}), str, "actions.area"),
        fallback_mode=ScheduleMode(raw["fallback_mode"]),
        opted_out_areas=frozenset(_load_opted_out(raw.get("opted_out_areas", []))),
    )


def _load_opted_out(raw: Any, location: str = "opted_out_areas") -> list[str]:
    """Провалидировать список исключённых area_id (недоверенный вход)."""
    if not isinstance(raw, list):
        raise ConfigValidationError(location, "ожидался список area_id")
    for index, item in enumerate(raw):
        _require(item, str, f"{location}[{index}]")
    return raw

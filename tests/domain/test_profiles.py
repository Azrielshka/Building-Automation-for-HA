"""Тесты разрешения профилей с наследованием (SPEC §5.3, domain/profiles.py)."""

from __future__ import annotations

from custom_components.building_automation.domain.profiles import resolve_actions
from custom_components.building_automation.domain.topology import TopologySnapshot
from custom_components.building_automation.domain.types import (
    Action,
    Config,
    Room,
    RoomType,
    ScheduleMode,
)

_LESSON = ScheduleMode.LESSON
_FLOOR_ACTION = (Action("light", "turn_off"),)


def _config(**overrides: object) -> Config:
    """Config с пустыми структурами, кроме переданных."""
    base: dict[str, object] = {
        "modes": {},
        "actions_object": {},
        "actions_by_floor": {},
        "actions_by_room_type": {},
        "actions_by_area": {},
        "fallback_mode": ScheduleMode.OFF,
    }
    base.update(overrides)
    return Config(**base)  # type: ignore[arg-type]


def _snapshot(room: Room) -> TopologySnapshot:
    return TopologySnapshot(floors={}, rooms={room.area_id: room})


def test_room_inherits_floor() -> None:
    """Помещение без своих настроек получает профиль этажа."""
    room = Room(area_id="a1", floor_id="f1")
    config = _config(actions_by_floor={("f1", _LESSON): _FLOOR_ACTION})
    result = resolve_actions(config, _snapshot(room), _LESSON)
    assert result["a1"] == _FLOOR_ACTION


def test_area_overrides_floor() -> None:
    """Профиль помещения перекрывает профиль этажа."""
    room = Room(area_id="a1", floor_id="f1")
    area_action = (Action("light", "turn_on", {"brightness_pct": 100}),)
    config = _config(
        actions_by_floor={("f1", _LESSON): _FLOOR_ACTION},
        actions_by_area={("a1", _LESSON): area_action},
    )
    result = resolve_actions(config, _snapshot(room), _LESSON)
    assert result["a1"] == area_action


def test_floor_overrides_object() -> None:
    """Профиль этажа перекрывает профиль объекта."""
    room = Room(area_id="a1", floor_id="f1")
    config = _config(
        actions_object={_LESSON: (Action("light", "turn_on"),)},
        actions_by_floor={("f1", _LESSON): _FLOOR_ACTION},
    )
    result = resolve_actions(config, _snapshot(room), _LESSON)
    assert result["a1"] == _FLOOR_ACTION


def test_object_inherited_when_no_floor() -> None:
    """Без профиля этажа помещение наследует профиль объекта."""
    room = Room(area_id="a1", floor_id="f1")
    object_action = (Action("light", "turn_off"),)
    config = _config(actions_object={_LESSON: object_action})
    result = resolve_actions(config, _snapshot(room), _LESSON)
    assert result["a1"] == object_action


def test_empty_when_nothing_set() -> None:
    """Пустой набор действий на всех уровнях — допустимый результат."""
    room = Room(area_id="a1", floor_id="f1")
    result = resolve_actions(_config(), _snapshot(room), _LESSON)
    assert result["a1"] == ()


def test_room_type_overrides_floor() -> None:
    """Профиль типа помещения перекрывает профиль этажа."""
    room = Room(area_id="a1", floor_id="f1", room_type=RoomType.KORRIDOR)
    type_action = (Action("switch", "turn_on"),)
    config = _config(
        actions_by_floor={("f1", _LESSON): _FLOOR_ACTION},
        actions_by_room_type={(RoomType.KORRIDOR, _LESSON): type_action},
    )
    result = resolve_actions(config, _snapshot(room), _LESSON)
    assert result["a1"] == type_action


def test_area_overrides_room_type() -> None:
    """Профиль помещения перекрывает профиль типа."""
    room = Room(area_id="a1", floor_id="f1", room_type=RoomType.KORRIDOR)
    area_action = (Action("light", "turn_on"),)
    config = _config(
        actions_by_room_type={
            (RoomType.KORRIDOR, _LESSON): (Action("switch", "turn_on"),)
        },
        actions_by_area={("a1", _LESSON): area_action},
    )
    result = resolve_actions(config, _snapshot(room), _LESSON)
    assert result["a1"] == area_action


def test_typed_room_without_type_profile_falls_to_floor() -> None:
    """Помещение с типом, но без профиля этого типа, наследует этаж."""
    room = Room(area_id="a1", floor_id="f1", room_type=RoomType.ZAL)
    config = _config(actions_by_floor={("f1", _LESSON): _FLOOR_ACTION})
    result = resolve_actions(config, _snapshot(room), _LESSON)
    assert result["a1"] == _FLOOR_ACTION


def test_full_priority_stack() -> None:
    """Все четыре уровня заданы — побеждает профиль помещения."""
    room = Room(area_id="a1", floor_id="f1", room_type=RoomType.KORRIDOR)
    area_action = (Action("light", "turn_on"),)
    config = _config(
        actions_object={_LESSON: (Action("switch", "turn_off"),)},
        actions_by_floor={("f1", _LESSON): (Action("switch", "turn_on"),)},
        actions_by_room_type={
            (RoomType.KORRIDOR, _LESSON): (Action("light", "turn_off"),)
        },
        actions_by_area={("a1", _LESSON): area_action},
    )
    result = resolve_actions(config, _snapshot(room), _LESSON)
    assert result["a1"] == area_action


def test_rooms_inherit_independently() -> None:
    """Каждое помещение снимка получает свой набор; новое наследует этаж."""
    configured = Room(area_id="a1", floor_id="f1")
    fresh = Room(area_id="a2", floor_id="f1")  # без своих настроек
    snapshot = TopologySnapshot(floors={}, rooms={"a1": configured, "a2": fresh})
    area_action = (Action("light", "turn_on"),)
    config = _config(
        actions_by_floor={("f1", _LESSON): _FLOOR_ACTION},
        actions_by_area={("a1", _LESSON): area_action},
    )
    result = resolve_actions(config, snapshot, _LESSON)
    assert result["a1"] == area_action
    assert result["a2"] == _FLOOR_ACTION

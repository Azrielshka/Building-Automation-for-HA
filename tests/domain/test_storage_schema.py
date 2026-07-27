"""Тесты схемы хранилища: сериализация, валидация, миграция (SPEC §5.6)."""

from __future__ import annotations

import pytest

from custom_components.building_automation.domain.storage_schema import (
    ConfigValidationError,
    dump_config,
    load_config,
    migrate,
)
from custom_components.building_automation.domain.types import (
    Action,
    Config,
    ModeSettings,
    RoomType,
    ScheduleMode,
)


def test_roundtrip_minimal() -> None:
    """Минимальная конфигурация переживает dump→load без потерь."""
    config = Config(
        modes={},
        actions_object={},
        actions_by_floor={},
        actions_by_room_type={},
        actions_by_area={},
        fallback_mode=ScheduleMode.OFF,
    )
    assert load_config(dump_config(config)) == config


def _full_config() -> Config:
    """Конфигурация с заполненными всеми пятью структурами."""
    return Config(
        modes={
            ScheduleMode.LESSON: ModeSettings(
                delay_seconds=300,
                sensors_allowed=True,
                sensors_allowed_by_floor={"1_etazh": False},
            ),
        },
        actions_object={ScheduleMode.OFF: (Action("light", "turn_off"),)},
        actions_by_floor={
            ("1_etazh", ScheduleMode.BREAK): (
                Action("light", "turn_on", {"brightness_pct": 100}),
            ),
        },
        actions_by_room_type={
            (RoomType.KORRIDOR, ScheduleMode.LESSON): (Action("switch", "turn_off"),),
        },
        actions_by_area={
            ("103_vestibiul", ScheduleMode.WINDOW): (Action("light", "turn_on"),),
        },
        fallback_mode=ScheduleMode.OFF,
        opted_out_areas=frozenset({"104_kabinet", "105_zal"}),
    )


def test_roundtrip_full() -> None:
    """Полная конфигурация со всеми структурами переживает dump→load."""
    config = _full_config()
    assert load_config(dump_config(config)) == config


def _raw_with_action(domain: str, service: str) -> dict:
    return {
        "fallback_mode": "off",
        "modes": {},
        "actions": {
            "object": {"off": [{"domain": domain, "service": service, "data": {}}]},
            "floor": {},
            "room_type": {},
            "area": {},
        },
    }


def test_action_domain_whitelist() -> None:
    """Действие с доменом вне light/switch отвергается с указанием места."""
    with pytest.raises(ConfigValidationError) as exc:
        load_config(_raw_with_action("mqtt", "publish"))
    assert exc.value.location.endswith(".domain")
    assert "mqtt" in exc.value.message


def test_toggle_service_rejected() -> None:
    """Сервис toggle запрещён (неидемпотентен, SPEC §4.2 ТЗ)."""
    with pytest.raises(ConfigValidationError) as exc:
        load_config(_raw_with_action("light", "toggle"))
    assert exc.value.location.endswith(".service")
    assert "toggle" in exc.value.message


def test_opted_out_areas_roundtrip() -> None:
    """Множество исключённых помещений переживает dump→load (Q3=C)."""
    config = _full_config()
    restored = load_config(dump_config(config))
    assert restored.opted_out_areas == frozenset({"104_kabinet", "105_zal"})


def test_opted_out_areas_absent_defaults_empty() -> None:
    """Старый файл без opted_out_areas грузится с пустым множеством."""
    restored = load_config(_raw_with_action("light", "turn_off"))
    assert restored.opted_out_areas == frozenset()


def test_opted_out_areas_wrong_type_rejected() -> None:
    """Неверный тип opted_out_areas отвергается с указанием места."""
    raw = _raw_with_action("light", "turn_off")
    raw["opted_out_areas"] = "104_kabinet"  # строка вместо списка
    with pytest.raises(ConfigValidationError) as exc:
        load_config(raw)
    assert exc.value.location == "opted_out_areas"


def test_wrong_type_gives_error_with_location() -> None:
    """Некорректный тип поля даёт ConfigValidationError с указанием места."""
    raw = {
        "fallback_mode": "off",
        "modes": {
            "lesson": {
                "delay_seconds": "не число",
                "sensors_allowed": True,
                "sensors_allowed_by_floor": {},
            }
        },
        "actions": {"object": {}, "floor": {}, "room_type": {}, "area": {}},
    }
    with pytest.raises(ConfigValidationError) as exc:
        load_config(raw)
    assert exc.value.location.endswith(".delay_seconds")
    assert "int" in exc.value.message


def test_bool_not_accepted_as_int_delay() -> None:
    """delay_seconds=True (bool — подкласс int) отвергается как неверный тип."""
    raw = {
        "fallback_mode": "off",
        "modes": {
            "lesson": {
                "delay_seconds": True,
                "sensors_allowed": True,
                "sensors_allowed_by_floor": {},
            }
        },
        "actions": {"object": {}, "floor": {}, "room_type": {}, "area": {}},
    }
    with pytest.raises(ConfigValidationError) as exc:
        load_config(raw)
    assert exc.value.location.endswith(".delay_seconds")


def test_unknown_field_does_not_break_load() -> None:
    """Неизвестное поле (например, из будущей версии) не роняет загрузку."""
    raw = {
        "fallback_mode": "off",
        "modes": {},
        "actions": {"object": {}, "floor": {}, "room_type": {}, "area": {}},
        "future_field": 42,
    }
    config = load_config(raw)
    assert config.fallback_mode is ScheduleMode.OFF


def test_load_missing_sections_gives_empty_config() -> None:
    """Отсутствующие секции modes/actions дают пустую конфигурацию, не падение."""
    config = load_config({"fallback_mode": "off"})
    assert config == Config(
        modes={},
        actions_object={},
        actions_by_floor={},
        actions_by_room_type={},
        actions_by_area={},
        fallback_mode=ScheduleMode.OFF,
    )


def test_migrate_v1_preserves_profiles() -> None:
    """Миграция версии 1 сохраняет профили и даёт загружаемую конфигурацию."""
    data = dump_config(_full_config())
    migrated = migrate(1, 1, data)
    assert migrated == data
    assert load_config(migrated) == _full_config()

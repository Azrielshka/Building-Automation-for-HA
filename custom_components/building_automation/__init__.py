"""Интеграция «Building Automation» (Оркестратор здания).

Тонкая обвязка жизненного цикла config entry. Вся логика — в пакете `domain`
(чистые функции без `hass`); связывание с Home Assistant — в `adapters` и
`coordinator`. См. SPEC §2.

Импорты Home Assistant здесь — только под `TYPE_CHECKING` или **отложенные внутри
функций**. Причина: пакет `homeassistant` не установлен в среде разработки
(SPEC §2.1), а этот модуль неизбежно загружается при импорте любого подмодуля
`domain` — ядро должно оставаться импортируемым без HA. Обвязочные модули
(`coordinator`, платформы) грузятся отложенно, только когда HA реально вызывает
setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

    from .coordinator import BuildingCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настроить config entry: координатор, платформы, сервисы."""
    # Отложенные импорты — разрыв зависимости ядра от HA (см. docstring модуля).
    from .const import PLATFORMS  # noqa: PLC0415
    from .coordinator import BuildingCoordinator  # noqa: PLC0415

    coordinator = BuildingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, list(PLATFORMS))
    _async_register_services(hass, coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузить config entry, его платформы и сервисы."""
    from .const import (  # noqa: PLC0415
        DOMAIN,
        PLATFORMS,
        SERVICE_REAPPLY,
        SERVICE_SET_CONTROL_MODE,
    )

    unloaded = await hass.config_entries.async_unload_platforms(entry, list(PLATFORMS))
    if unloaded:
        # Один объект — один config entry: сервисы домена снимаем вместе с ним.
        for service in (SERVICE_SET_CONTROL_MODE, SERVICE_REAPPLY):
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


def _async_register_services(
    hass: HomeAssistant, coordinator: BuildingCoordinator
) -> None:
    """Зарегистрировать сервисы `set_control_mode` и `reapply` (ТЗ §10)."""
    import voluptuous as vol  # noqa: PLC0415

    from .const import (  # noqa: PLC0415
        ATTR_FLOOR_ID,
        ATTR_MODE,
        ATTR_TARGET,
        DOMAIN,
        SERVICE_REAPPLY,
        SERVICE_SET_CONTROL_MODE,
        TARGET_BUILDING,
        TARGET_FLOOR,
    )
    from .domain.types import ControlMode, FloorControl  # noqa: PLC0415

    set_control_mode_schema = vol.Schema(
        {
            vol.Required(ATTR_TARGET): vol.In((TARGET_BUILDING, TARGET_FLOOR)),
            vol.Required(ATTR_MODE): vol.In(("auto", "manual")),
            vol.Optional(ATTR_FLOOR_ID): str,
        }
    )

    async def _handle_set_control_mode(call: ServiceCall) -> None:
        """Перевести здание или этаж в Авто/Ручной."""
        mode = call.data[ATTR_MODE]
        if call.data[ATTR_TARGET] == TARGET_BUILDING:
            await coordinator.async_set_building_mode(ControlMode(mode))
            return
        floor_id = call.data.get(ATTR_FLOOR_ID)
        if not floor_id:
            raise vol.Invalid(f"{ATTR_FLOOR_ID} обязателен при target=floor")
        control = FloorControl.BY_BUILDING if mode == "auto" else FloorControl.MANUAL
        await coordinator.async_set_floor_mode(floor_id, control)

    async def _handle_reapply(call: ServiceCall) -> None:
        """Пересобрать снимки и применить каскад заново."""
        await coordinator.async_reapply()

    if not hass.services.has_service(DOMAIN, SERVICE_SET_CONTROL_MODE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_CONTROL_MODE,
            _handle_set_control_mode,
            schema=set_control_mode_schema,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REAPPLY):
        hass.services.async_register(DOMAIN, SERVICE_REAPPLY, _handle_reapply)

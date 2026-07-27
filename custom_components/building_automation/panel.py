"""Регистрация панели пусконаладчика и её статики (SPEC §2.6, ТЗ §9.2).

Оболочка. Отдаёт `www/` как статику и регистрирует custom-panel в боковом меню.
Панель говорит с ядром только через WS-команды (`websocket_api.py`); Python здесь
ничего не считает — лишь монтирует фронтенд.

`require_admin=False`: мониторинг и переключение Авто/Ручной доступны всем
(ТЗ §9.3), а правка профилей гейтится внутри панели по `hass.user.is_admin` и
жёстко — на стороне WS-команд (`@require_admin`).

Грузится только в среде HA; ядро её не импортирует.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig

from .const import (
    DOMAIN,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PANEL_WEBCOMPONENT,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_STATIC_REGISTERED = f"{DOMAIN}_panel_static"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Смонтировать статику и зарегистрировать панель в боковом меню."""
    www_dir = Path(__file__).parent / "www"

    # Статику регистрируем один раз на инстанс HA: снять её нельзя, повторная
    # регистрация того же пути — ошибка. Панель — на каждый setup (снимается при
    # выгрузке), чтобы reload не падал на повторной регистрации маршрута.
    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_URL, str(www_dir), False)]
        )
        hass.data[_STATIC_REGISTERED] = True

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_WEBCOMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{PANEL_STATIC_URL}/panel.js",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=False,
    )


def async_remove_panel(hass: HomeAssistant) -> None:
    """Снять панель из бокового меню (при выгрузке entry)."""
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)

"""Адаптер хранилища: обёртка `Store` над схемой ядра (SPEC §2.3, §3 гайда).

Персистентность конфигурации в `.storage`. Вся сериализация/валидация/миграция —
в чистом `domain/storage_schema`; здесь только связывание со `Store`. Грузится
только в среде HA.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from ..const import STORAGE_KEY, STORAGE_MINOR_VERSION, STORAGE_VERSION
from ..domain.storage_schema import dump_config, load_config, migrate

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..domain.types import Config


class BuildingStore(Store[dict[str, Any]]):
    """`Store` с миграцией через чистую функцию ядра."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Мигрировать сырые данные к текущей версии схемы."""
        return migrate(old_major_version, old_minor_version, old_data)


class ConfigStore:
    """Читает и пишет `Config` через `BuildingStore`."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Создать хранилище конфигурации для этого HA."""
        self._store = BuildingStore(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            minor_version=STORAGE_MINOR_VERSION,
        )

    async def async_load(self) -> Config | None:
        """Загрузить конфигурацию; `None`, если хранилище пусто."""
        raw = await self._store.async_load()
        if raw is None:
            return None
        return load_config(raw)

    async def async_save(self, config: Config) -> None:
        """Сохранить конфигурацию."""
        await self._store.async_save(dump_config(config))

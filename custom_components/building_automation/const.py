"""Константы интеграции «Building Automation» (Оркестратор здания)."""

from typing import Final

DOMAIN: Final = "building_automation"

# Ключи конфигурации (entry.data), задаются в config_flow.
CONF_SCHEDULE_SOURCE: Final = "schedule_source"  # список entity_id источника
CONF_FALLBACK: Final = "fallback_mode"  # режим при недоступном расписании

# Платформы сущностей (в корне пакета — loader не сканирует подпапки).
PLATFORMS: Final = ("sensor", "binary_sensor", "select", "switch")

# Доменные события на шине (ТЗ §10). Payload: new_mode, previous_mode, source,
# floor_id, area_id, target_mode, apply_at — по типу события.
EVENT_MODE_CHANGED: Final = f"{DOMAIN}_mode_changed"  # свершившаяся смена
EVENT_MODE_WARNING: Final = f"{DOMAIN}_mode_warning"  # предупреждение о смене
EVENT_TRANSITION_CANCELLED: Final = f"{DOMAIN}_transition_cancelled"  # отмена

# Сервисы (ТЗ §10).
SERVICE_SET_CONTROL_MODE: Final = "set_control_mode"  # цель — здание или этаж
SERVICE_REAPPLY: Final = "reapply"  # пересобрать снимки и применить каскад

# Поля вызова сервиса set_control_mode.
ATTR_TARGET: Final = "target"  # "building" | "floor"
ATTR_FLOOR_ID: Final = "floor_id"  # обязателен при target=floor
ATTR_MODE: Final = "mode"  # "auto" | "manual"
TARGET_BUILDING: Final = "building"
TARGET_FLOOR: Final = "floor"

# Атрибут сущности отложенного перехода — момент применения.
ATTR_APPLY_AT: Final = "apply_at"

# Метки (Labels) на Area. ba_floor_area и ba_type_* проставляет генератор
# ha-lighting-compilers; ba_optout — вручную (эксплуатационное решение, §3.4 ТЗ).
LABEL_FLOOR_AREA: Final = "ba_floor_area"  # агрегатная Area этажа
LABEL_TYPE_PREFIX: Final = "ba_type_"  # тип помещения: ba_type_<RoomType>
LABEL_OPT_OUT: Final = "ba_optout"  # исключение из управления расписанием

# Версия схемы хранилища (.storage). Миграция — в domain/storage_schema.py.
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 1
STORAGE_KEY: Final = DOMAIN

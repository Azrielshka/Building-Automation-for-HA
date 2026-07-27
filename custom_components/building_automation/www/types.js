/**
 * Типы панели. Формы ДОЛЖНЫ совпадать с дата-классами ядра Python
 * (dump_config и payload get_state, SPEC §2.6). При правке одной стороны
 * правится и вторая — в одном коммите (javascript-guidelines.md §6).
 *
 * Ответы WS — недоверенный вход: обёртки в api.js приводят их к этим типам,
 * потребитель проверяет наличие полей перед использованием.
 */

// --- Home Assistant (минимум, что реально трогаем) ---

/**
 * @typedef {object} HassEntity
 * @property {string} entity_id
 * @property {string} state
 * @property {Record<string, unknown>} attributes
 */

/**
 * @typedef {object} HassRegistryEntry
 * @property {string} entity_id
 * @property {string | null} platform
 */

/**
 * @typedef {object} HassUser
 * @property {boolean} is_admin
 */

/**
 * @typedef {object} HassConnection
 * @property {(callback: (event: unknown) => void, eventType: string)
 *   => Promise<() => void>} subscribeEvents
 */

/**
 * @typedef {object} HomeAssistant
 * @property {Record<string, HassEntity>} states
 * @property {Record<string, HassRegistryEntry>} entities
 * @property {HassUser} user
 * @property {HassConnection} connection
 * @property {(message: object) => Promise<unknown>} callWS
 * @property {(domain: string, service: string, data?: object) => Promise<unknown>}
 *   callService
 */

// --- Мониторинг (payload get_state) ---

/**
 * @typedef {object} PendingInfo
 * @property {string} target_mode
 * @property {number} apply_at
 */

/**
 * @typedef {object} FloorInfo
 * @property {string} floor_id
 * @property {string | null} aggregate_area_id
 * @property {string} control            "auto" | "manual"
 * @property {boolean} gate              датчики разрешены
 */

/**
 * @typedef {object} RoomInfo
 * @property {string} area_id
 * @property {string} floor_id
 * @property {string | null} room_type
 * @property {boolean} opt_out
 * @property {string} status             "ok" | "no_light" | "multiple_lights"
 */

/**
 * @typedef {object} CommandInfo
 * @property {string} target_area_id
 * @property {string} domain
 * @property {string} service
 * @property {string} level              "floor" | "area"
 */

/**
 * @typedef {object} SkipInfo
 * @property {string} area_id
 * @property {string} reason
 */

/**
 * @typedef {object} CollapseInfo
 * @property {number} floor
 * @property {number} area
 */

/**
 * @typedef {object} PlanInfo
 * @property {CommandInfo[]} commands
 * @property {SkipInfo[]} skipped
 * @property {CollapseInfo} collapse
 * @property {string | null} previous_mode  режим до этого каскада
 * @property {string | null} applied_mode   режим, применённый этим каскадом
 */

/**
 * @typedef {object} OrphanedInfo
 * @property {string[]} areas
 * @property {string[]} floors
 */

/**
 * @typedef {object} StateSnapshot
 * @property {string} building_control
 * @property {string} schedule_mode
 * @property {string | null} applied_mode
 * @property {boolean} source_available
 * @property {PendingInfo | null} pending
 * @property {FloorInfo[]} floors
 * @property {RoomInfo[]} rooms
 * @property {PlanInfo | null} last_plan
 * @property {OrphanedInfo} orphaned
 */

// --- Конфигурация (dump_config) ---

/**
 * @typedef {object} ActionSpec
 * @property {string} domain
 * @property {string} service
 * @property {Record<string, unknown>} data
 */

/**
 * @typedef {object} ModeSettingsSpec
 * @property {number} delay_seconds
 * @property {boolean} sensors_allowed
 * @property {Record<string, boolean>} sensors_allowed_by_floor
 */

/**
 * Действия по узлу: object → {mode: Action[]}; floor/room_type/area →
 * {key: {mode: Action[]}}.
 * @typedef {object} ActionsSection
 * @property {Record<string, ActionSpec[]>} object
 * @property {Record<string, Record<string, ActionSpec[]>>} floor
 * @property {Record<string, Record<string, ActionSpec[]>>} room_type
 * @property {Record<string, Record<string, ActionSpec[]>>} area
 */

/**
 * @typedef {object} BuildingConfig
 * @property {string} fallback_mode
 * @property {Record<string, ModeSettingsSpec>} modes
 * @property {ActionsSection} actions
 * @property {string[]} opted_out_areas   помещения, исключённые из управления
 */

export {};

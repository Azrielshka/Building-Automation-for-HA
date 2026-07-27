/**
 * Обёртки над WS-командами ядра (SPEC §2.6). Единственный способ, которым панель
 * говорит с Python-частью (javascript-guidelines.md §5). Ответ — недоверенный
 * вход: приводим к типу, но потребитель проверяет поля перед использованием.
 *
 * @typedef {import("./types.js").HomeAssistant} HomeAssistant
 * @typedef {import("./types.js").StateSnapshot} StateSnapshot
 * @typedef {import("./types.js").BuildingConfig} BuildingConfig
 * @typedef {import("./types.js").ActionSpec} ActionSpec
 * @typedef {import("./types.js").ModeSettingsSpec} ModeSettingsSpec
 */

const DOMAIN = "building_automation";

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function isObject(value) {
  return typeof value === "object" && value !== null;
}

/**
 * @param {HomeAssistant} hass
 * @returns {Promise<StateSnapshot>}
 */
export async function getState(hass) {
  const result = await hass.callWS({ type: `${DOMAIN}/get_state` });
  if (!isObject(result)) {
    throw new Error("get_state: неожиданный ответ");
  }
  return /** @type {StateSnapshot} */ (result);
}

/**
 * @param {HomeAssistant} hass
 * @returns {Promise<BuildingConfig>}
 */
export async function getConfig(hass) {
  const result = await hass.callWS({ type: `${DOMAIN}/get_config` });
  if (!isObject(result) || !isObject(result.config)) {
    throw new Error("get_config: неожиданный ответ");
  }
  return /** @type {BuildingConfig} */ (result.config);
}

/**
 * @param {HomeAssistant} hass
 * @param {"building" | "floor"} target
 * @param {"auto" | "manual"} mode
 * @param {string} [floorId]
 * @returns {Promise<void>}
 */
export async function setControlMode(hass, target, mode, floorId) {
  /** @type {Record<string, unknown>} */
  const message = { type: `${DOMAIN}/set_control_mode`, target, mode };
  if (floorId !== undefined) {
    message.floor_id = floorId;
  }
  await hass.callWS(message);
}

/**
 * @param {HomeAssistant} hass
 * @param {string} mode
 * @param {number} delaySeconds
 * @param {boolean} sensorsAllowed
 * @param {Record<string, boolean>} [sensorsAllowedByFloor]
 * @returns {Promise<BuildingConfig>}
 */
export async function setModeSettings(
  hass,
  mode,
  delaySeconds,
  sensorsAllowed,
  sensorsAllowedByFloor,
) {
  /** @type {Record<string, unknown>} */
  const message = {
    type: `${DOMAIN}/set_mode_settings`,
    mode,
    delay_seconds: delaySeconds,
    sensors_allowed: sensorsAllowed,
  };
  if (sensorsAllowedByFloor !== undefined) {
    message.sensors_allowed_by_floor = sensorsAllowedByFloor;
  }
  return unwrapConfig(await hass.callWS(message));
}

/**
 * Задать действия узла. Пустой массив — явное «ничего не делать» (обрывает
 * наследование); вернуть наследование — clearActions.
 * @param {HomeAssistant} hass
 * @param {"object" | "floor" | "room_type" | "area"} scope
 * @param {string | null} key
 * @param {string} mode
 * @param {ActionSpec[]} actions
 * @returns {Promise<BuildingConfig>}
 */
export async function setActions(hass, scope, key, mode, actions) {
  /** @type {Record<string, unknown>} */
  const message = { type: `${DOMAIN}/set_actions`, scope, mode, actions };
  if (key !== null) {
    message.key = key;
  }
  return unwrapConfig(await hass.callWS(message));
}

/**
 * Удалить узел — вернуть наследование с вышестоящего уровня.
 * @param {HomeAssistant} hass
 * @param {"object" | "floor" | "room_type" | "area"} scope
 * @param {string | null} key
 * @param {string} mode
 * @returns {Promise<BuildingConfig>}
 */
export async function clearActions(hass, scope, key, mode) {
  /** @type {Record<string, unknown>} */
  const message = { type: `${DOMAIN}/clear_actions`, scope, mode };
  if (key !== null) {
    message.key = key;
  }
  return unwrapConfig(await hass.callWS(message));
}

/**
 * Исключить помещение из управления по расписанию или вернуть (Q3=C).
 * opt-out — политика Оркестратора в .storage, не метка реестра.
 * @param {HomeAssistant} hass
 * @param {string} areaId
 * @param {boolean} opted
 * @returns {Promise<BuildingConfig>}
 */
export async function setOptOut(hass, areaId, opted) {
  return unwrapConfig(
    await hass.callWS({ type: `${DOMAIN}/set_opt_out`, area_id: areaId, opted }),
  );
}

/**
 * Пересобрать снимки и применить каскад заново (сервис, не WS-команда).
 * @param {HomeAssistant} hass
 * @returns {Promise<void>}
 */
export async function reapply(hass) {
  await hass.callService(DOMAIN, "reapply", {});
}

/** @param {unknown} result @returns {BuildingConfig} */
function unwrapConfig(result) {
  if (!isObject(result) || !isObject(result.config)) {
    throw new Error("операция: неожиданный ответ (нет config)");
  }
  return /** @type {BuildingConfig} */ (result.config);
}

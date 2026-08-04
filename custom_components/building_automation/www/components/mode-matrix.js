/**
 * Матрица режимов (ТЗ §9.2, пункты 11–16, 19 плана этапа 9).
 *
 * Правка профилей — только администратору (ТЗ §9.3): при !isAdmin рендерим
 * read-only. Каждая операция точечная (один узел scope+key+mode); пустой список
 * действий = «ничего не делать» (обрывает наследование), «Наследовать» =
 * clear_actions (удалить узел). Разрешение профиля смотрит на НАЛИЧИЕ ключа,
 * а не на его пустоту — отсюда две раздельные операции.
 *
 * Конфиг не хранит: получает от корня, после мутации отдаёт свежий обратно
 * событием config-changed. Ошибки валидации ядра показывает как есть.
 *
 * @typedef {import("../types.js").HomeAssistant} HomeAssistant
 * @typedef {import("../types.js").BuildingConfig} BuildingConfig
 * @typedef {import("../types.js").StateSnapshot} StateSnapshot
 * @typedef {import("../types.js").ActionSpec} ActionSpec
 * @typedef {import("../types.js").ModeSettingsSpec} ModeSettingsSpec
 * @typedef {"object" | "floor" | "room_type" | "area"} Scope
 */

import { LitElement, html, css, nothing } from "../vendor/lit-3.3.3.js";
import { sharedStyles } from "../shared-styles.js";
import { setActions, clearActions, setModeSettings, setOptOut } from "../api.js";

const MODES = ["lesson", "break", "window", "off"];
/** @type {Record<string, string>} */
const MODE_LABELS = {
  lesson: "Урок",
  break: "Перемена",
  window: "Окошко",
  off: "Не рабочее время",
};
/**
 * Вид действия профиля — понятная наладчику подпись вместо сырых домен×сервис.
 * Автояркость (arvid_dali_center.set_autobrightness) кодирует состояние в
 * data.enabled; домен/сервис/enabled должны совпадать с ядром (storage_schema).
 * @typedef {object} ActionKind
 * @property {string} id
 * @property {string} label
 * @property {string} domain
 * @property {string} service
 * @property {boolean} [enabled]
 */
/** @type {ActionKind[]} */
const ACTION_KINDS = [
  { id: "light_on", label: "Свет — включить", domain: "light", service: "turn_on" },
  { id: "light_off", label: "Свет — выключить", domain: "light", service: "turn_off" },
  { id: "switch_on", label: "Реле — включить", domain: "switch", service: "turn_on" },
  {
    id: "switch_off",
    label: "Реле — выключить",
    domain: "switch",
    service: "turn_off",
  },
  {
    id: "autobright_on",
    label: "Автояркость — включить",
    domain: "arvid_dali_center",
    service: "set_autobrightness",
    enabled: true,
  },
  {
    id: "autobright_off",
    label: "Автояркость — выключить",
    domain: "arvid_dali_center",
    service: "set_autobrightness",
    enabled: false,
  },
];
const ROOM_TYPES = ["class", "korridor", "recreation", "zal", "special", "hall"];
/** @type {Record<Scope, string>} */
const SCOPE_LABELS = {
  object: "Объект",
  floor: "Этаж",
  room_type: "Тип помещения",
  area: "Помещение",
};

/** @param {string} mode */
function modeLabel(mode) {
  return MODE_LABELS[mode] ?? mode;
}

/**
 * Значение яркости действия для инпута (пусто, если не задана).
 * @param {ActionSpec} action
 * @returns {string}
 */
function brightnessOf(action) {
  const value = action.data?.brightness_pct;
  return typeof value === "number" ? String(value) : "";
}

/**
 * Глубокая копия узла {mode: Action[]} — черновик не мутирует конфиг.
 * @param {Record<string, ActionSpec[]>} node
 * @returns {Record<string, ActionSpec[]>}
 */
function cloneNode(node) {
  /** @type {Record<string, ActionSpec[]>} */
  const copy = {};
  for (const [mode, actions] of Object.entries(node)) {
    copy[mode] = actions.map((a) => ({
      domain: a.domain,
      service: a.service,
      data: { ...a.data },
    }));
  }
  return copy;
}

/**
 * Вид действия (id из ACTION_KINDS) по сохранённому действию.
 * Для автояркости состояние читается из data.enabled.
 * @param {ActionSpec} action
 * @returns {string}
 */
function kindOf(action) {
  if (
    action.domain === "arvid_dali_center" &&
    action.service === "set_autobrightness"
  ) {
    return action.data?.enabled === false ? "autobright_off" : "autobright_on";
  }
  const match = ACTION_KINDS.find(
    (k) => k.domain === action.domain && k.service === action.service,
  );
  return match ? match.id : "light_off";
}

/**
 * Построить действие для выбранного вида. Яркость сохраняется только при
 * переходе в «Свет — включить»; у автояркости пишем data.enabled.
 * @param {string} kindId
 * @param {Record<string, unknown>} prevData
 * @returns {ActionSpec}
 */
function actionForKind(kindId, prevData) {
  const kind = ACTION_KINDS.find((k) => k.id === kindId);
  if (!kind) {
    return { domain: "light", service: "turn_off", data: {} };
  }
  if (kind.domain === "arvid_dali_center") {
    return {
      domain: kind.domain,
      service: kind.service,
      data: { enabled: kind.enabled === true },
    };
  }
  /** @type {Record<string, unknown>} */
  const data = {};
  if (kindId === "light_on" && typeof prevData.brightness_pct === "number") {
    data.brightness_pct = prevData.brightness_pct;
  }
  return { domain: kind.domain, service: kind.service, data };
}

/**
 * Узел действий {mode: Action[]} для выбранного scope+key из конфига.
 * @param {BuildingConfig} config
 * @param {Scope} scope
 * @param {string | null} key
 * @returns {Record<string, ActionSpec[]>}
 */
function nodeOf(config, scope, key) {
  if (scope === "object") {
    return config.actions.object ?? {};
  }
  const section = config.actions[scope] ?? {};
  return (key !== null ? section[key] : undefined) ?? {};
}

export class BuildingAutomationModeMatrix extends LitElement {
  /** @override */
  static properties = {
    hass: { attribute: false },
    config: { attribute: false },
    snapshot: { attribute: false },
    isAdmin: { attribute: false },
    _scope: { state: true },
    _key: { state: true },
    _error: { state: true },
    _draftNode: { state: true },
  };

  constructor() {
    super();
    /** @type {HomeAssistant | undefined} */
    this.hass = undefined;
    /** @type {BuildingConfig | undefined} */
    this.config = undefined;
    /** @type {StateSnapshot | undefined} */
    this.snapshot = undefined;
    /** @type {boolean} */
    this.isAdmin = false;
    /** @type {Scope} */
    this._scope = "object";
    /** @type {string | null} */
    this._key = null;
    /** @type {string} */
    this._error = "";
    // Реактивный черновик действий выбранного узла {mode: Action[]}. Правки
    // domain/service/яркости идут сюда → перерисовка корректно показывает поле
    // яркости; «Сохранить» пишет черновик, «Наследовать» удаляет узел.
    /** @type {Record<string, ActionSpec[]>} */
    this._draftNode = {};
  }

  /**
   * @override
   * @param {import("../vendor/lit-3.3.3.js").PropertyValues} changed
   */
  willUpdate(changed) {
    // Сбросить черновик из сохранённого конфига при смене узла или конфига
    // (в т.ч. после успешной мутации: parent присылает свежий config).
    if (changed.has("config") || changed.has("_scope") || changed.has("_key")) {
      this._draftNode = this.config
        ? cloneNode(nodeOf(this.config, this._scope, this._key))
        : {};
    }
  }

  /** @returns {string[]} доступные ключи для текущего scope */
  _keyOptions() {
    const snap = this.snapshot;
    if (!snap) {
      return [];
    }
    if (this._scope === "floor") {
      return snap.floors.map((f) => f.floor_id);
    }
    if (this._scope === "area") {
      return snap.rooms.map((r) => r.area_id);
    }
    if (this._scope === "room_type") {
      return ROOM_TYPES;
    }
    return [];
  }

  /** @param {Event} event */
  _onScopeChange(event) {
    const value = /** @type {HTMLSelectElement} */ (event.target).value;
    this._scope = /** @type {Scope} */ (value);
    const options = this._keyOptions();
    this._key = this._scope === "object" ? null : (options[0] ?? null);
  }

  /** @param {Event} event */
  _onKeyChange(event) {
    this._key = /** @type {HTMLSelectElement} */ (event.target).value;
  }

  /** @param {BuildingConfig} config */
  _emitConfig(config) {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: config,
        bubbles: true,
        composed: true,
      }),
    );
  }

  /**
   * @param {() => Promise<BuildingConfig>} operation
   */
  async _run(operation) {
    this._error = "";
    try {
      const config = await operation();
      this._emitConfig(config);
    } catch (err) {
      this._error = err instanceof Error ? err.message : String(err);
    }
  }

  /** @param {string} mode */
  async _saveActions(mode) {
    if (!this.hass) {
      return;
    }
    const hass = this.hass;
    const actions = this._draftNode[mode] ?? [];
    await this._run(() => setActions(hass, this._scope, this._key, mode, actions));
  }

  /** @param {string} mode */
  async _inheritActions(mode) {
    if (!this.hass) {
      return;
    }
    const hass = this.hass;
    await this._run(() => clearActions(hass, this._scope, this._key, mode));
  }

  /**
   * @param {string} areaId
   * @param {boolean} opted
   */
  async _setOptOut(areaId, opted) {
    if (!this.hass) {
      return;
    }
    const hass = this.hass;
    await this._run(() => setOptOut(hass, areaId, opted));
  }

  /**
   * @param {string} mode
   * @param {ModeSettingsSpec} settings
   */
  async _saveModeSettings(mode, settings) {
    if (!this.hass) {
      return;
    }
    const hass = this.hass;
    await this._run(() =>
      setModeSettings(
        hass,
        mode,
        settings.delay_seconds,
        settings.sensors_allowed,
        settings.sensors_allowed_by_floor,
      ),
    );
  }

  /** @override */
  render() {
    if (!this.config || !this.snapshot) {
      return nothing;
    }
    return html`
      ${
        this.isAdmin
          ? nothing
          : html`<div class="notice">
              Только чтение: правка профилей доступна администратору.
            </div>`
      }
      ${
        this._error
          ? html`<div class="banner error">Ошибка: ${this._error}</div>`
          : nothing
      }
      ${this._renderModeSettings(this.config)} ${this._renderNodeEditor()}
    `;
  }

  /** @param {BuildingConfig} config */
  _renderModeSettings(config) {
    const floors = this.snapshot?.floors ?? [];
    return html`
      <div class="card">
        <div class="card-title">Настройки режимов</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Режим</th>
                <th>Задержка, c</th>
                <th>Датчики (по зданию)</th>
                ${floors.map((f) => html`<th>эт. ${f.floor_id}</th>`)}
              </tr>
            </thead>
            <tbody>
              ${MODES.map((mode) => this._renderModeRow(config, mode, floors))}
            </tbody>
          </table>
        </div>
        <div class="hint">
          Датчики на этаже: «наследовать» — по зданию; иначе явное вкл/выкл.
        </div>
      </div>
    `;
  }

  /**
   * @param {BuildingConfig} config
   * @param {string} mode
   * @param {StateSnapshot["floors"]} floors
   */
  _renderModeRow(config, mode, floors) {
    const settings = config.modes[mode] ?? {
      delay_seconds: 0,
      sensors_allowed: true,
      sensors_allowed_by_floor: {},
    };
    const ro = !this.isAdmin;
    /** @param {Partial<ModeSettingsSpec>} patch */
    const commit = (patch) => this._saveModeSettings(mode, { ...settings, ...patch });
    return html`
      <tr>
        <td>${modeLabel(mode)}</td>
        <td>
          <input
            type="number"
            min="0"
            .value=${String(settings.delay_seconds)}
            ?disabled=${ro}
            @change=${(/** @type {Event} */ e) =>
              commit({
                delay_seconds: Number(/** @type {HTMLInputElement} */ (e.target).value),
              })}
          />
        </td>
        <td>
          <input
            type="checkbox"
            .checked=${settings.sensors_allowed}
            ?disabled=${ro}
            @change=${(/** @type {Event} */ e) =>
              commit({
                sensors_allowed: /** @type {HTMLInputElement} */ (e.target).checked,
              })}
          />
        </td>
        ${floors.map((f) => this._renderFloorOverride(mode, settings, f.floor_id, ro))}
      </tr>
    `;
  }

  /**
   * @param {string} mode
   * @param {ModeSettingsSpec} settings
   * @param {string} floorId
   * @param {boolean} ro
   */
  _renderFloorOverride(mode, settings, floorId, ro) {
    const byFloor = settings.sensors_allowed_by_floor ?? {};
    const current = floorId in byFloor ? (byFloor[floorId] ? "on" : "off") : "";
    return html`
      <td>
        <select
          ?disabled=${ro}
          @change=${(/** @type {Event} */ e) => {
            const value = /** @type {HTMLSelectElement} */ (e.target).value;
            const next = { ...byFloor };
            if (value === "") {
              delete next[floorId];
            } else {
              next[floorId] = value === "on";
            }
            this._saveModeSettings(mode, {
              ...settings,
              sensors_allowed_by_floor: next,
            });
          }}
        >
          <option value="" ?selected=${current === ""}>насл.</option>
          <option value="on" ?selected=${current === "on"}>вкл</option>
          <option value="off" ?selected=${current === "off"}>выкл</option>
        </select>
      </td>
    `;
  }

  _renderNodeEditor() {
    const config = this.config;
    if (!config) {
      return nothing;
    }
    const options = this._keyOptions();
    return html`
      <div class="card">
        <div class="card-title">Действия профиля</div>
        <div class="selectors">
          <label>
            Уровень
            <select @change=${(/** @type {Event} */ e) => this._onScopeChange(e)}>
              ${
                /** @type {Scope[]} */ (["object", "floor", "room_type", "area"]).map(
                  (s) => html`
                    <option value=${s} ?selected=${this._scope === s}>
                      ${SCOPE_LABELS[s]}
                    </option>
                  `,
                )
              }
            </select>
          </label>
          ${
            this._scope === "object"
              ? nothing
              : html`
                  <label>
                    ${SCOPE_LABELS[this._scope]}
                    <select @change=${(/** @type {Event} */ e) => this._onKeyChange(e)}>
                      ${options.map(
                        (k) => html`
                          <option value=${k} ?selected=${this._key === k}>${k}</option>
                        `,
                      )}
                    </select>
                  </label>
                `
          }
        </div>
        ${
          this._scope === "area" && this._key !== null
            ? this._renderOptOut(config, this._key)
            : nothing
        }
        ${
          this._scope === "area" && this._key !== null
            ? this._renderEffective(config, this._key)
            : nothing
        }
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Режим</th>
                <th>Состояние</th>
                <th>Действия</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${MODES.map((mode) => this._renderActionRow(mode))}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  /**
   * Тумблер opt-out помещения (Q3=C): исключить из управления по расписанию.
   * @param {BuildingConfig} config
   * @param {string} areaId
   */
  _renderOptOut(config, areaId) {
    const opted = (config.opted_out_areas ?? []).includes(areaId);
    const ro = !this.isAdmin;
    return html`
      <div class="opt-out">
        <label class="inline">
          <input
            type="checkbox"
            .checked=${opted}
            ?disabled=${ro}
            @change=${(/** @type {Event} */ e) =>
              this._setOptOut(
                areaId,
                /** @type {HTMLInputElement} */ (e.target).checked,
              )}
          />
          Исключить помещение из управления по расписанию (opt-out)
        </label>
        ${
          opted
            ? html`<span class="chip accent">исключено — каскад пропускает</span>`
            : nothing
        }
      </div>
    `;
  }

  /**
   * Разрешение для помещения: помещение → тип → этаж → объект (мирроринг ядра).
   * @param {BuildingConfig} config
   * @param {string} areaId
   */
  _renderEffective(config, areaId) {
    const room = this.snapshot?.rooms.find((r) => r.area_id === areaId);
    if (!room) {
      return nothing;
    }
    /** @param {string} mode */
    const winner = (mode) => {
      if (mode in nodeOf(config, "area", areaId)) {
        return "помещение";
      }
      if (room.room_type && mode in nodeOf(config, "room_type", room.room_type)) {
        return `тип: ${room.room_type}`;
      }
      if (mode in nodeOf(config, "floor", room.floor_id)) {
        return `этаж: ${room.floor_id}`;
      }
      if (mode in nodeOf(config, "object", null)) {
        return "объект";
      }
      return "нет действий";
    };
    return html`
      <div class="effective">
        <b>Действует для помещения:</b>
        ${MODES.map(
          (mode) => html`
            <span class="chip">${modeLabel(mode)} → ${winner(mode)}</span>
          `,
        )}
      </div>
    `;
  }

  /** @param {string} mode */
  _renderActionRow(mode) {
    const inDraft = mode in this._draftNode;
    const actions = this._draftNode[mode] ?? [];
    const ro = !this.isAdmin;
    return html`
      <tr>
        <td>${modeLabel(mode)}</td>
        <td>
          ${
            inDraft
              ? html`<span class="chip accent">задано (${actions.length})</span>`
              : html`<span class="chip">наследует</span>`
          }
        </td>
        <td>${this._renderActionList(mode, actions, ro)}</td>
        <td class="actions-col">
          ${
            ro
              ? nothing
              : html`
                  <button @click=${() => this._saveActions(mode)}>Сохранить</button>
                  <button
                    class="secondary"
                    ?disabled=${!inDraft}
                    @click=${() => this._inheritActions(mode)}
                  >
                    Наследовать
                  </button>
                `
          }
        </td>
      </tr>
    `;
  }

  /**
   * @param {string} mode
   * @param {ActionSpec[]} actions
   * @param {boolean} ro
   */
  _renderActionList(mode, actions, ro) {
    return html`
      <div class="action-list">
        ${actions.map((action, index) => {
          const kind = kindOf(action);
          return html`
            <div class="action-row">
              <select
                class="action-kind"
                ?disabled=${ro}
                @change=${(/** @type {Event} */ e) =>
                  this._setKind(
                    mode,
                    index,
                    /** @type {HTMLSelectElement} */ (e.target).value,
                  )}
              >
                ${ACTION_KINDS.map(
                  (k) => html`
                    <option value=${k.id} ?selected=${kind === k.id}>${k.label}</option>
                  `,
                )}
              </select>
              ${
                kind === "light_on"
                  ? html`<input
                      class="action-brightness"
                      type="number"
                      min="1"
                      max="100"
                      placeholder="ярк %"
                      title="Яркость, % (пусто — не задавать)"
                      .value=${brightnessOf(action)}
                      ?disabled=${ro}
                      @change=${(/** @type {Event} */ e) =>
                        this._setBrightness(
                          mode,
                          index,
                          /** @type {HTMLInputElement} */ (e.target).value,
                        )}
                    />`
                  : nothing
              }
              ${
                ro
                  ? nothing
                  : html`<button
                      class="icon"
                      title="Удалить"
                      @click=${() => this._removeAction(mode, index)}
                    >
                      ✕
                    </button>`
              }
            </div>
          `;
        })}
        ${
          ro
            ? nothing
            : html`<button class="secondary" @click=${() => this._addAction(mode)}>
                + действие
              </button>`
        }
        ${
          actions.length === 0 && !ro
            ? html`<div class="hint">
                Пусто + «Сохранить» = «ничего не делать» (обрывает наследование).
              </div>`
            : nothing
        }
      </div>
    `;
  }

  /**
   * Изменить одно действие черновика (иммутабельно → перерисовка).
   * @param {string} mode
   * @param {number} index
   * @param {(action: ActionSpec) => ActionSpec} updater
   */
  _patchAction(mode, index, updater) {
    const actions = this._draftNode[mode] ?? [];
    const next = actions.map((a, i) => (i === index ? updater(a) : a));
    this._draftNode = { ...this._draftNode, [mode]: next };
  }

  /**
   * @param {string} mode
   * @param {number} index
   * @param {string} kindId
   */
  _setKind(mode, index, kindId) {
    this._patchAction(mode, index, (a) => actionForKind(kindId, a.data));
  }

  /**
   * @param {string} mode
   * @param {number} index
   * @param {string} value
   */
  _setBrightness(mode, index, value) {
    this._patchAction(mode, index, (a) => {
      const data = { ...a.data };
      if (value === "") {
        delete data.brightness_pct;
      } else {
        const pct = Number(value);
        if (Number.isFinite(pct)) {
          data.brightness_pct = pct;
        }
      }
      return { ...a, data };
    });
  }

  /** @param {string} mode */
  _addAction(mode) {
    const actions = this._draftNode[mode] ?? [];
    this._draftNode = {
      ...this._draftNode,
      [mode]: [...actions, { domain: "light", service: "turn_off", data: {} }],
    };
  }

  /**
   * @param {string} mode
   * @param {number} index
   */
  _removeAction(mode, index) {
    const actions = this._draftNode[mode] ?? [];
    this._draftNode = {
      ...this._draftNode,
      [mode]: actions.filter((_, i) => i !== index),
    };
  }

  /** @override */
  static styles = [
    sharedStyles,
    css`
      :host {
        display: block;
      }
      .selectors {
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
        margin-bottom: 12px;
      }
      label {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-size: 0.9rem;
        color: var(--secondary-text-color);
      }
      label.inline {
        flex-direction: row;
        align-items: center;
        gap: 8px;
        color: var(--primary-text-color);
        font-size: 0.95rem;
      }
      select,
      input {
        padding: 4px 6px;
        border: 1px solid var(--divider-color, #ccc);
        border-radius: 6px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
      }
      input[type="number"] {
        width: 70px;
      }
      .action-list {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .action-row {
        display: flex;
        gap: 6px;
        align-items: center;
      }
      .action-brightness {
        width: 70px;
      }
      .actions-col {
        display: flex;
        gap: 6px;
        white-space: nowrap;
      }
      button.icon {
        padding: 2px 8px;
        background: var(--error-color, #f44336);
        color: #fff;
      }
      .effective {
        margin: 8px 0 12px;
        font-size: 0.9rem;
      }
      .hint {
        margin-top: 6px;
      }
      .opt-out {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        margin: 8px 0;
      }
    `,
  ];
}

if (!customElements.get("building-automation-mode-matrix")) {
  customElements.define(
    "building-automation-mode-matrix",
    BuildingAutomationModeMatrix,
  );
}

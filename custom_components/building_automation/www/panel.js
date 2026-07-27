/**
 * Корень панели пусконаладчика «Оркестратор здания» (ТЗ §9.2).
 *
 * Держит вкладки Мониторинг / Матрица режимов, грузит снимок и конфиг через WS
 * (api.js) и раздаёт их вниз. Живость мониторинга — без нового Python
 * (PLAN этап 9): смена НАШИХ сущностей в hass или доменное событие на шине
 * планируют дебаунс-перезапрос get_state. Значения показываем из авторитетного
 * снимка ядра, а не парсим роли сущностей.
 *
 * @typedef {import("./types.js").HomeAssistant} HomeAssistant
 * @typedef {import("./types.js").StateSnapshot} StateSnapshot
 * @typedef {import("./types.js").BuildingConfig} BuildingConfig
 * @typedef {import("./vendor/lit-3.3.3.js").PropertyValues} PropertyValues
 */

import { LitElement, html, css } from "./vendor/lit-3.3.3.js";
import { getState, getConfig } from "./api.js";
import "./components/monitoring.js";
import "./components/mode-matrix.js";

const PLATFORM = "building_automation";
const BUS_EVENTS = [
  `${PLATFORM}_mode_changed`,
  `${PLATFORM}_mode_warning`,
  `${PLATFORM}_transition_cancelled`,
];
const REFETCH_DEBOUNCE_MS = 300;

export class BuildingAutomationPanel extends LitElement {
  /** @override */
  static properties = {
    hass: { attribute: false },
    narrow: { type: Boolean },
    _tab: { state: true },
    _snapshot: { state: true },
    _config: { state: true },
    _error: { state: true },
    _loading: { state: true },
  };

  constructor() {
    super();
    // Начальные значения — в конструкторе, НЕ полями класса: нативные поля
    // класса затеняют реактивные аксессоры Lit (сборки нет, семантика [[Define]]).
    /** @type {HomeAssistant | undefined} */
    this.hass = undefined;
    /** @type {boolean} */
    this.narrow = false;
    /** @type {"monitoring" | "matrix"} */
    this._tab = "monitoring";
    /** @type {StateSnapshot | undefined} */
    this._snapshot = undefined;
    /** @type {BuildingConfig | undefined} */
    this._config = undefined;
    /** @type {string} */
    this._error = "";
    /** @type {boolean} */
    this._loading = true;
    /** @type {Array<() => void>} */
    this._unsubs = [];
    /** @type {string[]} */
    this._watched = [];
    /** @type {boolean} */
    this._watchedComputed = false;
    /** @type {number | undefined} */
    this._refetchTimer = undefined;
  }

  /** @override */
  async connectedCallback() {
    super.connectedCallback();
    await this._subscribeBus();
    await this._loadAll();
  }

  /** @override */
  disconnectedCallback() {
    super.disconnectedCallback();
    for (const unsub of this._unsubs) {
      unsub();
    }
    this._unsubs = [];
    if (this._refetchTimer !== undefined) {
      clearTimeout(this._refetchTimer);
      this._refetchTimer = undefined;
    }
  }

  /**
   * @override
   * @param {PropertyValues} changed
   */
  shouldUpdate(changed) {
    if (changed.has("hass")) {
      this._ensureWatched();
      const prev = /** @type {HomeAssistant | undefined} */ (changed.get("hass"));
      if (prev && this.hass && this._watchedChanged(prev, this.hass)) {
        this._scheduleRefetch();
      }
    }
    // Рендерим только на изменение своего состояния — не на каждый hass из дома.
    for (const key of changed.keys()) {
      if (key !== "hass") {
        return true;
      }
    }
    return false;
  }

  _ensureWatched() {
    if (this._watchedComputed || !this.hass?.entities) {
      return;
    }
    // Один раз: список НАШИХ сущностей. Дальше сравнение — O(наши), не O(дом).
    this._watched = Object.values(this.hass.entities)
      .filter((entry) => entry.platform === PLATFORM)
      .map((entry) => entry.entity_id);
    this._watchedComputed = true;
  }

  /**
   * @param {HomeAssistant} prev
   * @param {HomeAssistant} next
   * @returns {boolean}
   */
  _watchedChanged(prev, next) {
    return this._watched.some((id) => prev.states[id] !== next.states[id]);
  }

  _scheduleRefetch() {
    if (this._refetchTimer !== undefined) {
      return; // уже запланировано в текущем окне
    }
    this._refetchTimer = window.setTimeout(() => {
      this._refetchTimer = undefined;
      void this._loadState();
    }, REFETCH_DEBOUNCE_MS);
  }

  async _subscribeBus() {
    for (const eventType of BUS_EVENTS) {
      if (!this.hass) {
        return;
      }
      const unsub = await this.hass.connection.subscribeEvents(
        () => this._scheduleRefetch(),
        eventType,
      );
      if (!this.isConnected) {
        unsub(); // отключили пока ждали промис — снимаем сразу (§4)
        return;
      }
      this._unsubs.push(unsub);
    }
  }

  async _loadAll() {
    if (!this.hass) {
      return;
    }
    this._loading = true;
    this._error = "";
    try {
      const [config, snapshot] = await Promise.all([
        getConfig(this.hass),
        getState(this.hass),
      ]);
      this._config = config;
      this._snapshot = snapshot;
    } catch (err) {
      this._error = err instanceof Error ? err.message : String(err);
    } finally {
      this._loading = false;
    }
  }

  async _loadState() {
    if (!this.hass) {
      return;
    }
    try {
      this._snapshot = await getState(this.hass);
      this._error = "";
    } catch (err) {
      this._error = err instanceof Error ? err.message : String(err);
    }
  }

  /** @param {"monitoring" | "matrix"} tab */
  _selectTab(tab) {
    this._tab = tab;
  }

  /** @override */
  render() {
    const isAdmin = this.hass?.user?.is_admin ?? false;
    return html`
      <div class="header">
        <div class="title">Оркестратор здания</div>
        <div class="tabs">
          <button
            class="tab ${this._tab === "monitoring" ? "active" : ""}"
            @click=${() => this._selectTab("monitoring")}
          >
            Мониторинг
          </button>
          <button
            class="tab ${this._tab === "matrix" ? "active" : ""}"
            @click=${() => this._selectTab("matrix")}
          >
            Матрица режимов
          </button>
        </div>
      </div>
      <div class="content">${this._renderBody(isAdmin)}</div>
    `;
  }

  /** @param {boolean} isAdmin */
  _renderBody(isAdmin) {
    if (this._error) {
      return html`<div class="banner error">Ошибка: ${this._error}</div>`;
    }
    if (this._loading || !this._snapshot || !this.hass) {
      return html`<div class="banner">Загрузка…</div>`;
    }
    if (this._tab === "monitoring") {
      return html`
        <building-automation-monitoring
          .hass=${this.hass}
          .snapshot=${this._snapshot}
        ></building-automation-monitoring>
      `;
    }
    if (!this._config) {
      return html`<div class="banner">Загрузка конфигурации…</div>`;
    }
    return html`
      <building-automation-mode-matrix
        .hass=${this.hass}
        .config=${this._config}
        .snapshot=${this._snapshot}
        .isAdmin=${isAdmin}
        @config-changed=${(/** @type {Event} */ e) => this._onConfigChanged(e)}
      ></building-automation-mode-matrix>
    `;
  }

  /** @param {Event} event */
  _onConfigChanged(event) {
    this._config = /** @type {CustomEvent<BuildingConfig>} */ (event).detail;
  }

  /** @override */
  static styles = css`
    :host {
      display: block;
      padding: 16px;
      color: var(--primary-text-color);
      background: var(--primary-background-color);
      min-height: 100%;
      box-sizing: border-box;
      font-family: var(--paper-font-body1_-_font-family, sans-serif);
    }
    .header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 16px;
      margin-bottom: 16px;
    }
    .title {
      font-size: 1.4rem;
      font-weight: 500;
    }
    .tabs {
      display: flex;
      gap: 4px;
    }
    .tab {
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--secondary-text-color);
      padding: 8px 12px;
      cursor: pointer;
      font-size: 1rem;
    }
    .tab.active {
      color: var(--primary-color);
      border-bottom-color: var(--primary-color);
    }
    .banner {
      padding: 16px;
      color: var(--secondary-text-color);
    }
    .banner.error {
      color: var(--error-color);
    }
  `;
}

if (!customElements.get("building-automation-panel")) {
  customElements.define("building-automation-panel", BuildingAutomationPanel);
}

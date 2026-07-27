/**
 * Мониторинг Оркестратора (ТЗ §9.2, пункты 1–10 плана этапа 9).
 *
 * Только читает авторитетный снимок (`snapshot`) и переключает режимы через WS
 * (доступно всем, ТЗ §9.3). Данные не кэширует: их пересобирает и раздаёт корень
 * панели. Действия меняют сущности select/switch → корень видит это и
 * перезапрашивает снимок.
 *
 * @typedef {import("../types.js").HomeAssistant} HomeAssistant
 * @typedef {import("../types.js").StateSnapshot} StateSnapshot
 * @typedef {import("../types.js").FloorInfo} FloorInfo
 * @typedef {import("../types.js").RoomInfo} RoomInfo
 */

import { LitElement, html, css, nothing } from "../vendor/lit-3.3.3.js";
import { setControlMode, reapply } from "../api.js";

/** @type {Record<string, string>} */
const MODE_LABELS = {
  lesson: "Урок",
  break: "Перемена",
  window: "Окошко",
  off: "Не рабочее время",
};

/** @type {Record<string, string>} */
const STATUS_LABELS = {
  ok: "OK",
  no_light: "нет света",
  multiple_lights: "несколько светильников",
};

/** @type {Record<string, string>} */
const SKIP_LABELS = {
  building_manual: "ручной режим здания",
  floor_manual: "ручной режим этажа",
  opt_out: "исключено (opt-out)",
  orphaned: "осиротевший профиль",
  invariant_broken: "нарушен инвариант Area",
};

/** @param {string | null} mode */
function modeLabel(mode) {
  if (mode === null) {
    return "—";
  }
  return MODE_LABELS[mode] ?? mode;
}

export class BuildingAutomationMonitoring extends LitElement {
  /** @override */
  static properties = {
    hass: { attribute: false },
    snapshot: { attribute: false },
    _actionError: { state: true },
  };

  constructor() {
    super();
    // Значения — в конструкторе, не полями класса (иначе затеняют аксессоры Lit).
    /** @type {HomeAssistant | undefined} */
    this.hass = undefined;
    /** @type {StateSnapshot | undefined} */
    this.snapshot = undefined;
    /** @type {string} */
    this._actionError = "";
  }

  /**
   * @param {"building" | "floor"} target
   * @param {"auto" | "manual"} mode
   * @param {string} [floorId]
   */
  async _setMode(target, mode, floorId) {
    if (!this.hass) {
      return;
    }
    this._actionError = "";
    try {
      await setControlMode(this.hass, target, mode, floorId);
    } catch (err) {
      this._actionError = err instanceof Error ? err.message : String(err);
    }
  }

  async _reapply() {
    if (!this.hass) {
      return;
    }
    this._actionError = "";
    try {
      await reapply(this.hass);
    } catch (err) {
      this._actionError = err instanceof Error ? err.message : String(err);
    }
  }

  /** @override */
  render() {
    const s = this.snapshot;
    if (!s) {
      return nothing;
    }
    return html`
      ${
        this._actionError
          ? html`<div class="banner error">Ошибка: ${this._actionError}</div>`
          : nothing
      }
      ${this._renderBuilding(s)} ${this._renderFloors(s.floors)}
      ${this._renderRooms(s.rooms, s.floors)} ${this._renderPlan(s)}
      ${this._renderOrphaned(s.orphaned)}
    `;
  }

  /** @param {StateSnapshot} s */
  _renderBuilding(s) {
    const manual = s.building_control === "manual";
    return html`
      <div class="card">
        <div class="card-title">Здание</div>
        <div class="row">
          <span>Режим управления</span>
          <span class="controls">
            <span class="badge ${manual ? "warn" : "ok"}">
              ${manual ? "Ручной" : "Авто"}
            </span>
            <button
              @click=${() => this._setMode("building", manual ? "auto" : "manual")}
            >
              ${manual ? "Вернуть в Авто" : "Перевести в Ручной"}
            </button>
          </span>
        </div>
        <div class="row">
          <span>Режим расписания</span>
          <span>
            ${modeLabel(s.schedule_mode)}
            ${
              s.source_available
                ? nothing
                : html`<span class="badge warn">источник недоступен</span>`
            }
          </span>
        </div>
        <div class="row">
          <span>Применённый режим</span><span>${modeLabel(s.applied_mode)}</span>
        </div>
        <div class="row">
          <span>Отложенный переход</span>
          <span>
            ${
              s.pending
                ? html`→ ${modeLabel(s.pending.target_mode)}
                    <span class="badge">ожидает применения</span>`
                : "нет"
            }
          </span>
        </div>
        <div class="row">
          <button @click=${() => this._reapply()}>Применить повторно</button>
        </div>
      </div>
    `;
  }

  /** @param {FloorInfo[]} floors */
  _renderFloors(floors) {
    return html`
      <div class="card">
        <div class="card-title">Этажи</div>
        <table>
          <thead>
            <tr>
              <th>Этаж</th>
              <th>Управление</th>
              <th>Датчики</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${floors.map((f) => {
              const manual = f.control === "manual";
              return html`
                <tr>
                  <td>${f.floor_id}</td>
                  <td>
                    <span class="badge ${manual ? "warn" : "ok"}">
                      ${manual ? "Ручной" : "Авто"}
                    </span>
                  </td>
                  <td>
                    <span class="badge ${f.gate ? "ok" : "muted"}">
                      ${f.gate ? "включены" : "выключены"}
                    </span>
                  </td>
                  <td>
                    <button
                      @click=${() =>
                        this._setMode("floor", manual ? "auto" : "manual", f.floor_id)}
                    >
                      ${manual ? "В Авто" : "В Ручной"}
                    </button>
                  </td>
                </tr>
              `;
            })}
          </tbody>
        </table>
      </div>
    `;
  }

  /**
   * @param {RoomInfo[]} rooms
   * @param {FloorInfo[]} floors
   */
  _renderRooms(rooms, floors) {
    // Гейт вычисляется на этаж; помещение следует гейту своего этажа.
    const gateByFloor = new Map(floors.map((f) => [f.floor_id, f.gate]));
    return html`
      <div class="card">
        <div class="card-title">Помещения (${rooms.length})</div>
        <table>
          <thead>
            <tr>
              <th>Area</th>
              <th>Этаж</th>
              <th>Тип</th>
              <th>Датчики</th>
              <th>Инвариант</th>
              <th>opt-out</th>
            </tr>
          </thead>
          <tbody>
            ${rooms.map((r) => {
              const gate = gateByFloor.get(r.floor_id);
              return html`
                <tr>
                  <td>${r.area_id}</td>
                  <td>${r.floor_id}</td>
                  <td>${r.room_type ?? "—"}</td>
                  <td>
                    ${
                      gate === undefined
                        ? "—"
                        : html`<span class="badge ${gate ? "ok" : "muted"}">
                            ${gate ? "включены" : "выключены"}
                          </span>`
                    }
                  </td>
                  <td>
                    <span class="badge ${r.status === "ok" ? "ok" : "error"}">
                      ${STATUS_LABELS[r.status] ?? r.status}
                    </span>
                  </td>
                  <td>${r.opt_out ? "да" : "—"}</td>
                </tr>
              `;
            })}
          </tbody>
        </table>
      </div>
    `;
  }

  /** @param {StateSnapshot} s */
  _renderPlan(s) {
    const plan = s.last_plan;
    if (!plan) {
      return html`
        <div class="card">
          <div class="card-title">Последний каскад</div>
          <div class="muted-text">ещё не применялся</div>
        </div>
      `;
    }
    const prevMode = plan.previous_mode;
    const toMode = plan.applied_mode;
    const transition =
      prevMode !== null && prevMode !== toMode
        ? html`${modeLabel(prevMode)} → ${modeLabel(toMode)}`
        : modeLabel(toMode);
    return html`
      <div class="card">
        <div class="card-title">Последний каскад</div>
        <div class="row">
          <span>Переход режима</span>
          <span><b>${transition}</b></span>
        </div>
        <div class="row">
          <span>Схлопывание</span>
          <span>
            этажей: <b>${plan.collapse.floor}</b>, помещений:
            <b>${plan.collapse.area}</b>
          </span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Цель</th>
              <th>Действие</th>
              <th>Уровень</th>
            </tr>
          </thead>
          <tbody>
            ${plan.commands.map(
              (c) => html`
                <tr>
                  <td>${c.target_area_id}</td>
                  <td>${c.domain}.${c.service}</td>
                  <td>${c.level === "floor" ? "этаж" : "помещение"}</td>
                </tr>
              `,
            )}
          </tbody>
        </table>
        ${
          plan.skipped.length
            ? html`
                <div class="card-subtitle">Пропущены</div>
                <ul>
                  ${plan.skipped.map(
                    (sk) => html`
                      <li>${sk.area_id} — ${SKIP_LABELS[sk.reason] ?? sk.reason}</li>
                    `,
                  )}
                </ul>
              `
            : nothing
        }
      </div>
    `;
  }

  /** @param {StateSnapshot["orphaned"]} orphaned */
  _renderOrphaned(orphaned) {
    const total = orphaned.areas.length + orphaned.floors.length;
    if (total === 0) {
      return nothing;
    }
    return html`
      <div class="card">
        <div class="card-title">Осиротевшие профили</div>
        <div class="muted-text">
          Профили ссылаются на исчезнувшие узлы — сохранены, но не применяются.
        </div>
        ${
          orphaned.areas.length
            ? html`<div class="row">
                <span>Area</span><span>${orphaned.areas.join(", ")}</span>
              </div>`
            : nothing
        }
        ${
          orphaned.floors.length
            ? html`<div class="row">
                <span>Этажи</span><span>${orphaned.floors.join(", ")}</span>
              </div>`
            : nothing
        }
      </div>
    `;
  }

  /** @override */
  static styles = css`
    :host {
      display: block;
    }
    .card {
      background: var(--card-background-color, var(--ha-card-background, #fff));
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.1));
    }
    .card-title {
      font-size: 1.1rem;
      font-weight: 500;
      margin-bottom: 12px;
    }
    .card-subtitle {
      font-weight: 500;
      margin: 12px 0 4px;
    }
    .row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 6px 0;
      border-bottom: 1px solid var(--divider-color, #eee);
    }
    .row:last-child {
      border-bottom: none;
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }
    th,
    td {
      text-align: left;
      padding: 6px 8px;
      border-bottom: 1px solid var(--divider-color, #eee);
    }
    th {
      color: var(--secondary-text-color);
      font-weight: 500;
    }
    button {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border: none;
      border-radius: 8px;
      padding: 6px 12px;
      cursor: pointer;
      font-size: 0.9rem;
    }
    button:hover {
      opacity: 0.9;
    }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.85rem;
      background: var(--divider-color, #eee);
      color: var(--primary-text-color);
    }
    .badge.ok {
      background: var(--success-color, #4caf50);
      color: #fff;
    }
    .badge.warn {
      background: var(--warning-color, #ff9800);
      color: #fff;
    }
    .badge.error {
      background: var(--error-color, #f44336);
      color: #fff;
    }
    .badge.muted {
      background: var(--divider-color, #eee);
      color: var(--secondary-text-color);
    }
    .muted-text {
      color: var(--secondary-text-color);
      font-size: 0.9rem;
    }
    .banner.error {
      color: var(--error-color);
      padding: 8px 0;
    }
    ul {
      margin: 4px 0;
      padding-left: 20px;
    }
  `;
}

if (!customElements.get("building-automation-monitoring")) {
  customElements.define("building-automation-monitoring", BuildingAutomationMonitoring);
}

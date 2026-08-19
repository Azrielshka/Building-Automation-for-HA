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
import { sharedStyles } from "../shared-styles.js";
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

/**
 * Режим как нейтральная пилюля (E5: единообразно, без «ёлочки»).
 * @param {string | null} mode
 */
function modeBadge(mode) {
  return html`<span class="badge mode">${modeLabel(mode)}</span>`;
}

/**
 * Состояние автояркости помещения как бейдж (этап 11).
 * @param {string | null} state  "on" | "off" | "mixed" | null (нет тумблеров)
 */
function autobrightnessBadge(state) {
  if (state === "on") {
    return html`<span class="badge ok">вкл</span>`;
  }
  if (state === "off") {
    return html`<span class="badge off">выкл</span>`;
  }
  if (state === "mixed") {
    return html`<span class="badge attention">смешано</span>`;
  }
  return html`—`;
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
      ${this._renderBuilding(s)}
      ${this._renderFloors(s.floors, s.building_control === "manual")}
      ${this._renderRooms(s.rooms, s.floors)} ${this._renderPlan(s)}
      ${this._renderOrphaned(s.orphaned)}
    `;
  }

  /**
   * Цвет индикатора источника: серый — недоступен/нет; красный — «off»;
   * зелёный — доступен. Читаем живое состояние из hass (корень держит источник
   * в watched → dot обновляется).
   * @param {string} entityId
   * @returns {"green" | "red" | "grey"}
   */
  _sourceColor(entityId) {
    const st = this.hass?.states[entityId];
    if (!st || st.state === "unavailable" || st.state === "unknown") {
      return "grey";
    }
    return st.state === "off" ? "red" : "green";
  }

  /** @param {string} entityId */
  _sourceTitle(entityId) {
    const st = this.hass?.states[entityId];
    return st ? `состояние: ${st.state}` : "недоступен";
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
            <span class="badge ${manual ? "attention" : "ok"}">
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
          <span class="controls">
            ${modeBadge(s.schedule_mode)}
            ${
              s.source_available
                ? nothing
                : html`<span class="badge attention">источник недоступен</span>`
            }
            ${
              s.schedule_gap
                ? html`<span
                    class="badge attention"
                    title="Активного события нет — режим держится по последнему завершившемуся (дырка в расписании или момент после перезапуска)"
                    >нет активного события</span
                  >`
                : nothing
            }
          </span>
        </div>
        <div class="row">
          <span>Объект расписания</span>
          <span class="sources">
            ${
              s.schedule_source.length === 0
                ? "—"
                : s.schedule_source.map(
                    (id) => html`
                      <span class="source">
                        <span
                          class="dot ${this._sourceColor(id)}"
                          title=${this._sourceTitle(id)}
                          aria-label=${this._sourceTitle(id)}
                        ></span>
                        <code>${id}</code>
                      </span>
                    `,
                  )
            }
          </span>
        </div>
        <div class="row">
          <span>Применённый режим</span><span>${modeBadge(s.applied_mode)}</span>
        </div>
        <div class="row">
          <span>Отложенный переход</span>
          <span>
            ${
              s.pending
                ? html`→ ${modeBadge(s.pending.target_mode)}
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

  /**
   * @param {FloorInfo[]} floors
   * @param {boolean} buildingManual  здание в Ручном — глушит гейты всех этажей
   */
  _renderFloors(floors, buildingManual) {
    return html`
      <div class="card">
        <div class="card-title">Этажи</div>
        <div class="table-wrap">
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
                      <span class="badge ${manual ? "attention" : "ok"}">
                        ${manual ? "Ручной" : "Авто"}
                      </span>
                      ${
                        buildingManual
                          ? html`<span class="muted-note">· здание: Ручной</span>`
                          : nothing
                      }
                    </td>
                    <td>
                      <span class="badge ${f.gate ? "ok" : "off"}">
                        ${f.gate ? "включены" : "выключены"}
                      </span>
                    </td>
                    <td>
                      <button
                        @click=${() =>
                          this._setMode(
                            "floor",
                            manual ? "auto" : "manual",
                            f.floor_id,
                          )}
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
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Area</th>
                <th>Этаж</th>
                <th>Тип</th>
                <th>Датчики</th>
                <th>Автояркость</th>
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
                          : html`<span class="badge ${gate ? "ok" : "off"}">
                              ${gate ? "включены" : "выключены"}
                            </span>`
                      }
                    </td>
                    <td>${autobrightnessBadge(r.autobrightness)}</td>
                    <td>
                      <span class="badge ${r.status === "ok" ? "ok" : "alert"}">
                        ${STATUS_LABELS[r.status] ?? r.status}
                      </span>
                    </td>
                    <td>
                      ${r.opt_out ? html`<span class="badge accent">да</span>` : "—"}
                    </td>
                  </tr>
                `;
              })}
            </tbody>
          </table>
        </div>
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
        ? html`${modeBadge(prevMode)} → ${modeBadge(toMode)}`
        : modeBadge(toMode);
    return html`
      <div class="card">
        <div class="card-title">Последний каскад</div>
        <div class="row"><span>Переход режима</span><span>${transition}</span></div>
        <div class="row">
          <span>Схлопывание</span>
          <span>
            этажей: <b>${plan.collapse.floor}</b>, помещений:
            <b>${plan.collapse.area}</b>
          </span>
        </div>
        <div class="table-wrap">
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
                    <td><code>${c.target}</code></td>
                    <td>${c.domain}.${c.service}</td>
                    <td>${c.level === "floor" ? "этаж" : "помещение"}</td>
                  </tr>
                `,
              )}
            </tbody>
          </table>
        </div>
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
  static styles = [
    sharedStyles,
    css`
      :host {
        display: block;
      }
      .controls {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }
      .sources {
        display: flex;
        flex-direction: column;
        gap: 4px;
        align-items: flex-end;
      }
      .source {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .source code {
        font-size: 0.85rem;
        color: var(--secondary-text-color);
      }
      .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        flex: 0 0 auto;
        animation: ba-blink 1.4s ease-in-out infinite;
      }
      .dot.green {
        background: var(--success-color, #4caf50);
      }
      .dot.red {
        background: var(--error-color, #f44336);
      }
      .dot.grey {
        background: var(--disabled-text-color, #9e9e9e);
      }
      @keyframes ba-blink {
        0%,
        100% {
          opacity: 1;
        }
        50% {
          opacity: 0.25;
        }
      }
      .muted-note {
        color: var(--secondary-text-color);
        font-size: 0.85rem;
        margin-left: 4px;
      }
      ul {
        margin: 4px 0;
        padding-left: 20px;
      }
    `,
  ];
}

if (!customElements.get("building-automation-monitoring")) {
  customElements.define("building-automation-monitoring", BuildingAutomationMonitoring);
}

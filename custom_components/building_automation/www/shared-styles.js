/**
 * Общие стили панели (единый визуальный язык карточек, бейджей, таблиц).
 * Импортируется компонентами: `static styles = [sharedStyles, css`...`]`.
 *
 * Принцип цвета = сигнал: нормальные состояния — нейтральные, насыщенный цвет
 * только у отклонений (Ручной, нарушенный инвариант, исключения). Бейджи —
 * тонированный фон + цветной текст (тише и контрастнее сплошной заливки).
 */

import { css } from "./vendor/lit-3.3.3.js";

export const sharedStyles = css`
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

  /* Строки «ключ — значение» */
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
    border-bottom: 1px solid var(--divider-color, #eee);
  }
  .row:last-child {
    border-bottom: none;
  }

  /* Таблицы: горизонтальный скролл на узком (C), зебра/hover (E3) */
  .table-wrap {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.95rem;
  }
  th,
  td {
    text-align: left;
    padding: 7px 8px;
    border-bottom: 1px solid var(--divider-color, #eee);
    vertical-align: top;
    white-space: nowrap;
  }
  th {
    color: var(--secondary-text-color);
    font-weight: 500;
  }
  tbody tr:nth-child(even) td {
    background: color-mix(in srgb, var(--primary-text-color, #000) 3%, transparent);
  }
  tbody tr:hover td {
    background: color-mix(in srgb, var(--primary-color, #03a9f4) 8%, transparent);
  }

  /* Бейджи: нейтральный по умолчанию, цвет — только сигнал (A/F) */
  .badge,
  .chip {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 12px;
    font-size: 0.85rem;
    background: var(--divider-color, #e6e6e6);
    color: var(--secondary-text-color);
    white-space: nowrap;
  }
  .chip {
    margin: 2px;
  }
  .badge.ok,
  .chip.ok {
    background: color-mix(in srgb, var(--success-color, #43a047) 18%, transparent);
    color: var(--success-color, #2e7d32);
  }
  .badge.attention,
  .chip.attention {
    background: color-mix(in srgb, var(--warning-color, #ffa726) 20%, transparent);
    color: var(--warning-color, #b26a00);
  }
  .badge.alert,
  .chip.alert {
    background: color-mix(in srgb, var(--error-color, #f44336) 16%, transparent);
    color: var(--error-color, #d32f2f);
  }
  .badge.accent,
  .chip.accent {
    background: color-mix(in srgb, var(--primary-color, #03a9f4) 16%, transparent);
    color: var(--primary-color, #0277bd);
  }
  .badge.off {
    background: color-mix(
      in srgb,
      var(--secondary-text-color, #9e9e9e) 14%,
      transparent
    );
    color: var(--secondary-text-color);
  }
  /* Режим-пилюля — нейтральная, чуть плотнее фон, без «ёлочки» (E5) */
  .badge.mode {
    background: color-mix(in srgb, var(--primary-text-color, #000) 8%, transparent);
    color: var(--primary-text-color);
  }

  /* Кнопки */
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
  button.secondary {
    background: var(--secondary-background-color, #e0e0e0);
    color: var(--primary-text-color);
  }
  button[disabled] {
    opacity: 0.5;
    cursor: default;
  }

  .hint,
  .muted-text {
    color: var(--secondary-text-color);
    font-size: 0.85rem;
  }
  .banner {
    padding: 16px;
    color: var(--secondary-text-color);
  }
  .banner.error {
    color: var(--error-color);
    padding: 8px 0;
  }
  .notice {
    padding: 8px 12px;
    margin-bottom: 12px;
    border-radius: 8px;
    background: var(--secondary-background-color, #eee);
    color: var(--secondary-text-color);
  }
`;

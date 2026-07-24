"""Адаптер таймера: `TimerOp` ядра → `async_call_later` (SPEC §2.3, этап 7a).

Ровно **один** отложенный переход на здание (решение §7.4): держим единственную
отписку. `SetTimer` снимает прежний таймер и заводит новый; `CancelTimer` снимает;
`NoTimerOp` не трогает. `apply_at` — абсолютный момент, задержку для
`async_call_later` вычисляем как `apply_at - now` (не меньше нуля).

Грузится только в среде HA; ядро его не импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later

from ..domain.types import CancelTimer, SetTimer

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from homeassistant.core import HomeAssistant

    from ..domain.types import Instant, TimerOp


class DelayedTransitionTimer:
    """Единственный таймер отложенного перехода, привязанный к жизни entry."""

    def __init__(self) -> None:
        """Создать таймер без активной отписки."""
        self._unsub: Callable[[], None] | None = None

    def apply(
        self,
        hass: HomeAssistant,
        op: TimerOp,
        now: Instant,
        on_fire: Callable[[], None],
    ) -> None:
        """Применить операцию с таймером из решения машины."""
        if isinstance(op, SetTimer):
            self.cancel()
            delay = max(0.0, op.apply_at - now)

            # Колбэк должен быть @callback, иначе HA исполнит его в executor-
            # потоке, откуда планирование задач в петле недопустимо.
            @callback
            def _fire(_now: datetime) -> None:
                on_fire()

            self._unsub = async_call_later(hass, delay, _fire)
        elif isinstance(op, CancelTimer):
            self.cancel()
        # NoTimerOp — оставить как есть.

    def cancel(self) -> None:
        """Снять активный таймер, если есть (идемпотентно)."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

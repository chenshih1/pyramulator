"""Hardware primitives for DES: clocks, components, FIFOs, pipeline stages.

Components own a :class:`Clock` and use it to convert cycle counts into
simulator time; :class:`FIFO` and :class:`Pipe` are the basic building
blocks for dataflow between components.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from .sim import Simulator


class Clock:
    """Hardware clock: period in simulator time units (ps).

    Time in the simulator is an integer count of picoseconds; a clock
    with ``period_ps=N`` advances N time units per cycle.
    """

    def __init__(self, period_ps: int, name: str = "clk") -> None:
        if period_ps <= 0:
            raise ValueError(f"clock period must be positive, got {period_ps}")
        self.period_ps = period_ps
        self.name = name

    def cycles(self, count: int) -> int:
        """Simulator time for *count* cycles of this clock."""
        if count < 0:
            raise ValueError(f"negative cycle count {count}")
        return count * self.period_ps

    def __repr__(self) -> str:
        return f"Clock({self.name!r}, {self.period_ps}ps)"


class Component:
    """Base class for DES hardware components.

    Subclasses own a :class:`Simulator` and a :class:`Clock`; the
    ``schedule_*`` helpers convert delays into simulator time.
    """

    def __init__(self, sim: Simulator, clk: Clock, name: str) -> None:
        self.sim = sim
        self.clk = clk
        self.name = name

    def schedule_cycles(
        self, delay_cycles: int, callback: Callable[[], None], priority: int = 0
    ) -> int:
        """Schedule *callback* after *delay_cycles* of this clock.

        The event is attributed to this component in ``sim.event_counts``."""
        return self.sim.schedule(
            self.clk.cycles(delay_cycles), callback, priority, source=self.name
        )

    def schedule_ps(
        self, delay_ps: int, callback: Callable[[], None], priority: int = 0
    ) -> int:
        """Schedule *callback* after *delay_ps* time units.

        The event is attributed to this component in ``sim.event_counts``."""
        return self.sim.schedule(delay_ps, callback, priority, source=self.name)

    def reset(self) -> None:
        """Hook for resetting component state; default no-op."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"


class FIFO(Component):
    """Bounded FIFO with combinational (immediate) put/get semantics.

    State changes take effect as soon as the owning component calls
    :meth:`put` / :meth:`get` while processing an event; there is no
    register delay (use :class:`Pipe` for a clocked stage).
    """

    def __init__(
        self, sim: Simulator, clk: Clock, capacity: int, name: str = "fifo"
    ) -> None:
        if capacity < 1:
            raise ValueError(f"FIFO capacity must be positive, got {capacity}")
        super().__init__(sim, clk, name)
        self._capacity = capacity
        self._q: deque[Any] = deque()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def level(self) -> int:
        return len(self._q)

    @property
    def full(self) -> bool:
        return len(self._q) >= self._capacity

    @property
    def empty(self) -> bool:
        return not self._q

    def can_put(self) -> bool:
        return not self.full

    def put(self, item: Any) -> bool:
        """Enqueue *item*; False if the FIFO is full."""
        if self.full:
            return False
        self._q.append(item)
        return True

    def can_get(self) -> bool:
        return not self.empty

    def get(self) -> Any:
        """Dequeue and return the oldest item; IndexError if empty."""
        return self._q.popleft()

    def peek(self) -> Any | None:
        """Oldest item without dequeuing; None if empty."""
        return self._q[0] if self._q else None

    def clear(self) -> None:
        self._q.clear()


class Pipe(Component):
    """Fixed-latency pipeline stage with bounded occupancy.

    :meth:`put` accepts an item and schedules its delivery to the
    *consumer* exactly ``latency_cycles`` of the component clock later.
    At most ``slots`` items may be in flight; :meth:`put` returns False
    when the stage is full.

    The consumer may stall the stage by returning ``False``: the item
    stays in the last pipeline register and delivery is retried every
    cycle until accepted (any other return value, including ``None``,
    accepts the item). A consumer that never accepts stalls the stage —
    and with it the simulator — forever.
    """

    def __init__(
        self,
        sim: Simulator,
        clk: Clock,
        latency_cycles: int,
        slots: int = 1,
        consumer: Callable[[Any], bool | None] | None = None,
        name: str = "pipe",
    ) -> None:
        if latency_cycles < 1:
            raise ValueError(
                f"pipe latency must be at least 1 cycle, got {latency_cycles}"
            )
        if slots < 1:
            raise ValueError(f"pipe slots must be positive, got {slots}")
        if consumer is None:
            raise ValueError("pipe requires a consumer callback")
        super().__init__(sim, clk, name)
        self._latency_cycles = latency_cycles
        self._slots = slots
        self._consumer = consumer
        self._in_flight = 0
        self._stalled: deque[Any] = deque()
        self._retry_eid: int | None = None

    @property
    def latency_cycles(self) -> int:
        return self._latency_cycles

    @property
    def slots(self) -> int:
        return self._slots

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @property
    def full(self) -> bool:
        return self._in_flight >= self._slots

    def can_put(self) -> bool:
        return not self.full

    def put(self, item: Any) -> bool:
        """Accept *item*, delivering it to the consumer after the latency.

        False if the stage is full (call again later)."""
        if self.full:
            return False
        self._in_flight += 1
        self.schedule_cycles(self._latency_cycles, lambda: self._deliver(item))
        return True

    def _deliver(self, item: Any) -> None:
        if self._consumer(item) is False:
            # Downstream is stalled: queue the item and schedule a shared
            # retry event if one is not already pending.
            self._stalled.append(item)
            if self._retry_eid is None:
                self._retry_eid = self.schedule_cycles(1, self._retry)
            return
        self._in_flight -= 1

    def _retry(self) -> None:
        """Attempt to drain stalled items; reschedule on backpressure."""
        self._retry_eid = None
        while self._stalled:
            item = self._stalled[0]
            if self._consumer(item) is False:
                self._retry_eid = self.schedule_cycles(1, self._retry)
                return
            self._stalled.popleft()
            self._in_flight -= 1

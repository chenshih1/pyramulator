"""Discrete-event simulation kernel.

Implements the classic next-event time-advance mechanism used in
discrete-event simulation: the simulator jumps from event to event and
never steps through empty time. Events scheduled at the same time are
processed in a deterministic order -- priority first (lower value runs
earlier), then insertion order (FIFO).

Time is an integer count of the base time unit (picoseconds, see
:class:`pyramulator.hardware.Clock`).
"""

from __future__ import annotations

import heapq
from collections import Counter
from collections.abc import Callable


class _Event:
    """Heap entry ordered by (time, priority, seq) only."""

    __slots__ = ("callback", "cancelled", "key", "seq", "time")

    def __init__(
        self, time: int, priority: int, seq: int, callback: Callable[[], None]
    ) -> None:
        self.time = time
        self.seq = seq
        self.key = (time, priority, seq)
        self.callback = callback
        self.cancelled = False

    def __lt__(self, other: _Event) -> bool:
        return self.key < other.key


class Simulator:
    """Discrete-event simulator with next-event time advance.

    Examples:
        sim = Simulator()
        sim.schedule(10, lambda: print("t=10"))
        sim.run()  # processes all events, advancing time as needed

    Events run at the time they were scheduled for; time never advances
    past an event without processing it. An event callback may schedule
    further events, including zero-delay delta events at the current time.
    A callback that raises propagates the exception; the event is already
    removed from the queue, so the simulator stays consistent.
    """

    def __init__(self) -> None:
        self._heap: list[_Event] = []
        self._by_id: dict[int, _Event] = {}
        self._seq = 0
        self._now = 0
        self._processed = 0
        self._live = 0
        self._sources: Counter[str | None] = Counter()

    # -- state ---------------------------------------------------------------

    @property
    def now(self) -> int:
        """Current simulation time (base time units, typically ps)."""
        return self._now

    @property
    def processed(self) -> int:
        """Number of events processed so far."""
        return self._processed

    @property
    def pending(self) -> int:
        """Number of events still scheduled (cancelled events excluded)."""
        return self._live

    @property
    def next_time(self) -> int | None:
        """Time of the next pending event, or None if the queue is empty."""
        event = self._peek()
        return event.time if event is not None else None

    @property
    def event_counts(self) -> dict[str | None, int]:
        """Events scheduled so far, grouped by the ``source`` name passed to
        :meth:`schedule` / :meth:`at` (None = scheduled directly on the
        simulator). Useful for profiling which component generates events."""
        return dict(self._sources)

    # -- scheduling ----------------------------------------------------------

    def schedule(
        self,
        delay: int,
        callback: Callable[[], None],
        priority: int = 0,
        source: str | None = None,
    ) -> int:
        """Schedule *callback* to run *delay* time units from now.

        ``source`` is an optional label (typically a component name) counted
        in :attr:`event_counts`. Returns an event id usable with
        :meth:`cancel`."""
        if delay < 0:
            raise ValueError(f"negative delay {delay}")
        return self._push(self._now + delay, callback, priority, source)

    def at(
        self,
        time: int,
        callback: Callable[[], None],
        priority: int = 0,
        source: str | None = None,
    ) -> int:
        """Schedule *callback* at absolute *time*; must not be in the past."""
        if time < self._now:
            raise ValueError(f"cannot schedule at {time} < now {self._now}")
        return self._push(time, callback, priority, source)

    def _push(
        self,
        time: int,
        callback: Callable[[], None],
        priority: int,
        source: str | None,
    ) -> int:
        event = _Event(time, priority, self._seq, callback)
        self._seq += 1
        heapq.heappush(self._heap, event)
        self._live += 1
        self._sources[source] += 1
        self._by_id[event.seq] = event
        return event.seq

    def cancel(self, event_id: int) -> bool:
        """Cancel a pending event; returns True if it was still scheduled."""
        event = self._by_id.get(event_id)
        if event is not None and not event.cancelled:
            event.cancelled = True
            self._live -= 1
            return True
        return False

    def _advance_to(self, time: int) -> None:
        """Jump *now* to *time* without processing events.

        *time* must be >= now, and no pending event may fall strictly
        before *time*. Used by :class:`~pyramulator.dram.Dram` to keep
        simulator time aligned after coalescing empty DRAM cycles in C++.
        """
        if time < self._now:
            raise ValueError(f"cannot advance to {time} < now {self._now}")
        nxt = self._peek()
        if nxt is not None and nxt.time < time:
            raise RuntimeError(f"cannot advance to {time}: event pending at {nxt.time}")
        self._now = time

    # -- execution -----------------------------------------------------------

    def _peek(self) -> _Event | None:
        while self._heap and self._heap[0].cancelled:
            dead = heapq.heappop(self._heap)
            self._by_id.pop(dead.seq, None)
        return self._heap[0] if self._heap else None

    def _fire(self, event: _Event) -> None:
        self._live -= 1
        self._now = event.time
        # Drop the id before the callback so cancel() of the running event
        # returns False (it is no longer scheduled) and does not decrement
        # pending a second time.
        self._by_id.pop(event.seq, None)
        event.callback()
        self._processed += 1

    def step(self) -> bool:
        """Advance to and process the next event; False if none remain."""
        event = self._peek()
        if event is None:
            return False
        heapq.heappop(self._heap)
        self._fire(event)
        return True

    def run(self, until: int | None = None, max_events: int | None = None) -> int:
        """Process events until the queue is empty, *until* (inclusive) is
        reached, or *max_events* have run. Returns events processed."""
        start = self._processed
        while True:
            if max_events is not None and self._processed - start >= max_events:
                break
            event = self._peek()
            if event is None:
                break
            if until is not None and event.time > until:
                break
            heapq.heappop(self._heap)
            self._fire(event)
        return self._processed - start

    def run_until_idle(self, max_events: int | None = None) -> int:
        """Process every event in the queue; returns events processed."""
        return self.run(None, max_events)

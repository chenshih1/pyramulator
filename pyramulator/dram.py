"""Dram: the Ramulator engine embedded as a discrete-event device.

The component owns a :class:`Clock` running at the DRAM tCK (rounded to
integer picoseconds) and ticks the cycle-accurate engine only while
requests are in flight — an idle DRAM costs zero simulator events.
Read completions are delivered as zero-delay events at the simulator
time of the DRAM tick on which Ramulator fired them; write completion
follows the engine's constraint (Ramulator has no upstream write
callback), so writes complete upon acceptance. Use :meth:`Dram.flush`
as a barrier when writes must be truly serviced before proceeding.

With ``idle_refresh=True`` the component keeps a coarse idle clock
running (one event per ``idle_batch_cycles``) so Ramulator's refresh
timer advances with wall-clock time — matching the reference
integration (e.g. gem5) — at the cost of nonzero idle events. Note
that with idle refresh enabled the DRAM never goes idle, so
``run_until_idle()`` does not terminate; drive the simulator with
``run(until=...)`` instead.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

from ._engine import CompletionCallback, Config, MemorySystem, RequestInfo
from .hardware import Clock, Component
from .sim import Simulator


class Dram(Component):
    """Cycle-accurate DRAM model as a DES component.

    Examples:
        sim = Simulator()
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")
        dram = Dram(sim, cfg)
        done = []

        def on_complete(info):
            done.append(info)

        dram.read(0x1000, callback=on_complete)
        sim.run_until_idle()          # completions delivered as events
        print(done[0].latency)        # latency in DRAM clock cycles
    """

    def __init__(
        self,
        sim: Simulator,
        config: Config | dict[str, Any],
        cacheline: int = 64,
        num_cores: int = 1,
        completion_priority: int = 0,
        idle_refresh: bool = False,
        idle_batch_cycles: int = 1024,
        name: str = "dram",
    ) -> None:
        self._mem = MemorySystem(config, cacheline=cacheline, num_cores=num_cores)
        period_ps = round(self._mem.tck * 1000)  # ns -> integer ps
        super().__init__(sim, Clock(period_ps, name + "_clk"), name)
        self._completion_priority = completion_priority
        self._ticking = False
        self._idle_refresh = idle_refresh
        if idle_batch_cycles < 1:
            raise ValueError(
                f"idle_batch_cycles must be positive, got {idle_batch_cycles}"
            )
        self._idle_batch_cycles = idle_batch_cycles
        self._current_idle_batch = idle_batch_cycles
        self._max_idle_batch = idle_batch_cycles * 16
        self._idle_ticking = False
        self._idle_event_id: int | None = None
        self._completed: deque[tuple[RequestInfo, CompletionCallback]] = deque()
        self._collector_src: CompletionCallback = None
        self._collector_wrap: Callable[[RequestInfo], None] | None = None
        if self._idle_refresh:
            self._start_idle_ticking()

    # -- timing / state ------------------------------------------------------

    @property
    def period_ps(self) -> int:
        """DRAM clock period in picoseconds (tCK, rounded to integer ps)."""
        return self.clk.period_ps

    @property
    def tck_ns(self) -> float:
        """DRAM clock period in nanoseconds (engine value)."""
        return self._mem.tck

    @property
    def pending(self) -> int:
        """Requests accepted but not yet serviced by the DRAM."""
        return self._mem.pending

    @property
    def cycles(self) -> int:
        """DRAM clock cycles simulated so far."""
        return self._mem.clk

    # -- request interface ---------------------------------------------------

    def read(
        self,
        addr: int,
        callback: CompletionCallback = None,
        core_id: int = 0,
    ) -> bool:
        """Send a READ request; True if accepted (False = queue full).

        On completion, *callback* runs as a simulator event at the DRAM
        tick time, with a :class:`RequestInfo` whose ``latency`` is in
        DRAM clock cycles. The engine only fires read completions; writes
        complete upon acceptance (see :meth:`write`).
        """
        accepted = self._mem.send_read(addr, core_id, self._collector(callback))
        if accepted:
            self._start_ticking()
        return accepted

    def write(
        self,
        addr: int,
        callback: CompletionCallback = None,
        core_id: int = 0,
    ) -> bool:
        """Send a WRITE request; True if accepted (False = queue full).

        Ramulator has no write-completion callback upstream, so the
        callback fires at acceptance (zero latency) — the same constraint
        the engine documents. Use :meth:`flush` to wait until writes are
        truly serviced by the DRAM.
        """
        accepted = self._mem.send_write(addr, core_id, self._collector(callback))
        if accepted:
            self._deliver_completed()
            self._start_ticking()
        return accepted

    def reads(
        self,
        addrs: Iterable[int],
        callback: CompletionCallback = None,
        core_id: int = 0,
    ) -> list[bool]:
        """Send multiple READ requests in one engine call; returns accept flags.

        Completions arrive as individual events through *callback*, exactly
        as with :meth:`read`. Any accepted request starts the DRAM clock."""
        accepted = self._mem.send_reads(addrs, core_id, self._collector(callback))
        if any(accepted):
            self._start_ticking()
        return accepted

    def writes(
        self,
        addrs: Iterable[int],
        callback: CompletionCallback = None,
        core_id: int = 0,
    ) -> list[bool]:
        """Send multiple WRITE requests in one engine call; returns accept flags.

        Writes complete upon acceptance (see :meth:`write`); acceptance
        events are delivered immediately."""
        accepted = self._mem.send_writes(addrs, core_id, self._collector(callback))
        if any(accepted):
            self._deliver_completed()
            self._start_ticking()
        return accepted

    def flush(self, max_events: int = 1_000_000) -> int:
        """Barrier: step the simulator until the DRAM queue is empty.

        Blocks the caller (it advances the simulator) until every accepted
        request — writes included — has been serviced. Returns the number
        of events processed. Raises RuntimeError if the DRAM does not
        drain within *max_events*.
        """
        processed = 0
        while self._mem.pending > 0:
            if not self.sim.step():
                raise RuntimeError("simulator stalled before DRAM drained")
            processed += 1
            if processed >= max_events:
                raise RuntimeError(f"DRAM not drained within {max_events} events")
        return processed

    # -- statistics ----------------------------------------------------------

    def get_stats(self) -> dict[str, object]:
        """Raw Ramulator counters for this instance (see engine docs)."""
        return self._mem.get_stats()

    def reset_stats(self) -> None:
        """Reset Ramulator statistics to zero (e.g. per simulation phase)."""
        self._mem.reset_stats()

    def metrics(self) -> dict[str, float]:
        """Derived summary: avg read latency, row-hit rate, bandwidth, ..."""
        return self._mem.metrics()

    # -- internals -----------------------------------------------------------

    def _collector(self, callback: CompletionCallback) -> Callable[[RequestInfo], None]:
        if callback is self._collector_src and self._collector_wrap is not None:
            return self._collector_wrap

        def on_complete(info: RequestInfo) -> None:
            self._completed.append((info, callback))

        self._collector_src = callback
        self._collector_wrap = on_complete
        return on_complete

    def _deliver_completed(self) -> None:
        """Turn recorded completions into zero-delay simulator events."""
        while self._completed:
            info, callback = self._completed.popleft()
            if callback is not None:
                # Capture via default-arg to avoid late-binding surprises.
                self.sim.schedule(
                    0,
                    self._make_completion_cb(callback, info),
                    priority=self._completion_priority,
                )

    @staticmethod
    def _make_completion_cb(
        callback: Callable[[RequestInfo], None], info: RequestInfo
    ) -> Callable[[], None]:
        return lambda: callback(info)

    def _start_ticking(self) -> None:
        if self._ticking:
            return
        if self._idle_ticking:
            self._idle_ticking = False
            if self._idle_event_id is None:
                raise RuntimeError("idle ticking without an event id")
            self.sim.cancel(self._idle_event_id)
        self._ticking = True
        self.schedule_cycles(1, self._tick)

    def _max_tick_burst(self) -> int:
        """How many DRAM cycles can run in C++ before the next sim event.

        Cycle 0 is *now*. Cycle k would run at ``now + k * period``; we
        only include k such that that time is strictly before the next
        pending event, so coalescing cannot reorder or skip other work.
        """
        nxt = self.sim.next_time
        if nxt is None:
            return 1_000_000
        dt = nxt - self.sim.now
        if dt <= 0:
            return 1
        return (dt - 1) // self.clk.period_ps + 1

    def _tick(self) -> None:
        """Advance the engine; reschedule while busy.

        Empty DRAM cycles with no other simulator events in between are
        ticked in C++ in one call, then simulator time is jumped to the
        cycle that made progress (a completion or idle). Completions are
        still delivered as zero-delay events at that cycle's time.
        """
        n = self._mem.tick_until_progress(self._max_tick_burst())
        if n > 1:
            self.sim._advance_to(self.sim.now + (n - 1) * self.clk.period_ps)
        self._deliver_completed()
        if self._mem.pending:
            self.schedule_cycles(1, self._tick)
        else:
            self._ticking = False
            if self._idle_refresh:
                self._start_idle_ticking()

    def _start_idle_ticking(self) -> None:
        """Start the coarse idle clock that advances refresh with wall time."""
        if self._idle_ticking:
            return
        self._idle_ticking = True
        # Restart backoff so the first idle event after a busy stretch ticks
        # the same number of DRAM cycles as it was scheduled for. Leaving a
        # grown batch in place scheduled a short delay then ran the long
        # batch, desynchronizing dram.cycles from wall-clock time.
        self._current_idle_batch = self._idle_batch_cycles
        self._idle_event_id = self.schedule_cycles(
            self._idle_batch_cycles, self._idle_tick
        )

    def _idle_tick(self) -> None:
        """Advance wall-clock time in batches while the DRAM is idle."""
        self._mem.run(self._current_idle_batch)
        if self._mem.pending:
            # Defensive: a request appeared during the batch (impossible in
            # single-threaded DES) — hand back to the busy tick chain.
            self._idle_ticking = False
            self._current_idle_batch = self._idle_batch_cycles
            self._start_ticking()
            return
        # Exponential back-off: fewer events when the DRAM stays idle.
        self._current_idle_batch = min(
            self._current_idle_batch * 2, self._max_idle_batch
        )
        self._idle_event_id = self.schedule_cycles(
            self._current_idle_batch, self._idle_tick
        )

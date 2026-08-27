"""Copy engine composed from Pipe, FIFO, and Dram.

A 1 GHz core copies cachelines from a source region to a destination
region. The other examples drive Dram from a Component and a raw deque;
this one wires the public hardware primitives:

  produce -> issue Pipe --(stall if FIFO full)--> issue FIFO --pump--> Dram.read
  Dram.read complete -> compute Pipe --(stall if write queue full)--> Dram.write

Two clocks: the core at 1 GHz, the Dram at the DDR4 tCK. Backpressure is
Pipe consumer ``False`` (retry every core cycle) plus ``Dram.read`` /
``Dram.write`` returning False (retry from the next completion or Pipe
retry). A completing load still occupies a compute-pipe slot, so the
read pump also stops when ``reads_inflight + compute in_flight`` would
exceed the pipe; leftovers that find the pipe full are held and pushed
once a store frees a slot. The simulator is drained with
``run_until_idle()`` from outside the pipeline — not with a nested
``flush()`` from inside a callback.

Run:
    python examples/pipe_fifo_dram.py
"""

from __future__ import annotations

from collections import deque

from pyramulator import FIFO, Clock, Component, Config, Dram, Pipe, Simulator

HOST_PERIOD_PS = 1000  # 1 GHz core
CACHELINE = 64
SRC_BASE = 0x0
DST_BASE = 0x10_0000


class CopyEngine(Component):
    """Streaming copy: Pipe/FIFO issue path, Pipe compute, Dram load/store."""

    def __init__(
        self,
        sim: Simulator,
        dram: Dram,
        n_lines: int = 256,
        issue_latency: int = 2,
        compute_latency: int = 4,
        issue_slots: int = 4,
        compute_slots: int = 16,
        queue_depth: int = 16,
        max_outstanding: int = 16,
    ) -> None:
        super().__init__(sim, Clock(HOST_PERIOD_PS, "host"), "copy")
        self.dram = dram
        self.n_lines = n_lines
        self.max_outstanding = max_outstanding
        self._produced = 0
        self._reads_inflight = 0
        self._writes_accepted = 0
        self._issue_stalls = 0
        self._store_stalls = 0
        self._compute_stalls = 0
        self._fifo_high_water = 0
        self._held_compute: deque[tuple[int, int]] = deque()

        self.issue_q = FIFO(sim, self.clk, capacity=queue_depth, name="issue_q")
        self.issue_pipe = Pipe(
            sim,
            self.clk,
            latency_cycles=issue_latency,
            slots=issue_slots,
            consumer=self._on_issue,
            name="issue_pipe",
        )
        # A completing load still occupies a slot, so issue credits include
        # pipe occupancy; slots need not be >= max_outstanding.
        self.compute_pipe = Pipe(
            sim,
            self.clk,
            latency_cycles=compute_latency,
            slots=compute_slots,
            consumer=self._try_store,
            name="compute_pipe",
        )

    def run(self) -> None:
        """Fill the issue pipe and drive the simulator until the copy drains."""
        self._fill_issue()
        self.sim.run_until_idle()

    def _dst(self, src: int) -> int:
        return DST_BASE + (src - SRC_BASE)

    def _fill_issue(self) -> None:
        """Push source addresses into the issue pipe until it or the stream is done."""
        while self._produced < self.n_lines and self.issue_pipe.can_put():
            addr = SRC_BASE + self._produced * CACHELINE
            self.issue_pipe.put(addr)
            self._produced += 1

    def _on_issue(self, addr: int) -> bool:
        """Pipe consumer: enqueue for DRAM, or stall the pipe if the FIFO is full."""
        if not self.issue_q.put(addr):
            self._issue_stalls += 1
            return False
        if self.issue_q.level > self._fifo_high_water:
            self._fifo_high_water = self.issue_q.level
        self._pump_reads()
        self._fill_issue()
        return True

    def _compute_reserved(self) -> int:
        """Items that already occupy, or will occupy, a compute-pipe slot."""
        return (
            self._reads_inflight + self.compute_pipe.in_flight + len(self._held_compute)
        )

    def _drain_held_compute(self) -> None:
        """Push completions that found the compute pipe full."""
        while self._held_compute and self.compute_pipe.put(self._held_compute[0]):
            self._held_compute.popleft()

    def _pump_reads(self) -> None:
        """Issue queued reads until DRAM, the window, or compute occupancy says no.

        ``max_outstanding`` caps DRAM reads in flight. It does not cap compute-pipe
        occupancy: a completed load still holds a slot after ``_reads_inflight``
        drops, so a further read can complete into a full pipe. Reserve a slot
        at issue time (``_compute_reserved``) and hold any completion that
        still sees ``put`` return False — ``put`` must not live in ``assert``
        (``python -O`` would skip it and drop the store).
        """
        self._drain_held_compute()
        while (
            self.issue_q.can_get()
            and self._reads_inflight < self.max_outstanding
            and self._compute_reserved() < self.compute_pipe.slots
        ):
            addr = self.issue_q.peek()
            if not self.dram.read(addr, callback=self._on_load):
                break
            self.issue_q.get()
            self._reads_inflight += 1

    def _on_load(self, info) -> None:
        self._reads_inflight -= 1
        item = (info.addr, self._dst(info.addr))
        self._drain_held_compute()
        if not self.compute_pipe.put(item):
            self._held_compute.append(item)
            self._compute_stalls += 1
        self._pump_reads()

    def _try_store(self, item: tuple[int, int]) -> bool:
        """Pipe consumer: accept a write, or stall until the DRAM queue has room."""
        _src, dst = item
        if not self.dram.write(dst, callback=self._on_store_accepted):
            self._store_stalls += 1
            return False
        return True

    def _on_store_accepted(self, info) -> None:
        self._writes_accepted += 1
        # Slot is already free: Pipe decrements in_flight before this delta
        # callback. Drain held completions and issue the next reads.
        self._pump_reads()

    def report(self) -> None:
        host_cycles = self.sim.now // HOST_PERIOD_PS
        m = self.dram.metrics()
        print("Pipe + FIFO + Dram copy engine")
        print(f"  lines:            {self.n_lines}")
        print(f"  host cycles:      {host_cycles}  ({self.sim.now} ps)")
        print(f"  dram cycles:      {self.dram.cycles}")
        print(f"  writes accepted:  {self._writes_accepted}")
        print(f"  issue FIFO high:  {self._fifo_high_water}/{self.issue_q.capacity}")
        print(f"  issue stalls:     {self._issue_stalls}")
        print(f"  store stalls:     {self._store_stalls}")
        print(f"  compute stalls:   {self._compute_stalls}")
        print(f"  dram events:      {self.sim.event_counts.get(self.dram.name, 0)}")
        print(f"  row hit rate:     {m['row_hit_rate']:.2f}")
        print(f"  bandwidth:        {m['bandwidth_gbs']:.2f} GB/s")


def main() -> None:
    sim = Simulator()
    dram = Dram(
        sim,
        Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8", channels=2),
    )
    engine = CopyEngine(sim, dram)
    engine.run()
    if engine._writes_accepted != engine.n_lines:
        raise RuntimeError(
            f"copy dropped stores: {engine._writes_accepted} != {engine.n_lines}"
        )
    if dram.pending != 0:
        raise RuntimeError(f"DRAM still pending: {dram.pending}")
    engine.report()


if __name__ == "__main__":
    main()

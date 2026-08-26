"""Sparse-Dense matrix multiplication (SpMM) accelerator on HBM, DES style.

A deliberately naive, single-PE architecture modeled as discrete-event
components: the accelerator streams the dense matrix B row-by-row (one
cacheline per request, up to MAX_INFLIGHT in flight) from an HBM DRAM
modeled by the Dram component, multiplying each element by the matching A
value and accumulating as read completions arrive as events. The DRAM is
a pure timing model, so the actual B data lives in a host-side image
indexed by address.

The accelerator runs on a 1 GHz host clock; the Dram component owns its
own clock at the HBM tCK and only ticks while requests are in flight.
Issue is purely event-driven: each read completion frees a slot and
re-triggers the issue loop.

Run:
    python examples/spmm_hbm.py [channels]

Validates the result against numpy (C == A @ B) and reports cycles,
effective DRAM bandwidth, and row-buffer hit rate.
"""

from __future__ import annotations

import sys
import time
from collections import deque

import numpy as np

from pyramulator import Clock, Component, Config, Dram, Simulator

FLOATS_PER_CACHELINE = 16  # 64 B cacheline / 4 B float
MAX_INFLIGHT = 16  # requests in flight (naive queue cap)
B_BASE = 0x100000  # start of B's image in DRAM
HOST_PERIOD_PS = 1000  # accelerator clock: 1 GHz


class SpMMAccelerator(Component):
    """Naive single-PE SpMM accelerator as a DES component."""

    def __init__(self, sim: Simulator, dram: Dram, channels: int = 4):
        super().__init__(sim, Clock(HOST_PERIOD_PS, "host"), "spmm")
        self.dram = dram
        self.channels = channels
        self._pending: deque = deque()  # (i, j, t, v) tuples to issue
        self._inflight = 0
        self._sent = 0
        self._acc = None
        self._image = None
        self._k = 0
        self._wall = 0.0

    def _addr_of(self, j: int, t: int) -> int:
        return B_BASE + (j * self._k + t) * 4

    def run(self, A, B):
        """Compute C = A @ B. A: CSR triplets, B: ndarray.

        Blocks until every request has completed (drives the simulator to
        idle), then returns the accumulator."""
        rows_ptr, cols, vals = A
        m = len(rows_ptr) - 1
        self._k = B.shape[1]
        self._image = B.flatten()
        self._acc = np.zeros((m, self._k), dtype=np.float64)

        for i in range(m):
            for idx in range(rows_ptr[i], rows_ptr[i + 1]):
                j = cols[idx]
                v = vals[idx]
                for t in range(0, self._k, FLOATS_PER_CACHELINE):
                    self._pending.append((i, j, t, v))

        self.dram.reset_stats()
        t0 = time.perf_counter()
        self._issue()
        self.sim.run_until_idle()
        self._wall = time.perf_counter() - t0
        assert not self._pending and self._inflight == 0
        return self._acc

    def _issue(self) -> None:
        """Fill the in-flight window; completions re-trigger issue."""
        while self._inflight < MAX_INFLIGHT and self._pending:
            i, j, t, v = self._pending[0]
            addr = self._addr_of(j, t)
            if not self.dram.read(
                addr,
                callback=lambda info, i=i, j=j, t=t, v=v: self._on_complete(
                    info, i, j, t, v
                ),
            ):
                break  # DRAM queue full; a completion will re-trigger us
            self._pending.popleft()
            self._inflight += 1
            self._sent += 1

    def _on_complete(self, info, i: int, j: int, t: int, v: float) -> None:
        self._inflight -= 1
        off = (info.addr - B_BASE) // 4
        blk = self._image[off : off + FLOATS_PER_CACHELINE]
        self._acc[i, t : t + FLOATS_PER_CACHELINE] += v * blk
        self._issue()

    def report(self) -> None:
        dram = self.dram
        bytes_read = self._sent * 64  # one cacheline per request
        gbs = bytes_read / (dram.cycles * dram.tck_ns * 1e-9) / 1e9
        theo = 1000e6 * 16 * self.channels / 1e9  # 1Gbps x 128-bit x channels
        print(
            f"SpMM on HBM ({self.channels}ch): {dram.cycles} cycles, "
            f"{self._wall:.2f}s wall"
        )
        print(
            f"  effective DRAM bandwidth: {gbs:.1f} GB/s (theoretical {theo:.0f} GB/s)"
        )
        print(f"  inflight window: {MAX_INFLIGHT}, requests: {self._sent}")
        print(f"  row hit rate: {dram.metrics()['row_hit_rate']:.2f}")


def main(channels):
    rng = np.random.default_rng(0)
    m, n, k = 64, 64, 64
    density = 0.1

    # Sparse A in CSR (rows_ptr, cols, vals).
    cols, vals = [], []
    rows_ptr = [0]
    for _ in range(m):
        row_cols = [c for c in range(n) if rng.random() < density]
        cols.extend(row_cols)
        vals.extend(rng.random(len(row_cols)))
        rows_ptr.append(len(cols))
    A = (
        np.array(rows_ptr),
        np.array(cols, dtype=np.int64),
        np.array(vals, dtype=np.float64),
    )

    B = rng.random((n, k), dtype=np.float64)

    sim = Simulator()
    dram = Dram(
        sim, Config(standard="HBM", speed="HBM_1Gbps", org="HBM_1Gb", channels=channels)
    )
    accel = SpMMAccelerator(sim, dram, channels=channels)
    acc = accel.run(A, B)
    accel.report()

    # Reference: C = A @ B.
    ref = np.zeros((m, k))
    for i in range(m):
        for idx in range(rows_ptr[i], rows_ptr[i + 1]):
            ref[i] += vals[idx] * B[cols[idx]]
    assert np.allclose(acc, ref, atol=1e-9), "SpMM result mismatch!"
    print("validated: C == A @ B (numpy)")


if __name__ == "__main__":
    channels = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    main(channels)

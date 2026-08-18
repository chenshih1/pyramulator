"""Sparse-Dense matrix multiplication (SpMM) accelerator on HBM.

A deliberately naive, single-PE architecture: the accelerator streams the
dense matrix B row-by-row (one cacheline per request, up to MAX_INFLIGHT
in flight) from an HBM DRAM modeled by pyramulator, multiplying each
element by the matching A value and accumulating as read completions
arrive. The DRAM is a pure timing model, so the actual B data lives in a
host-side image indexed by address.

Run:
    python examples/spmm_hbm.py [channels]

Validates the result against numpy (C == A @ B) and reports cycles,
effective DRAM bandwidth, and row-buffer hit rate.
"""

import sys
import time
from collections import deque

import numpy as np

from pyramulator import Config, MemorySystem

FLOATS_PER_CACHELINE = 16  # 64 B cacheline / 4 B float
MAX_INFLIGHT = 16  # requests in flight (naive queue cap)
B_BASE = 0x100000  # start of B's image in DRAM


class SpMMAccelerator:
    """Naive single-PE SpMM accelerator with an HBM timing model."""

    def __init__(self, channels=4):
        cfg = Config(
            standard="HBM", speed="HBM_1Gbps", org="HBM_1Gb", channels=channels
        )
        self.mem = MemorySystem(cfg)
        self.channels = channels

    @staticmethod
    def _addr_of(j, t, k):
        return B_BASE + (j * k + t) * 4

    def run(self, A, B):
        """Compute C = A @ B. A: CSR triplets, B: ndarray."""
        rows_ptr, cols, vals = A  # CSR
        m = len(rows_ptr) - 1
        k = B.shape[1]
        assert B.flags["C_CONTIGUOUS"]
        self.image = B.flatten()  # host-side image of DRAM contents

        acc = np.zeros((m, k), dtype=np.float64)

        # All read requests: for each (i, j) non-zero, B's row j in
        # FLOATS_PER_CACHELINE chunks.
        pending = deque()
        for i in range(m):
            for idx in range(rows_ptr[i], rows_ptr[i + 1]):
                j = cols[idx]
                v = vals[idx]
                for t in range(0, k, FLOATS_PER_CACHELINE):
                    pending.append((i, j, t, v))

        inflight = []  # (i, j, t, v, addr) issued but not yet completed
        completed = []  # RequestInfos from the last tick
        sent = 0
        mem = self.mem
        mem.reset_stats()
        t0 = time.perf_counter()

        def on_complete(info):
            completed.append(info)

        while pending or inflight:
            # 1. Fill the in-flight window (backpressure via send()).
            while len(inflight) < MAX_INFLIGHT and pending:
                i, j, t, v = pending.popleft()
                addr = self._addr_of(j, t, k)
                if mem.send_read(addr, callback=on_complete):
                    inflight.append((i, j, t, v, addr))
                    sent += 1
                else:
                    pending.appendleft((i, j, t, v))  # queue full, retry
                    break

            # 2. Advance the DRAM one cycle; completions arrive here
            #    through the batched event path.
            mem.tick()

            # 3. Multiply-accumulate on completion.
            for info in completed:
                off = (info.addr - B_BASE) // 4
                blk = self.image[off : off + FLOATS_PER_CACHELINE]
                for idx, (i, _j, t, v, addr) in enumerate(inflight):
                    if addr == info.addr:
                        acc[i, t : t + FLOATS_PER_CACHELINE] += v * blk
                        del inflight[idx]
                        break
            completed.clear()

        wall = time.perf_counter() - t0
        bytes_read = sent * 64  # one cacheline per request
        gbs = bytes_read / (mem.clk * mem.tck * 1e-9) / 1e9
        theo = 1000e6 * 16 * self.channels / 1e9  # 1Gbps x 128-bit x channels
        print(f"SpMM on HBM ({self.channels}ch): {mem.clk} cycles, {wall:.2f}s wall")
        print(
            f"  effective DRAM bandwidth: {gbs:.1f} GB/s (theoretical {theo:.0f} GB/s)"
        )
        print(f"  inflight window: {MAX_INFLIGHT}, requests: {sent}")
        print(f"  row hit rate: {mem.metrics()['row_hit_rate']:.2f}")
        return acc


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

    acc = SpMMAccelerator(channels=channels).run(A, B)

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

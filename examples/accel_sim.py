"""Simple vector accelerator simulator, DES style.

Models a multi-lane accelerator computing C[i] = A[i] + B[i] on the
discrete-event framework. Each lane runs a 3-phase pipeline per tile:

  1. LOAD:    issue reads for A and B, wait for all to return
  2. COMPUTE: fixed latency per element (an event delay)
  3. STORE:   issue writes for C, barrier until truly serviced

Demonstrates: components and clocks, backpressure, event-driven issue,
the write-acceptance semantics of the Dram component and its flush()
barrier.
"""

from __future__ import annotations

import logging
from collections import deque

from pyramulator import Clock, Component, Config, Dram, Simulator

logger = logging.getLogger(__name__)

HOST_PERIOD_PS = 1000  # 1 GHz accelerator clock


class Accelerator(Component):
    def __init__(
        self,
        sim: Simulator,
        dram: Dram,
        num_lanes: int = 4,
        vector_size: int = 4096,
        elem_size: int = 8,
        tile_size: int = 64,
        max_outstanding: int = 32,
        compute_cycles: int = 4,
        base_addr_a: int = 0x0_0000,
        base_addr_b: int = 0x10_0000,
        base_addr_c: int = 0x20_0000,
    ):
        super().__init__(sim, Clock(HOST_PERIOD_PS, "host"), "accel")
        self.dram = dram
        self.num_lanes = num_lanes
        self.vector_size = vector_size
        self.elem_size = elem_size
        self.tile_size = tile_size
        self.max_outstanding = max_outstanding
        self.compute_cycles = compute_cycles
        self.base_addr_a = base_addr_a
        self.base_addr_b = base_addr_b
        self.base_addr_c = base_addr_c

        self.outstanding = 0  # requests in flight (global bound)
        self.read_latencies = []
        self.write_latencies = []
        self.stalls = 0  # rejected issue attempts
        self._lane = 0
        self._tile_start = 0
        self._tile_count = 0
        self._pending: deque = deque()  # (addr, core_id) to issue
        self._loads_outstanding = 0

    def _elems_per_lane(self) -> int:
        return self.vector_size // self.num_lanes

    def _lane_base(self) -> int:
        return self._lane * self._elems_per_lane() * self.elem_size

    def run(self) -> None:
        """Run the full vector computation; drives the simulator to idle."""
        self._next_tile()
        self.sim.run_until_idle()

    def _next_tile(self) -> None:
        """Advance (lane, tile) and start the next LOAD phase."""
        while True:
            if self._tile_start >= self._elems_per_lane():
                self._tile_start = 0
                self._lane += 1
                if self._lane >= self.num_lanes:
                    return  # done
            self._tile_count = min(
                self.tile_size, self._elems_per_lane() - self._tile_start
            )
            self._load_tile()
            return

    def _load_tile(self) -> None:
        base = self._lane_base()
        self._pending = deque()
        for i in range(self._tile_count):
            byte_off = base + (self._tile_start + i) * self.elem_size
            self._pending.append((self.base_addr_a + byte_off, self._lane))
            self._pending.append((self.base_addr_b + byte_off, self._lane))
        self._loads_outstanding = 0
        self._pump_loads()

    def _pump_loads(self) -> None:
        while self._pending and self.outstanding < self.max_outstanding:
            addr, lane = self._pending.popleft()
            if not self.dram.read(
                addr,
                core_id=lane,
                callback=lambda info, lane=lane: self._on_load_done(info, lane),
            ):
                self._pending.appendleft((addr, lane))
                self.stalls += 1
                break  # queue full; a completion will re-trigger the pump
            self.outstanding += 1
            self._loads_outstanding += 1
        if not self._pending and self._loads_outstanding == 0:
            # All loads for this tile are complete: compute, then store.
            self.schedule_cycles(
                self._tile_count * self.compute_cycles, self._store_tile
            )

    def _on_load_done(self, info, lane: int) -> None:
        self.outstanding -= 1
        self._loads_outstanding -= 1
        self.read_latencies.append(info.latency)
        self._pump_loads()

    def _store_tile(self) -> None:
        base = self._lane_base()
        self._pending = deque()
        for i in range(self._tile_count):
            byte_off = base + (self._tile_start + i) * self.elem_size
            self._pending.append((self.base_addr_c + byte_off, self._lane))
        while self._pending:
            addr, lane = self._pending.popleft()
            if not self.dram.write(
                addr,
                core_id=lane,
                callback=lambda info, lane=lane: self._on_store_done(info, lane),
            ):
                self._pending.appendleft((addr, lane))
                self.stalls += 1
                self.dram.flush()  # wait for the DRAM to make room
        # All writes accepted; barrier until they are truly serviced.
        self.dram.flush()
        self._tile_start += self._tile_count
        self._next_tile()

    def _on_store_done(self, info, lane: int) -> None:
        self.outstanding -= 1
        self.write_latencies.append(info.latency)

    def report(self) -> None:
        dram = self.dram
        tck = dram.tck_ns
        total_reads = len(self.read_latencies)
        total_writes = len(self.write_latencies)
        total_requests = total_reads + total_writes
        bytes_moved = total_requests * 64
        time_ns = self.sim.now / 1000  # ps -> ns
        bandwidth = bytes_moved / (time_ns * 1e-9) / 1e9 if time_ns > 0 else 0

        avg_read_lat = sum(self.read_latencies) / total_reads if total_reads else 0
        avg_write_lat = sum(self.write_latencies) / total_writes if total_writes else 0

        logger.info("=" * 60)
        logger.info("%s", f"{'Accelerator Simulation Report':^60}")
        logger.info("=" * 60)
        logger.info("  Lanes:           %d", self.num_lanes)
        logger.info("  Vector:          %d x %dB", self.vector_size, self.elem_size)
        logger.info("  Tile size:       %d elements", self.tile_size)
        logger.info("  Max outstanding: %d", self.max_outstanding)
        logger.info("  Compute:         %d cyc/elem", self.compute_cycles)
        logger.info("  DRAM tck:        %.3f ns", tck)
        logger.info("-" * 60)
        logger.info("  Total cycles:    %d", self.sim.now // HOST_PERIOD_PS)
        logger.info("  Sim time:        %.0f ns (%.4f ms)", time_ns, time_ns / 1e6)
        logger.info("  Reads:           %d", total_reads)
        logger.info("  Writes:          %d", total_writes)
        logger.info("  Stalls:          %d", self.stalls)
        logger.info(
            "  Avg read lat:    %.1f cyc (%.1f ns)", avg_read_lat, avg_read_lat * tck
        )
        logger.info(
            "  Avg write lat:   %.1f cyc (%.1f ns)", avg_write_lat, avg_write_lat * tck
        )
        logger.info("  Achieved BW:     %.2f GB/s", bandwidth)
        logger.info("=" * 60)


def main() -> None:
    scenarios = [
        (
            "DDR4-2400 2ch, tile=64, depth=32",
            {
                "standard": "DDR4",
                "channels": 2,
                "ranks": 1,
                "speed": "DDR4_2400R",
                "org": "DDR4_4Gb_x8",
            },
            {
                "num_lanes": 4,
                "vector_size": 4096,
                "tile_size": 64,
                "max_outstanding": 32,
                "compute_cycles": 4,
            },
        ),
        (
            "DDR4-2400 2ch, tile=256, depth=32",
            {
                "standard": "DDR4",
                "channels": 2,
                "ranks": 1,
                "speed": "DDR4_2400R",
                "org": "DDR4_4Gb_x8",
            },
            {
                "num_lanes": 4,
                "vector_size": 4096,
                "tile_size": 256,
                "max_outstanding": 32,
                "compute_cycles": 4,
            },
        ),
        (
            "DDR4-2400 1ch, tile=64, depth=32",
            {
                "standard": "DDR4",
                "channels": 1,
                "ranks": 1,
                "speed": "DDR4_2400R",
                "org": "DDR4_4Gb_x8",
            },
            {
                "num_lanes": 4,
                "vector_size": 4096,
                "tile_size": 64,
                "max_outstanding": 32,
                "compute_cycles": 4,
            },
        ),
        (
            "DDR3-1600 1ch, tile=64, depth=16",
            {
                "standard": "DDR3",
                "channels": 1,
                "ranks": 1,
                "speed": "DDR3_1600K",
                "org": "DDR3_2Gb_x8",
            },
            {
                "num_lanes": 4,
                "vector_size": 4096,
                "tile_size": 64,
                "max_outstanding": 16,
                "compute_cycles": 4,
            },
        ),
    ]

    for label, dram_params, accel_params in scenarios:
        logger.info("--- %s ---", label)
        sim = Simulator()
        dram = Dram(sim, Config(**dram_params), num_cores=accel_params["num_lanes"])
        accel = Accelerator(sim, dram, **accel_params)
        accel.run()
        accel.report()
        logger.info("")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()

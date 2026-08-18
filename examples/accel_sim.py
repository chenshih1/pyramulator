"""Simple vector accelerator simulator with DRAM-side timing via pyramulator.

Models a multi-lane accelerator computing C[i] = A[i] + B[i].
Each lane runs a 3-phase pipeline per tile:
  1. LOAD:    issue reads for A and B, wait for all to return
  2. COMPUTE: fixed latency per element
  3. STORE:   issue writes for C, wait for all to return

Demonstrates: multi-core traffic, backpressure, callbacks, latency measurement.
"""

import logging

from pyramulator import Config, MemorySystem

logger = logging.getLogger(__name__)


class Accelerator:
    def __init__(
        self,
        num_lanes=4,
        vector_size=4096,
        elem_size=8,
        tile_size=64,
        max_outstanding=32,
        compute_cycles=4,
        base_addr_a=0x0_0000,
        base_addr_b=0x10_0000,
        base_addr_c=0x20_0000,
    ):
        self.num_lanes = num_lanes
        self.vector_size = vector_size
        self.elem_size = elem_size
        self.tile_size = tile_size
        self.max_outstanding = max_outstanding
        self.compute_cycles = compute_cycles
        self.base_addr_a = base_addr_a
        self.base_addr_b = base_addr_b
        self.base_addr_c = base_addr_c

        self.clk = 0
        self.outstanding = 0
        self.read_latencies = []
        self.write_latencies = []
        self.stall_cycles = 0

    def setup(self, dram_config: Config):
        self.mem = MemorySystem(dram_config, cacheline=64, num_cores=self.num_lanes)

    def _wait_drain(self, max_cycles=500_000):
        for _ in range(max_cycles):
            self.mem.tick()
            self.clk += 1
            if self.outstanding == 0:
                return
        raise RuntimeError("drain timeout")

    def _load_tile(self, lane, offset, count):
        base_off = lane * (self.vector_size // self.num_lanes) * self.elem_size

        for i in range(count):
            byte_off = base_off + (offset + i) * self.elem_size

            def on_read_done(info, _lane=lane):
                self.outstanding -= 1
                self.read_latencies.append(info.depart - info.arrive)

            while True:
                if self.outstanding + 2 > self.max_outstanding:
                    self.mem.tick()
                    self.clk += 1
                    self.stall_cycles += 1
                    continue
                ok_a = self.mem.send_read(
                    self.base_addr_a + byte_off, core_id=lane, callback=on_read_done
                )
                ok_b = self.mem.send_read(
                    self.base_addr_b + byte_off, core_id=lane, callback=on_read_done
                )
                if ok_a and ok_b:
                    self.outstanding += 2
                    break
                self.mem.tick()
                self.clk += 1
                self.stall_cycles += 1

        self._wait_drain()

    def _store_tile(self, lane, offset, count):
        base_off = lane * (self.vector_size // self.num_lanes) * self.elem_size

        for i in range(count):
            byte_off = base_off + (offset + i) * self.elem_size

            def on_write_done(info, _lane=lane):
                self.outstanding -= 1
                self.write_latencies.append(info.depart - info.arrive)

            while True:
                if self.outstanding >= self.max_outstanding:
                    self.mem.tick()
                    self.clk += 1
                    self.stall_cycles += 1
                    continue
                if self.mem.send_write(
                    self.base_addr_c + byte_off, core_id=lane, callback=on_write_done
                ):
                    self.outstanding += 1
                    break
                self.mem.tick()
                self.clk += 1
                self.stall_cycles += 1

        self._wait_drain()

    def run(self):
        """Run the full vector computation across all lanes sequentially."""
        elems_per_lane = self.vector_size // self.num_lanes

        for lane in range(self.num_lanes):
            for tile_start in range(0, elems_per_lane, self.tile_size):
                count = min(self.tile_size, elems_per_lane - tile_start)
                self._load_tile(lane, tile_start, count)
                self.clk += count * self.compute_cycles
                self._store_tile(lane, tile_start, count)

        self.mem.finish()

    def report(self):
        tck = self.mem.tck
        total_reads = len(self.read_latencies)
        total_writes = len(self.write_latencies)
        total_requests = total_reads + total_writes
        bytes_moved = total_requests * 64
        time_ns = self.clk * tck
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
        logger.info("  Total cycles:    %d", self.clk)
        logger.info("  Sim time:        %.0f ns (%.4f ms)", time_ns, time_ns / 1e6)
        logger.info("  Reads:           %d", total_reads)
        logger.info("  Writes:          %d", total_writes)
        logger.info("  Stall cycles:    %d", self.stall_cycles)
        logger.info(
            "  Avg read lat:    %.1f cyc (%.1f ns)", avg_read_lat, avg_read_lat * tck
        )
        logger.info(
            "  Avg write lat:   %.1f cyc (%.1f ns)", avg_write_lat, avg_write_lat * tck
        )
        logger.info("  Achieved BW:     %.2f GB/s", bandwidth)
        logger.info("=" * 60)


def main():
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
        accel = Accelerator(**accel_params)
        accel.setup(Config(**dram_params))
        accel.run()
        accel.report()
        logger.info("")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()

"""One-call DRAM benchmarks (latency / throughput) for any configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .workload import addresses

if TYPE_CHECKING:
    from . import Config, MemorySystem


def _mem(config: Config | dict[str, Any], cacheline: int) -> MemorySystem:
    # Late import: pyramulator/__init__.py imports this module while it is
    # still initializing.
    from . import MemorySystem

    return MemorySystem(config, cacheline=cacheline)


def benchmark_latency(
    config: Config | dict[str, Any],
    num_requests: int = 256,
    cacheline: int = 64,
    mode: str = "sequential",
    seed: int | None = None,
    max_addr: int = 1 << 26,
) -> dict[str, float | int]:
    """Average read latency in DRAM clock cycles for an address pattern.

    Requests are sent blockingly (ticking until accepted), then the system
    is drained. Returns a dict with avg/min/max latency and tck."""
    mem = _mem(config, cacheline)
    latencies = []
    for addr in addresses(mode, num_requests, cacheline, seed=seed, max_addr=max_addr):
        while not mem.send_read(
            addr, callback=lambda info: latencies.append(info.depart - info.arrive)
        ):
            mem.tick()
    mem.run_until_idle()
    if not latencies:
        return {"avg": 0.0, "min": 0, "max": 0, "tck": mem.tck, "completed": 0}
    return {
        "avg": sum(latencies) / len(latencies),
        "min": min(latencies),
        "max": max(latencies),
        "tck": mem.tck,
        "completed": len(latencies),
    }


def benchmark_bandwidth(
    config: Config | dict[str, Any],
    num_requests: int = 256,
    cacheline: int = 64,
    queue_depth: int = 32,
    max_cycles: int = 200_000,
) -> dict[str, float | int]:
    """Sustained read bandwidth in GB/s with a saturated queue."""
    mem = _mem(config, cacheline)
    completed = [0]
    first_clk = [None]
    last_clk = [0]

    def on_done(info):
        completed[0] += 1
        if first_clk[0] is None:
            first_clk[0] = info.depart
        last_clk[0] = info.depart

    issued = 0
    addr = 0
    while completed[0] < num_requests and mem.clk < max_cycles:
        while issued - completed[0] < queue_depth and issued < num_requests:
            if mem.send_read(addr, callback=on_done):
                issued += 1
                addr += cacheline
            else:
                break
        mem.tick()

    if first_clk[0] is None or completed[0] < 2:
        return {
            "bandwidth_gbs": 0.0,
            "completed": completed[0],
            "cycles": 0,
            "tck": mem.tck,
        }

    active_cycles = last_clk[0] - first_clk[0]
    if active_cycles == 0:
        return {
            "bandwidth_gbs": 0.0,
            "completed": completed[0],
            "cycles": 0,
            "tck": mem.tck,
        }

    seconds = active_cycles * mem.tck * 1e-9
    bandwidth = completed[0] * cacheline / seconds / 1e9
    return {
        "bandwidth_gbs": bandwidth,
        "completed": completed[0],
        "cycles": active_cycles,
        "tck": mem.tck,
    }


def benchmark_all(
    config: Config | dict[str, Any], num_requests: int = 256, cacheline: int = 64
) -> dict[str, dict[str, float | int]]:
    """Run sequential-latency and bandwidth benchmarks; return both dicts."""
    return {
        "latency": benchmark_latency(config, num_requests, cacheline),
        "bandwidth": benchmark_bandwidth(config, num_requests, cacheline),
    }

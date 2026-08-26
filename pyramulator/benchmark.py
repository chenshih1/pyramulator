"""One-call DRAM benchmarks (latency / throughput) for any configuration.

Both benchmarks run on the DES framework: a :class:`Simulator` drives a
:class:`Dram` component; requests are issued with backpressure and
completions are delivered as events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .dram import Dram
from .sim import Simulator
from .workload import addresses

if TYPE_CHECKING:
    from ._memory import Config


def _dram(config: Config | dict[str, Any], cacheline: int) -> tuple[Simulator, Dram]:
    sim = Simulator()
    return sim, Dram(sim, config, cacheline=cacheline)


def benchmark_latency(
    config: Config | dict[str, Any],
    num_requests: int = 256,
    cacheline: int = 64,
    mode: str = "sequential",
    seed: int | None = None,
    max_addr: int = 1 << 26,
) -> dict[str, float | int]:
    """Average read latency in DRAM clock cycles for an address pattern.

    Requests are issued one at a time with backpressure (the simulator is
    stepped until each is accepted), then the DRAM is drained. Returns a
    dict with avg/min/max latency and tck."""
    sim, dram = _dram(config, cacheline)
    latencies: list[int] = []

    def on_complete(info):
        latencies.append(info.latency)

    for addr in addresses(mode, num_requests, cacheline, seed=seed, max_addr=max_addr):
        while not dram.read(addr, callback=on_complete):
            sim.step()
    sim.run_until_idle()
    if not latencies:
        return {"avg": 0.0, "min": 0, "max": 0, "tck": dram.tck_ns, "completed": 0}
    return {
        "avg": sum(latencies) / len(latencies),
        "min": min(latencies),
        "max": max(latencies),
        "tck": dram.tck_ns,
        "completed": len(latencies),
    }


def benchmark_bandwidth(
    config: Config | dict[str, Any],
    num_requests: int = 256,
    cacheline: int = 64,
    queue_depth: int = 32,
    max_events: int = 1_000_000,
) -> dict[str, float | int]:
    """Sustained read bandwidth in GB/s with a saturated queue."""
    sim, dram = _dram(config, cacheline)
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
    while completed[0] < num_requests and sim.processed < max_events:
        while issued - completed[0] < queue_depth and issued < num_requests:
            if dram.read(addr, callback=on_done):
                issued += 1
                addr += cacheline
            else:
                break
        sim.step()

    if first_clk[0] is None or completed[0] < 2:
        return {
            "bandwidth_gbs": 0.0,
            "completed": completed[0],
            "cycles": 0,
            "tck": dram.tck_ns,
        }

    active_cycles = last_clk[0] - first_clk[0]
    if active_cycles == 0:
        return {
            "bandwidth_gbs": 0.0,
            "completed": completed[0],
            "cycles": 0,
            "tck": dram.tck_ns,
        }

    seconds = active_cycles * dram.tck_ns * 1e-9
    bandwidth = completed[0] * cacheline / seconds / 1e9
    return {
        "bandwidth_gbs": bandwidth,
        "completed": completed[0],
        "cycles": active_cycles,
        "tck": dram.tck_ns,
    }


def benchmark_all(
    config: Config | dict[str, Any], num_requests: int = 256, cacheline: int = 64
) -> dict[str, dict[str, float | int]]:
    """Run sequential-latency and bandwidth benchmarks; return both dicts."""
    return {
        "latency": benchmark_latency(config, num_requests, cacheline),
        "bandwidth": benchmark_bandwidth(config, num_requests, cacheline),
    }

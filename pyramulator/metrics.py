"""Derived performance metrics computed from Ramulator statistics.

Ramulator only finalizes aggregate stats (latency averages, bandwidth) in
``finish()``; these helpers compute them on demand from the raw counters
returned by ``MemorySystem.get_stats()``.
"""

from __future__ import annotations

import re
from typing import Mapping

_LAT_SUM_RE = re.compile(r"read_latency_sum_(\d+)$")
_ROW_HITS_RE = re.compile(r"read_row_hits_channel_(\d+)_core$")
_ROW_MISSES_RE = re.compile(r"read_row_misses_channel_(\d+)_core$")
_ROW_CONFLICTS_RE = re.compile(r"read_row_conflicts_channel_(\d+)_core$")


def _sum_matching(stats: Mapping[str, object], pattern: re.Pattern) -> float:
    return sum(v for k, v in stats.items()
               if pattern.match(k) and isinstance(v, (int, float)))


def avg_read_latency(stats: Mapping[str, object]) -> float:
    """Average read latency in DRAM clock cycles (all channels)."""
    total = _sum_matching(stats, _LAT_SUM_RE)
    requests = stats.get("read_requests", 0) or 0
    return total / requests if requests else 0.0


def row_hit_rate(stats: Mapping[str, object]) -> float:
    """Read row-buffer hit rate: hits / (hits + misses + conflicts)."""
    hits = _sum_matching(stats, _ROW_HITS_RE)
    misses = _sum_matching(stats, _ROW_MISSES_RE)
    conflicts = _sum_matching(stats, _ROW_CONFLICTS_RE)
    total = hits + misses + conflicts
    return hits / total if total else 0.0


def measured_bandwidth(stats: Mapping[str, object], cacheline: int,
                       tck_ns: float) -> float:
    """Sustained bandwidth in GB/s over the whole simulated window.

    Uses the total simulated time (dram_cycles x tck), so idle cycles are
    included.
    """
    requests = (stats.get("read_requests", 0) or 0) + \
        (stats.get("write_requests", 0) or 0)
    cycles = stats.get("dram_cycles", 0) or 0
    seconds = cycles * tck_ns * 1e-9
    if seconds <= 0:
        return 0.0
    return requests * cacheline / seconds / 1e9


def summarize_metrics(stats: Mapping[str, object], cacheline: int,
                      tck_ns: float) -> dict[str, float]:
    """One-call summary dict for event-driven architecture reporting."""
    cycles = stats.get("dram_cycles", 0) or 0
    latency = avg_read_latency(stats)
    return {
        "read_requests": stats.get("read_requests", 0) or 0,
        "write_requests": stats.get("write_requests", 0) or 0,
        "dram_cycles": cycles,
        "avg_read_latency_cycles": latency,
        "avg_read_latency_ns": latency * tck_ns,
        "row_hit_rate": row_hit_rate(stats),
        "bandwidth_gbs": measured_bandwidth(stats, cacheline, tck_ns),
    }

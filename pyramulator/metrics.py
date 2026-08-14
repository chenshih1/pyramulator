"""Derived performance metrics computed from Ramulator statistics.

Ramulator only finalizes aggregate stats (latency averages, bandwidth) in
``finish()``; these helpers compute them on demand from the raw counters
returned by ``MemorySystem.get_stats()``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

_LAT_SUM_RE = re.compile(r"read_latency_sum_(\d+)$")
_ROW_HITS_RE = re.compile(r"read_row_hits_channel_(\d+)_core$")
_ROW_MISSES_RE = re.compile(r"read_row_misses_channel_(\d+)_core$")
_ROW_CONFLICTS_RE = re.compile(r"read_row_conflicts_channel_(\d+)_core$")


def _sum_matching(stats: Mapping[str, object], pattern: re.Pattern) -> float:
    return sum(v for k, v in stats.items()
               if pattern.match(k) and isinstance(v, (int, float)))


def _num(stats: Mapping[str, object], key: str) -> float:
    value = stats.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.0


def avg_read_latency(stats: Mapping[str, object]) -> float:
    """Average read latency in DRAM clock cycles (all channels)."""
    total = _sum_matching(stats, _LAT_SUM_RE)
    requests = _num(stats, "read_requests")
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
    requests = _num(stats, "read_requests") + _num(stats, "write_requests")
    cycles = _num(stats, "dram_cycles")
    seconds = cycles * tck_ns * 1e-9
    if seconds <= 0:
        return 0.0
    return requests * cacheline / seconds / 1e9


def summarize_metrics(stats: Mapping[str, object], cacheline: int,
                      tck_ns: float) -> dict[str, float]:
    """One-call summary dict for event-driven architecture reporting."""
    latency = avg_read_latency(stats)
    return {
        "read_requests": _num(stats, "read_requests"),
        "write_requests": _num(stats, "write_requests"),
        "dram_cycles": _num(stats, "dram_cycles"),
        "avg_read_latency_cycles": latency,
        "avg_read_latency_ns": latency * tck_ns,
        "row_hit_rate": row_hit_rate(stats),
        "bandwidth_gbs": measured_bandwidth(stats, cacheline, tck_ns),
    }

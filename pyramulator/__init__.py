"""Pyramulator: discrete-event simulation for hardware architecture.

A DES framework — :class:`Simulator` kernel, hardware primitives
(:class:`Clock`, :class:`Component`, :class:`FIFO`, :class:`Pipe`) — with
a cycle-accurate DRAM timing model (Ramulator) embedded as the
:class:`Dram` component. Time is counted in integer picoseconds; events
are processed with next-event time advance, never stepping through empty
cycles.
"""

from __future__ import annotations

from pyramulator._engine import Config, RequestInfo, RequestType
from pyramulator._version import __version__
from pyramulator.benchmark import (
    benchmark_all,
    benchmark_bandwidth,
    benchmark_latency,
)
from pyramulator.configs import (
    config_dir,
    estimate_capacity,
    supported_orgs,
    supported_speeds,
    supported_standards,
    theoretical_bandwidth,
)
from pyramulator.dram import Dram
from pyramulator.hardware import FIFO, Clock, Component, Pipe
from pyramulator.metrics import (
    avg_read_latency,
    measured_bandwidth,
    row_hit_rate,
    summarize_metrics,
)
from pyramulator.sim import Simulator
from pyramulator.workload import address_stream, split_read_write

__all__ = [
    "FIFO",
    "Clock",
    "Component",
    "Config",
    "Dram",
    "Pipe",
    "RequestInfo",
    "RequestType",
    "Simulator",
    "__version__",
    "address_stream",
    "avg_read_latency",
    "benchmark_all",
    "benchmark_bandwidth",
    "benchmark_latency",
    "config_dir",
    "estimate_capacity",
    "measured_bandwidth",
    "row_hit_rate",
    "split_read_write",
    "summarize_metrics",
    "supported_orgs",
    "supported_speeds",
    "supported_standards",
    "theoretical_bandwidth",
]

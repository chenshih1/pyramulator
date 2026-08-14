# pyramulator

[![CI](https://img.shields.io/github/actions/workflow/status/chenshih1/pyramulator/ci.yml?branch=master&label=CI)](https://github.com/chenshih1/pyramulator/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)

Python bindings for the [Ramulator](https://github.com/CMU-SAFARI/ramulator)
DRAM simulator.

A thin, event-driven Python wrapper over Ramulator 1.x for DRAM-side
simulation of custom hardware accelerator architectures: cycle-accurate
latency, bandwidth and row-buffer behaviour without modifying a single line
of Ramulator.

## Features

- **Cycle-accurate DRAM timing** — DDR3/4, LPDDR3/4, GDDR5, WideIO/2, HBM,
  SALP, with channel/rank scaling and per-standard timing
- **Event-driven API** — non-blocking request send with backpressure, async
  completion callbacks (`RequestInfo` with latency and core id), write
  barrier (`flush()`), drain (`run_until_idle()`)
- **Unmodified Ramulator** — only its public API is used, exactly like
  gem5's `Gem5Wrapper`; Ramulator is a pinned git submodule
- **Fast** — batched C++ simulation (`run`, `send_batch`, `send_range`)
  keeps per-request Python overhead low (~150K req/s sustained)
- **Programmable statistics** — `get_stats()` exposes all 170+ Ramulator
  counters (latency, row hits/misses, queue depths, bandwidth) plus derived
  metrics helpers (`avg_read_latency`, `row_hit_rate`, `measured_bandwidth`)
- **Helpers** — address-stream generators, one-call benchmarks, capacity
  estimation, theoretical bandwidth

## Install

Ramulator is an external dependency, registered as a git submodule at
`third_party/ramulator` (pinned to a fixed commit), so the build needs
network access.

```bash
git clone --recurse-submodules <repo-url>   # or: git submodule update --init
pip install .
```

When building from an sdist (which has no submodule), CMake falls back to
fetching ramulator from its upstream repository via `FetchContent`.

## Quick start

```python
from pyramulator import Config, MemorySystem, RequestType

cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")
mem = MemorySystem(cfg, cacheline=64)

completed = []
mem.send_read(0x1000, callback=lambda info: completed.append(info))
mem.run(1000)                # or mem.tick() per cycle

print(completed[0])          # RequestInfo(addr=4096, type=READ, arrive=.., depart=.., core_id=0)
print(completed[0].latency)  # latency in DRAM clock cycles
```

## How Ramulator is wrapped

The wrapper follows the same approach gem5 uses for Ramulator, and only
calls Ramulator's public API — **no Ramulator source is modified**:

- **Simulation core**: `MemoryFactory::create` + the `MemoryBase` interface
  (`tick` / `send` / `finish`), the same calls gem5's `Gem5Wrapper` makes.
- **Configuration**: `Config.add` / `contains` / `set_core_num` only. There
  is no value-overwrite setter; `Config.from_file` parses the `.cfg` text in
  Python and rebuilds a fresh `Config` with the overrides applied.
- **Request completion**: read completions are delivered via Ramulator's
  callback (it already fires for reads). Ramulator has no write-completion
  callback upstream, so — like gem5, which answers writes immediately upon
  acceptance — write callbacks fire right when the request is accepted. Use
  `mem.flush()` if you need to wait until writes are truly serviced by the
  DRAM.

## Event-driven simulation

A typical accelerator-simulation loop:

```python
mem = MemorySystem(cfg)
done = [0]

def on_complete(info):   # your completion handler
    done[0] += 1

issued = 0
addr = 0
while done[0] < NUM_REQUESTS:
    # 1. keep the request queue full (backpressure: send returns False
    #    when the queue is full — retry next cycle)
    while issued - done[0] < 32 and issued < NUM_REQUESTS:
        if mem.send_read(addr, callback=on_complete):
            issued += 1
            addr += 64
        else:
            break
    # 2. advance the DRAM clock (batched inside C++ for speed)
    mem.run(1000)

mem.flush()                  # drain remaining reads AND writes
```

For initial bursts, `send_read_blocking(addr)` blocks until accepted;
`send_reads()` / `send_writes()` / `send_reads_range()` / `send_writes_range()`
batch many requests in one C++ call.

For a self-contained drive loop — the role gem5's MemCtrl scheduler plays —
`drive()` / `drive_range()` run the whole backpressure + tick + drain loop
inside C++:

```python
issued = mem.drive_range(0, NUM_REQUESTS, 64, queue_depth=32, batch=200,
                         callback=on_complete)
```

`batch` trades scheduling granularity for cycle efficiency: ~`queue_depth x 6`
cycles wastes no DRAM time (measured at parity with the Python loop,
~150K req/s, with the loop overhead removed).

### Address mapping

The channel/bank/row interleaving scheme is selectable via `mapping`
(Ramulator honors it for DDR3):

```python
cfg = Config(standard="DDR3", speed="DDR3_1600K", org="DDR3_2Gb_x8",
             mapping="cacheline_interleaving")   # row_interleaving, *_randomized, defaultmapping
```

### Statistics

```python
mem.reset_stats()                 # per simulation phase
mem.run_until_idle()
stats = mem.get_stats()           # 170+ raw Ramulator counters
print(stats["read_requests"], stats["read_latency_sum_0"])

from pyramulator import metrics
print(mem.metrics())              # derived summary dict:
# {'read_requests': 256, 'dram_cycles': 1460, 'avg_read_latency_cycles': 193.2,
#  'avg_read_latency_ns': 161.0, 'row_hit_rate': 0.98, 'bandwidth_gbs': 13.5}
```

### Benchmarks and address streams

```python
from pyramulator import benchmark_latency, benchmark_bandwidth, addresses

benchmark_latency(cfg, num_requests=256, mode="random", seed=42)
benchmark_bandwidth(cfg, num_requests=256)

addrs = addresses("sequential", 256, cacheline=64)   # or "strided" / "random"
mem.send_reads(addrs)
```

## Supported DRAM Standards

DDR3, DDR4, LPDDR3, LPDDR4, GDDR5, WideIO, WideIO2, HBM,
SALP-1, SALP-2, SALP-MASA

## Performance

The DRAM model itself is simulated at C++ speed (~3.6M DRAM cycles/s on a
single channel DDR4). Sustained request throughput with per-request Python
callbacks is ~150K req/s; callbacks are delivered in batches (no per-event
GIL round-trip). See `bench/bench.py` for measured latency and bandwidth
across standards.

## Development

Build, test and check inside a local virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # includes test, ruff, mypy, pytest-cov

pytest                       # 79 tests, ~95% coverage
ruff check pyramulator/ test/ bench/ examples/
mypy pyramulator/
python bench/bench.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Project Layout

- `src/bindings.cpp` — pybind11 bindings (the only C++ in this project)
- `pyramulator/` — pure-Python wrapper API
  - `configs.py` — standards/speed/org tables, capacity & bandwidth estimation
  - `metrics.py` — derived performance metrics
  - `workload.py` — address-stream generators
  - `benchmark.py` — one-call latency/bandwidth benchmarks
- `third_party/ramulator` — Ramulator as a git submodule (pinned commit), used unmodified
- Ramulator is not vendored; see `git submodule status` and <https://github.com/CMU-SAFARI/ramulator>

## License

MIT — see [LICENSE](LICENSE). Ramulator itself is MIT-licensed (Copyright
2015 SAFARI Research Group, Carnegie Mellon University).

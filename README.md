# pyramulator

[![CI](https://img.shields.io/github/actions/workflow/status/chenshih1/pyramulator/ci.yml?branch=master&label=CI)](https://github.com/chenshih1/pyramulator/actions)
[![Release](https://img.shields.io/github/v/release/chenshih1/pyramulator?label=release&logo=github)](https://github.com/chenshih1/pyramulator/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)

A discrete-event simulation (DES) framework for hardware architecture,
with a cycle-accurate DRAM timing model — Ramulator — embedded as the
[`Dram`](#dram-component) component.

The simulator kernel uses the classic next-event time-advance mechanism:
time jumps from event to event and never steps through empty cycles.
Components (a 1 GHz accelerator, a DDR4 controller, a 500 MHz HBM ...)
each own a `Clock` and schedule work as events; the DRAM ticks only
while requests are in flight, so an idle memory costs zero events.

## Features

- **DES kernel** — `Simulator` with next-event time advance, deterministic
  event ordering (priority, then FIFO at equal time), zero-delay delta
  events, event cancel, `next_time` peeking, per-component event counts,
  and `step` / `run` / `run_until_idle` drivers
- **Hardware primitives** — `Clock` (integer-ps periods), `Component`
  base class, bounded combinational `FIFO`, fixed-latency `Pipe` stages
  with bounded occupancy and consumer backpressure (stall/retry)
- **Cycle-accurate DRAM timing** — DDR3/4, LPDDR3/4, GDDR5, WideIO/2, HBM,
  SALP, with channel/rank scaling and per-standard timing (JEDEC timing
  parameters via Ramulator 1.x)
- **`Dram` component** — non-blocking `read`/`write`/`reads`/`writes`
  with backpressure, read completions delivered as events at the DRAM
  tick time, optional wall-clock `idle_refresh`, `flush()` write
  barrier, per-instance Ramulator statistics (170+ counters) and derived
  metrics
- **Unmodified Ramulator** — only its public API is used, exactly like
  gem5's `Gem5Wrapper`; Ramulator is a pinned git submodule
- **Fast** — the engine ticks in C++; events are batched across the
  Python boundary (~150K req/s sustained with per-request callbacks)
- **Helpers** — address-stream generators, one-call benchmarks, capacity
  estimation, theoretical bandwidth

## Install

Build from source (requires Python >= 3.8 and a C++17 compiler; pybind11
and CMake are resolved automatically):

```bash
git clone --recurse-submodules https://github.com/chenshih1/pyramulator.git
cd pyramulator
pip install .
```

Ramulator is an external dependency pinned at `third_party/ramulator`
(a git submodule). If it is missing, the build downloads the pinned
source tarball automatically — with retries and a configurable mirror
(`-DPYRAMULATOR_RAMULATOR_TARBALL_URL=...`, disable with
`-DPYRAMULATOR_FETCH_RAMULATOR=OFF`) — so no manual `git submodule
update --init` is needed.

## Quick start

```python
from pyramulator import Simulator, Dram, Config

sim = Simulator()
dram = Dram(sim, Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8"))

completed = []
dram.read(0x1000, callback=lambda info: completed.append(info))
sim.run_until_idle()          # completions arrive as events

print(completed[0])           # RequestInfo(addr=4096, type=READ, arrive=.., depart=.., core_id=0)
print(completed[0].latency)   # latency in DRAM clock cycles
```

## The DES kernel

Time is an integer count of picoseconds. The `Simulator` never advances
time past an event without processing it — a run that only touches the
DRAM in cycle 0 and cycle 4000 advances straight from 0 to 4000:

```python
sim = Simulator()
sim.schedule(4000, lambda: print("t=4000"))  # 4000 ps from now
sim.schedule(0, lambda: print("t=0"), priority=-1)  # same time, earlier priority
sim.run()                                     # processes every event
```

- Events at the same time run in **priority order** (lower value first),
  then **insertion order** (FIFO) — fully deterministic.
- Callbacks may schedule **zero-delay delta events** at the current time;
  they run after already-queued events at that time.
- `schedule(delay, ...)` / `at(time, ...)` return an event id;
  `cancel(id)` removes a pending event. `next_time` peeks at the next
  event's time without running anything.
- `step()` processes one event, `run(until=...)` processes events up to
  an absolute time (inclusive), `run(max_events=...)` bounds the count.
- `event_counts` reports how many events each named source scheduled
  (`Component.schedule_*` attributes its events to the component) —
  handy for profiling which part of the architecture generates load.

## Hardware primitives

```python
from pyramulator import Clock, Component, FIFO, Pipe

host = Clock(1000, "host")      # 1 GHz

class MyCore(Component):
    def __init__(self, sim, clk, name="core"):
        super().__init__(sim, clk, name)
        self.issue_q = FIFO(sim, clk, capacity=16)
        self.pipe = Pipe(sim, clk, latency_cycles=4, slots=2,
                         consumer=self._on_pipe_out)
```

- `Clock(period_ps, name)` — `clk.cycles(n)` converts cycle counts to
  simulator time.
- `FIFO(sim, clk, capacity)` — bounded, combinational (state changes
  immediately when the owning component processes an event); `put` /
  `get` / `peek` / `can_put` / `can_get` / `clear`.
- `Pipe(sim, clk, latency_cycles, slots, consumer)` — a fixed-latency
  pipeline stage with bounded occupancy; `put` returns False when full
  and delivers items to the consumer exactly `latency_cycles` later.
  A consumer returning `False` stalls the last stage: the item stays
  put and delivery is retried every cycle until accepted (any other
  return value, including `None`, accepts — existing consumers are
  unaffected).

## Dram component

`Dram` embeds the Ramulator engine behind events:

- It owns a clock at the DRAM tCK (rounded to integer ps) and ticks the
  engine **only while requests are in flight** — an idle DRAM schedules
  nothing.
- `read(addr, callback=None, core_id=0)` / `write(...)` / `reads(addrs)`
  / `writes(addrs)` are non-blocking with backpressure (False = queue
  full); accepted requests are counted in `dram.pending`.
- Read completions are delivered as events at the DRAM tick time, with
  `RequestInfo.latency` in DRAM clock cycles. `completion_priority`
  controls their order relative to other same-time events.
- **Write completion**: Ramulator has no upstream write-completion
  callback (writes never enter its `pending` list), so write callbacks
  fire upon acceptance — with zero latency. Use `dram.flush()` as a
  barrier when writes must be truly serviced before proceeding:

```python
for i in range(64):
    dram.write(i * 64)
dram.flush()                  # blocks until the DRAM queue is empty
```

- `core_id` is validated against `num_cores` (Ramulator indexes
  per-core statistic arrays with `coreid`; out-of-range ids would
  corrupt the C++ heap silently).

### Event-driven accelerator loop

Components driven purely by completions (each `_on_complete` re-issues)
never poll — the DRAM's tick chain is the only recurring event source:

```python
mem = Dram(sim, cfg)
done = [0]

def on_complete(info):   # your completion handler (runs as an event)
    done[0] += 1

issued = 0
addr = 0
while done[0] < NUM_REQUESTS:
    # 1. keep the request queue full (backpressure: read returns False
    #    when the queue is full — retry on the next completion)
    while issued - done[0] < 32 and issued < NUM_REQUESTS:
        if mem.read(addr, callback=on_complete):
            issued += 1
            addr += 64
        else:
            break
    # 2. advance time to the next event (a DRAM tick or completion)
    sim.step()

mem.flush()                # drain remaining reads AND writes
```

### Idle refreshes and wall-clock time

By default an idle DRAM schedules nothing, so Ramulator's refresh timer
only advances while requests are in flight. For studies where idle
refreshes must contend with wall-clock time (e.g. long idle gaps before
a latency-sensitive burst), construct the component with
`Dram(sim, cfg, idle_refresh=True)`: a coarse idle clock (one event per
`idle_batch_cycles`, default 1024) keeps refresh advancing like the
reference integration. With idle refresh enabled the DRAM never goes
idle, so drive the simulator with `run(until=...)` rather than
`run_until_idle()`.

## Statistics

Per-instance Ramulator counters and derived metrics:

```python
dram.reset_stats()                 # per simulation phase
for i in range(32):                # 32 reads fit the queue; all accepted
    dram.read(i * 64)
sim.run_until_idle()
stats = dram.get_stats()           # 170+ raw Ramulator counters
print(stats["read_requests"], stats["read_latency_sum_0"])

print(dram.metrics())              # derived summary dict:
# {'read_requests': 32.0, 'write_requests': 0.0, 'dram_cycles': 223.0,
#  'avg_read_latency_cycles': 130.0, 'avg_read_latency_ns': 108.3,
#  'row_hit_rate': 0.97, 'bandwidth_gbs': 11.0}
```

## Address mapping and configuration

The channel/bank/row interleaving scheme is selectable via `mapping`
(Ramulator honors it for DDR3):

```python
cfg = Config(standard="DDR3", speed="DDR3_1600K", org="DDR3_2Gb_x8",
             mapping="cacheline_interleaving")   # row_interleaving, *_randomized, defaultmapping
```

`Config` also validates itself (`cfg.validate()`), and the bundled
reference configurations are available via `config_dir()`.

## Benchmarks and address streams

```python
from pyramulator import benchmark_latency, benchmark_bandwidth, addresses

benchmark_latency(cfg, num_requests=256, mode="random", seed=42)
benchmark_bandwidth(cfg, num_requests=256)

addrs = addresses("sequential", 256, cacheline=64)   # or "strided" / "random"
```

## Supported DRAM Standards

DDR3, DDR4, LPDDR3, LPDDR4, GDDR5, WideIO, WideIO2, HBM,
SALP-1, SALP-2, SALP-MASA

## Performance

The DRAM model itself is simulated at C++ speed (~3.6M DRAM cycles/s on a
single channel DDR4). Sustained request throughput with per-request Python
callbacks is ~150K req/s; callbacks are delivered in batches (no per-event
GIL round-trip). Measured latency and bandwidth across standards are
reported by `bench/bench.py`.

## Examples

- `examples/spmm_hbm.py` — a naive single-PE SpMM accelerator streaming
  the dense matrix from an HBM timing model as DES components
  (event-driven issue loop with a bounded in-flight window, validated
  against numpy, reports cycles/bandwidth/row hits). Run with
  `python examples/spmm_hbm.py [channels]`.
- `examples/accel_sim.py` — multi-lane vector accelerator with a
  LOAD / COMPUTE / STORE pipeline per tile: event-driven load pumping,
  backpressure, write-acceptance semantics and the `flush()` barrier.

## Development

Build, test and check inside a local virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # includes test, ruff, mypy, pytest-cov

pytest                       # 144 tests
ruff check pyramulator/ test/ bench/ examples/
mypy pyramulator/
python bench/bench.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Project Layout

- `src/bindings.cpp` — pybind11 bindings (the only C++ in this project)
- `pyramulator/` — the DES framework
  - `__init__.py` — public API exports
  - `sim.py` — `Simulator` kernel (event queue, next-event time advance)
  - `hardware.py` — `Clock`, `Component`, `FIFO`, `Pipe`
  - `dram.py` — `Dram` component (Ramulator behind events)
  - `_memory.py` — internal cycle-stepped engine (Ramulator wrapper)
  - `configs.py` — standards/speed/org tables, capacity & bandwidth estimation
  - `metrics.py` — derived performance metrics
  - `workload.py` — address-stream generators
  - `benchmark.py` — one-call latency/bandwidth benchmarks
- `examples/` — runnable architecture examples (SpMM, vector accelerator)
- `bench/` — cross-standard latency/bandwidth benchmark script
- `test/` — pytest suite (engine, DES kernel, components)
- `third_party/ramulator` — Ramulator as a git submodule (pinned commit), used unmodified
- Ramulator is not vendored; see `git submodule status` and <https://github.com/CMU-SAFARI/ramulator>

## License

MIT — see [LICENSE](LICENSE). Ramulator itself is MIT-licensed (Copyright
2015 SAFARI Research Group, Carnegie Mellon University).

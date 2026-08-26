# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-08-26

### Added

- **DES framework (the project is now a discrete-event simulator for
  hardware architecture)**: `Simulator` kernel with next-event time
  advance, deterministic event ordering (priority, then FIFO), event
  cancel, and `run`/`run_until_idle`/`step` drivers. Time is counted in
  integer picoseconds; time jumps between events, never stepping through
  empty cycles.
- Hardware primitives: `Clock` (period in ps, cycle conversions),
  `Component` base class, `FIFO` (bounded, combinational), `Pipe`
  (fixed-latency pipeline stage with bounded occupancy).
- `Dram` DES component: embeds the Ramulator engine behind events. It
  owns a clock at the DRAM tCK and ticks the engine only while requests
  are in flight (an idle DRAM costs zero events); read completions are
  delivered as events at the DRAM tick time, with a configurable
  completion priority; `flush()` is a blocking write barrier.
- `core_id` validation against `num_cores` at the engine boundary —
  Ramulator indexes per-core statistic arrays with `coreid`, and an
  out-of-range id previously corrupted the C++ heap silently.
- Batch request interface on `Dram`: `reads(addrs)` / `writes(addrs)`
  send a whole burst in one engine call (completions still arrive as
  individual events).
- `Dram(idle_refresh=True)` keeps a coarse idle clock (one event per
  `idle_batch_cycles`) so Ramulator's refresh timer advances with
  wall-clock time, matching the reference integration; off by default
  (an idle DRAM then costs zero events).
- Kernel introspection: `Simulator.next_time` (peek at the next event
  time) and `Simulator.event_counts` (events scheduled per `source`
  name); `Component.schedule_*` attributes its events automatically.
- `Pipe` consumer backpressure: a consumer returning `False` stalls the
  last stage — the item is retried every cycle until accepted (None/True
  accept, so existing consumers are unaffected).

### Changed

- Public API is DES-first: `Simulator`, `Clock`, `Component`, `FIFO`,
  `Pipe`, `Dram`, `Config`, `RequestInfo`, `RequestType`, workload and
  benchmark helpers. The cycle-stepped `MemorySystem` wrapper moved to
  `pyramulator._memory` as the internal engine behind `Dram`.
- Benchmarks (`benchmark_latency`, `benchmark_bandwidth`,
  `benchmark_all`) now drive the DES framework; return shapes unchanged.
- Examples rewritten as DES components (`examples/spmm_hbm.py`,
  `examples/accel_sim.py`); both still validate against numpy where
  applicable.
- Version bumped to 0.4.0 (breaking API change).

### Fixed

- Write completion semantics documented at the component level: Ramulator
  has no upstream write-completion callback (writes never enter its
  `pending` list — verified in `Controller.cpp`), so writes complete upon
  acceptance; `Dram.flush()` is the barrier for "truly serviced".

### Refactored

- Removed dead/duplicated API surface: the module-level singleton
  `get_stats()` / `reset_stats()` (superseded by per-instance methods)
  and the `stats` property alias (use `get_stats()`).
- Deduplicated the engine's write-completion path (`send`,
  `send_writes`, `send_writes_range` now share one helper) and the
  `drive`/`drive_range` callback wrappers (reuse `_read_cb`).
- Deduplicated the C++ completion-callback construction across
  `send`/`send_batch`/`send_range` into one `make_callback` helper.
- Collapsed the four near-identical benchmark table loops in
  `bench/bench.py` into shared table helpers.

## [0.1.0] - 2026-08-14

### Added

- Python bindings for Ramulator 1.x via pybind11 (`Config`, `MemorySystem`,
  `RequestType`, `RequestInfo`).
- Ramulator as an external dependency: pinned git submodule
  (`third_party/ramulator`, commit `214f635`) with a `FetchContent` fallback
  for sdist builds. Only Ramulator's public API is used; no Ramulator source
  is modified. The wrapper follows gem5's `Gem5Wrapper` integration pattern.
- Event-driven simulation API:
  - non-blocking `send` with backpressure (bool return)
  - completion callbacks (`RequestInfo` with `addr`, `type`, `arrive`,
    `depart`, `latency`, `core_id`) for reads; writes complete upon
    acceptance (like gem5 — Ramulator has no upstream write callback)
  - `tick`, `run`, `run_until_idle`, `flush()` write barrier
  - blocking send variants (`send_read_blocking`, ...)
  - batch APIs for throughput: `send_reads`, `send_writes`,
    `send_reads_range`, `send_writes_range`, C++-side batched `run`
- Statistics: `get_stats()` / `reset_stats()` exposing all Ramulator
  counters per instance (safe with multiple live instances), and derived
  metrics (`avg_read_latency`, `row_hit_rate`, `measured_bandwidth`,
  `MemorySystem.metrics()`).
- Configuration helpers: kwargs-based `Config`, `Config.from_file` with
  overrides (Python-side .cfg parsing), `validate()`, `estimate_capacity`,
  `theoretical_bandwidth`, per-standard minimum cacheline validation.
- Workload helpers: `addresses()` (sequential / strided / random), and
  one-call benchmarks (`benchmark_latency`, `benchmark_bandwidth`,
  `benchmark_all`).
- Bundled Ramulator reference configs (`pyramulator.data.configs` /
  `pyramulator.config_dir()`).

### Changed

- Vendored `src/ramulator` copy removed in favour of the submodule.
- `Config.set()` removed (Ramulator public API has no value overwrite).

### Performance

- Completion events are batched in C++ (no per-event GIL round-trip).
- `run` / `run_until_idle` execute the tick loop inside C++.
- Sustained request throughput ~150K req/s with per-request callbacks;
  DRAM simulation ~3.6M cycles/s single channel.

[0.4.0]: https://gitee.com/chenshih1/pyramulator/releases/tag/v0.4.0
[0.1.0]: https://gitee.com/chenshih1/pyramulator/releases/tag/v0.1.0

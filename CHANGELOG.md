# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `examples/pipe_fifo_dram.py` — architecture composition template:
  `Pipe` + `FIFO` + `Dram` on two clocks, with Pipe-consumer backpressure
  into a bounded issue FIFO and into `Dram.write`. Tests cover the same
  wiring in `tests/test_des.py`.
- README hardware-primitives snippet now wires `Pipe`/`FIFO` to `Dram`
  (the previous snippet constructed them but never connected them).

### Changed

- `docs/quickstart.rst` Python floor is 3.10 (was still 3.8 after 0.5.0).
- `scripts/build_pgo.py` trains on `benchmarks/bench.py` (the 0.5.0
  directory rename) and includes the new composition example.
- `Dram` coalesces empty in-flight DRAM cycles into one C++
  `tick_until_progress` call when no other simulator event or
  `run(until=)` horizon falls in that window, then jumps simulator
  time to the cycle that made progress. Completions are still
  delivered as zero-delay events at that cycle; `RequestInfo`,
  backpressure, and event order relative to other components are
  unchanged.
- `Simulator.run()` no longer double-peeks the event heap per event;
  heap ordering uses a stored `(time, priority, seq)` key.

### Fixed

<<<<<<< HEAD
- `Dram` coalescing now clips empty-cycle bursts to the active
  `Simulator.run(until=)` horizon, not only the next heap event. An
  in-flight request no longer jumps `sim.now` past *until*, drops
  `dram.pending` to 0, and leaves the completion callback unfired.
  Incremental `run(until=)` windows and `idle_refresh` + `run(until=...)`
  stop at the requested time.
=======
- `examples/pipe_fifo_dram.py`: `_on_load` no longer treats
  `compute_pipe.put` as infallible because `compute_slots >=
  max_outstanding`. A completed load still occupies a compute slot after
  `_reads_inflight` drops, so the read pump reserves pipe occupancy and
  holds completions that find the pipe full. `put` is not inside
  `assert` (which `python -O` would strip, dropping stores).
>>>>>>> c49104a (fix: bound compute-pipe occupancy in the FIFO+Dram copy engine)
- `MemorySystem.drive()` / `drive_range()` reset the in-flight completion
  counter at the start of each call, so a second drive on the same
  instance actually drains.
- `Dram` idle-refresh backoff now restarts after a busy stretch, so the
  first idle event ticks the same number of DRAM cycles as it was
  scheduled for (a grown batch previously ran over a short delay and
  desynchronized `dram.cycles` from wall-clock time).
- `MemorySystem.drive()` / `drive_range()` reject non-positive `batch` or
  `queue_depth` (``batch=0`` with more requests than the queue depth
  spun forever without ticking).
- `Simulator.cancel()` of the currently running event returns False and
  does not decrement ``pending`` a second time.
- `split_read_write()` docstring now matches the independent random split
  (it previously claimed writes were taken from the tail of the list).

## [0.5.2] - 2026-08-27

### Fixed

- Moved `_core.pyi` to `pyramulator/_core.pyi` so type checkers can find it.
- Typed `RequestType` enum members as `ClassVar[RequestType]` in the stub.
- `MemorySystem.drive()` now converts `Iterable[int]` to `list[int]` before
  passing to the C++ layer (prevents failures with generators).
- Replaced runtime `assert` in `Dram._start_ticking()` with `RuntimeError`.
- Fixed `theoretical_bandwidth()` config variable typing.

### Added

- Extreme simulation tests (`tests/test_extreme.py`).
- Edge-case tests (`tests/test_edge_cases.py`).
- HBM-specific tests (`tests/test_memory.py::TestHBM`).

## [0.5.1] - 2026-08-27

### Removed (internal engine cleanup)

- Removed unused `MemorySystem` methods from `_engine.py` — blocking
  sends (`send_blocking`, `send_read_blocking`, `send_write_blocking`),
  the pull-model `completions()` + `collect_events` support, `finish()`,
  and the `__enter__`/`__exit__` context manager. `MemorySystem` is the
  internal engine behind `Dram`; the public `pyramulator` API is
  unchanged.

### Changed

- `Dram._deliver_completed` extracts `_make_completion_cb` (mypy fix).
- README: documents configuration helpers (`estimate_capacity`,
  `theoretical_bandwidth`, `supported_*`), `split_read_write`,
  `benchmark_all`, and the event-scheduling DES paradigm.
- docs/: added API pages for `metrics`, `workload`, `configs`.

### Removed (tests)

- Dropped tests for the removed engine methods (5 tests); suite now
  has 150 tests at 97% coverage.

## [0.5.0] - 2026-08-27

### Changed (breaking)

- **API renames for clarity** (breaking):
  - `RequestInfo.arrive` / `RequestInfo.depart` → `arrive_cycle` /
    `depart_cycle` — the fields are DRAM clock-cycle counts, not wall-
    clock timestamps; the new names state the unit explicitly.
  - `addresses()` → `address_stream()` — the generator name now carries
    the "generate a stream" action.
  - `read_write_mix()` → `split_read_write()` — the function splits a
    stream into reads and writes; the old name implied mixing.
- **Python floor raised to 3.10** (breaking): 3.8/3.9 reached end-of-
  life; numpy 2.x / pytest 8+ require 3.10+. Code now uses 3.10+
  features (`match`/`case`, `int.bit_count()`, `TypeAlias`).
- **CMake floor raised to 3.20** (breaking): modern `FindPython` and
  preset support; capped below 4.0 to avoid future incompatible major.
- `config_dir()` simplified: the Python 3.8 `importlib.resources`
  fallback was removed (3.10's `files()` is stable).

### Added

- `_core.pyi` hand-written type stubs for the C++ extension (mypy can
  now type-check the engine boundary).
- `docs/` Sphinx skeleton (`conf.py`, `index.rst`, quickstart, API pages).
- GitHub Issue templates (bug report, feature request).
- Single-source versioning via `pyramulator/_version.py`; `pyproject.toml`
  reads it dynamically.

### Changed

- Engine module renamed `_memory.py` → `_engine.py` (internal).
- Data tables split out of `configs.py` into `configs_data.py` (internal).
- `tests/` and `benchmarks/` directory names aligned with community
  convention (were `test/`, `bench/`); `src/` → `cpp/` for the native
  binding.
- Completion callback type extracted as `CompletionCallback` `TypeAlias`
  (used across `_engine.py` and `dram.py`).
- `Pipe` stall retry batches stalled items into one shared retry event
  instead of one event per item per cycle.
- `Dram` idle refresh batch size now backs off exponentially while idle.
- `Simulator.cancel()` is O(1) via an id → event map; `_by_id` is
  cleaned on `step()` to bound memory.
- C++ binding: `send_batch`/`send_range` reuse one completion callback;
  `drain_completed` preallocates the output list; `drive` converts the
  address list to `std::vector` once.
- Release builds add `-march=native`; PGO support via
  `scripts/build_pgo.py` (instrument → train → optimize).

### Fixed

- mypy error on lambda type inference in `Dram._deliver_completed`
  (extracted `_make_completion_cb`).
- `config_dir()` coverage gap; several hardware-primitive edge cases
  now tested (coverage 96%).

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
  `pyramulator._engine` as the internal engine behind `Dram`.
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
  `benchmarks/bench.py` into shared table helpers.

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
- Workload helpers: `address_stream()` (sequential / strided / random), and
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

[0.5.2]: https://github.com/chenshih1/pyramulator/releases/tag/v0.5.2
[0.5.1]: https://github.com/chenshih1/pyramulator/releases/tag/v0.5.1
[0.5.0]: https://github.com/chenshih1/pyramulator/releases/tag/v0.5.0
[0.4.0]: https://github.com/chenshih1/pyramulator/releases/tag/v0.4.0
[0.1.0]: https://github.com/chenshih1/pyramulator/releases/tag/v0.1.0

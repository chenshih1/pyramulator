# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[0.1.0]: https://gitee.com/chenshih1/pyramulator/releases/tag/v0.1.0

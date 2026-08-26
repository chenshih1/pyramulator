# Contributing

Thanks for considering contributing to pyramulator.

## Development setup

The build compiles the pybind11 bindings and Ramulator (from the pinned
submodule), so a C++17 toolchain and network access are required.

```bash
git clone --recurse-submodules <repo-url>
cd pyramulator

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Profile-Guided Optimization (PGO)

For release builds targeting the local machine, a PGO pass can improve
C++ engine throughput by 5–15 %:

```bash
python scripts/build_pgo.py
```

This compiles an instrumented wheel, runs `benchmarks/bench.py` to collect
execution profiles, and recompiles with `-fprofile-use`.  The script
requires GCC or Clang and is exercised in Linux CI only.

## Checks

All checks must pass before merging:

```bash
ruff check pyramulator/ tests/ benchmarks/ examples/          # lint
ruff format --check pyramulator/ tests/ benchmarks/ examples/ # formatting
mypy pyramulator/                                       # type check
pytest                                                  # tests (+ coverage)
python benchmarks/bench.py                                   # sanity benchmark
```

CI runs these on Python 3.10–3.13 with the submodule initialized.

## Testing

Tests live in `tests/` and are organized by topic:

- `test_config.py` — configuration, capacity, theoretical bandwidth
- `test_memory.py` — internal engine (`_engine.py`, statistics, batch APIs)
- `test_des.py` — DES kernel, hardware primitives, Dram component
- `test_helpers.py` — metrics, workload generators, benchmarks
- `test_metadata.py` — package metadata consistency

Shared fixtures are defined in `tests/conftest.py`. When adding functionality,
add tests for it and keep the suite green with coverage.

## Project layout

- `cpp/bindings.cpp` — pybind11 bindings; the only C++ in this project.
  It uses only Ramulator's public API (`MemoryFactory` + `MemoryBase`) —
  do not patch or modify `third_party/ramulator`.
- `pyramulator/` — the DES framework: `sim.py` (kernel), `hardware.py`
  (primitives), `dram.py` (DRAM component), `_engine.py` (internal engine)
- `third_party/ramulator` — Ramulator submodule (pinned commit)

## Commits

Write clear, imperative commit messages. Update `CHANGELOG.md` for notable
changes and `pyproject.toml` when the version changes.

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

## Checks

All checks must pass before merging:

```bash
ruff check pyramulator/ test/ bench/ examples/          # lint
ruff format --check pyramulator/ test/ bench/ examples/ # formatting
mypy pyramulator/                                       # type check
pytest                                                  # tests (+ coverage)
python bench/bench.py                                   # sanity benchmark
```

CI runs these on Python 3.8–3.13 with the submodule initialized.

## Testing

Tests live in `test/` and are organized by topic:

- `test_config.py` — configuration, capacity, theoretical bandwidth
- `test_memory.py` — internal engine (Ramulator wrapper, statistics, batch APIs)
- `test_des.py` — DES kernel, hardware primitives, Dram component
- `test_helpers.py` — metrics, workload generators, benchmarks
- `test_metadata.py` — package metadata consistency

Shared fixtures are defined in `test/conftest.py`. When adding functionality,
add tests for it and keep the suite green with coverage.

## Project layout

- `src/bindings.cpp` — pybind11 bindings; the only C++ in this project.
  It uses only Ramulator's public API (`MemoryFactory` + `MemoryBase`) —
  do not patch or modify `third_party/ramulator`.
- `pyramulator/` — the DES framework: `sim.py` (kernel), `hardware.py`
  (primitives), `dram.py` (DRAM component), `_memory.py` (internal engine)
- `third_party/ramulator` — Ramulator submodule (pinned commit)

## Commits

Write clear, imperative commit messages. Update `CHANGELOG.md` for notable
changes and `pyproject.toml` when the version changes.

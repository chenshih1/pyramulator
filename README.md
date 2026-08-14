# pyramulator

Python bindings for [Ramulator](https://github.com/CMU-SAFARI/ramulator) DRAM simulator.

Provides a thin Python wrapper over Ramulator 1.x for DRAM-side simulation of custom hardware accelerator architectures.

## Install

Ramulator is an external dependency, registered as a git submodule at `third_party/ramulator` (pinned to a fixed commit), so the build needs network access.

```bash
git clone --recurse-submodules <repo-url>   # or: git submodule update --init
pip install .
```

When building from an sdist (which has no submodule), CMake falls back to fetching ramulator from its upstream repository via `FetchContent`.

## How Ramulator is wrapped

The wrapper follows the same approach gem5 uses for Ramulator, and only calls
Ramulator's public API — no Ramulator source is modified:

- **Simulation core**: `MemoryFactory::create` + the `MemoryBase` interface
  (`tick` / `send` / `finish`), the same calls gem5's `Gem5Wrapper` makes.
- **Configuration**: `Config.add` / `contains` / `set_core_num` only. There is
  no value-overwrite setter; `Config.from_file` parses the `.cfg` text in
  Python and rebuilds a fresh `Config` with the overrides applied.
- **Request completion**: read completions are delivered via Ramulator's
  callback (it already fires for reads). Ramulator has no write-completion
  callback upstream, so — like gem5, which answers writes immediately upon
  acceptance — write callbacks fire right when the request is accepted.

## Usage

```python
from pyramulator import Config, MemorySystem, RequestType

cfg = Config()
cfg.add("standard", "DDR4")
cfg.add("channels", "1")
cfg.add("ranks", "1")
cfg.add("speed", "DDR4_2400R")
cfg.add("org", "DDR4_4Gb_x8")

mem = MemorySystem(cfg, cacheline=64)

completed = []
mem.send(0x1000, RequestType.READ, coreid=0,
         callback=lambda addr, t: completed.append(addr))

for _ in range(1000):
    mem.tick()

mem.finish()
```

## Supported DRAM Standards

DDR3, DDR4, LPDDR3, LPDDR4, GDDR5, WideIO, WideIO2, HBM, SALP-1, SALP-2, SALP-MASA

## Development

Build and test inside a local virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest
```

## Project Layout

- `src/bindings.cpp` - pybind11 bindings (the only C++ in this project)
- `pyramulator/` - pure-Python wrapper API
- `third_party/ramulator` - Ramulator as a git submodule (pinned commit), used unmodified
- Ramulator is not vendored; see `git submodule status` and <https://github.com/CMU-SAFARI/ramulator>

# pyramulator

Python bindings for [Ramulator](https://github.com/CMU-SAFARI/ramulator) DRAM simulator.

Provides a thin Python wrapper over Ramulator 1.x for DRAM-side simulation of custom hardware accelerator architectures.

## Install

```bash
pip install .
```

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

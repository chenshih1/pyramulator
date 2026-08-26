---
name: Bug report
about: Report a problem with pyramulator
title: ""
labels: bug
---

## Environment

- OS / Python version:
- Installation method (git clone / sdist / wheel):
- C++ compiler (if built locally):

## Description

What did you expect to happen, and what actually happened?

## Reproduction

Minimal code to reproduce:

```python
from pyramulator import Config, Dram, Simulator

sim = Simulator()
dram = Dram(sim, Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8"))
dram.read(0x1000)
sim.run_until_idle()
...
```

## Expected behavior

## Actual behavior

(Include the full error message / traceback.)

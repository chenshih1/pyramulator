"""Address-stream generators for driving memory simulations."""

from __future__ import annotations

import random as _random
from collections.abc import Sequence


def addresses(mode: str = "sequential", count: int = 256,
              cacheline: int = 64, start: int = 0, stride: int = 64,
              seed: int | None = None, max_addr: int = 1 << 26) -> list[int]:
    """Generate `count` cacheline-aligned addresses.

    Modes:
      sequential - start, start+cacheline, start+2*cacheline, ...
      strided    - start, start+stride, start+2*stride, ...
      random     - uniform, cacheline-aligned addresses in [0, max_addr);
                   deterministic for a given seed

    Returns a list of ints, ready for ``send_reads`` / ``send_writes``.
    """
    if mode == "sequential":
        return [start + i * cacheline for i in range(count)]
    if mode == "strided":
        return [start + i * stride for i in range(count)]
    if mode == "random":
        rng = _random.Random(seed)
        return [rng.randrange(0, max_addr, cacheline) for _ in range(count)]
    raise ValueError(f"unknown address mode: {mode!r} "
                     "(choose from sequential, strided, random)")


def read_write_mix(addrs: Sequence[int], write_fraction: float = 0.0,
                   seed: int | None = None) -> tuple[list[int], list[int]]:
    """Split an address stream into (read_addrs, write_addrs).

    Writes are taken from the tail of the list so consecutive addresses stay
    contiguous in each stream."""
    rng = _random.Random(seed)
    reads, writes = [], []
    for addr in addrs:
        if rng.random() < write_fraction:
            writes.append(addr)
        else:
            reads.append(addr)
    return reads, writes

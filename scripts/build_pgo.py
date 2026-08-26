#!/usr/bin/env python3
"""Automated PGO (Profile-Guided Optimization) build for pyramulator.

Usage:
    python scripts/build_pgo.py

Steps:
  1. Compile with -fprofile-generate (instrumented build).
  2. Run benchmarks/bench.py to collect execution profiles.
  3. Re-compile with -fprofile-use (optimized build).

Requires GCC or Clang. The profile directory is shared across both builds
via cmake.define.PYRAMULATOR_PGO_DIR.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_PGO_DIR = ROOT / "build" / "pgo-data"


def run(cmd: list[str | Path], cwd: Path = ROOT) -> None:
    print(f"+ {' '.join(str(c) for c in cmd)}")
    subprocess.check_call(cmd, cwd=cwd)


def clean_build_dirs() -> None:
    for sub in ("generate", "use"):
        d = ROOT / "build" / sub
        if d.exists():
            shutil.rmtree(d)


def phase_generate(pgo_dir: Path) -> None:
    print("\n=== Phase 1: instrumented build (-fprofile-generate) ===")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            ".",
            "-C",
            "build-dir=build/generate",
            "-C",
            "cmake.define.PYRAMULATOR_PGO_MODE=GENERATE",
            "-C",
            f"cmake.define.PYRAMULATOR_PGO_DIR={pgo_dir}",
        ]
    )


def _train(script: Path) -> None:
    print(f"\n--- Training: {script.name} ---")
    run([sys.executable, str(script)])


def phase_train(train_script: Path | None = None) -> None:
    print("\n=== Phase 2: comprehensive PGO training ===")

    # 1. Standard benchmarks (latency, bandwidth, channel scaling)
    _train(train_script if train_script else ROOT / "bench" / "bench.py")

    # 2. Real-world architecture examples (SpMM, vector accelerator)
    for example in ("spmm_hbm.py", "accel_sim.py"):
        path = ROOT / "examples" / example
        if path.exists():
            _train(path)

    # 3. Synthetic micro-benchmarks to cover write path, batch APIs,
    #    idle refresh, and all supported DRAM standards.
    print("\n--- Training: micro-benchmarks (writes, batch, idle, standards) ---")
    _run_micro_benchmarks()


def _run_micro_benchmarks() -> None:
    """Execute inline Python snippets to exercise code paths not hit by bench.py."""
    code = '''
import sys
sys.path.insert(0, str(""" + str(ROOT) + """))

from pyramulator import Config, Simulator, Dram, benchmark_latency, benchmark_bandwidth
from pyramulator._engine import MemorySystem

# ---- Write path + write queue watermark ----
cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")
mem = MemorySystem(cfg)
mem.set_write_queue_watermark(high=0.8, low=0.2)
for i in range(64):
    mem.send_write(i * 64)
mem.run(2000)

# ---- Batch read/write APIs ----
mem2 = MemorySystem(cfg)
mem2.send_reads(range(0, 64 * 8, 64))
mem2.send_writes(range(0, 64 * 8, 64))
mem2.drive(list(range(0, 64 * 16, 64)), queue_depth=8, batch=20)
mem2.drive_range(0, 16, 64, queue_depth=8)
mem2.run_until_idle()

# ---- Idle refresh path ----
sim = Simulator()
dram = Dram(sim, cfg, idle_refresh=True, idle_batch_cycles=512)
for i in range(8):
    dram.read(i * 64)
sim.run(until=5_000 * dram.period_ps)
dram.flush()

# ---- Touch diverse standards (single request each to cover create/tick paths) ----
for std, speed, org in [
    ("DDR3", "DDR3_1600K", "DDR3_2Gb_x8"),
    ("DDR4", "DDR4_2400R", "DDR4_4Gb_x8"),
    ("LPDDR4", "LPDDR4_2400", "LPDDR4_8Gb_x16"),
    ("GDDR5", "GDDR5_5000", "GDDR5_2Gb_x32"),
    ("HBM", "HBM_1Gbps", "HBM_1Gb"),
    ("SALP-1", "SALP_1600K", "SALP_2Gb_x8"),
]:
    try:
        c = Config(standard=std, speed=speed, org=org)
        m = MemorySystem(c)
        m.send_read(0x1000)
        m.run(100)
        m.get_stats()
        m.reset_stats()
    except Exception:
        pass  # skip unsupported or mis-configured standards in PGO training

# ---- Benchmark wrappers (small scale) ----
benchmark_latency(cfg, num_requests=32, mode="sequential")
benchmark_latency(cfg, num_requests=32, mode="random", seed=42)
benchmark_bandwidth(cfg, num_requests=32)

print("Micro-benchmarks done.")
'''
    run([sys.executable, "-c", code])


def phase_use(pgo_dir: Path) -> None:
    print("\n=== Phase 3: optimized build (-fprofile-use) ===")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            ".",
            "-C",
            "build-dir=build/use",
            "-C",
            "cmake.define.PYRAMULATOR_PGO_MODE=USE",
            "-C",
            f"cmake.define.PYRAMULATOR_PGO_DIR={pgo_dir}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build pyramulator with Profile-Guided Optimization"
    )
    parser.add_argument(
        "--pgo-dir",
        type=Path,
        default=DEFAULT_PGO_DIR,
        help="Directory to store PGO profile data (default: build/pgo-data)",
    )
    parser.add_argument(
        "--train-script",
        type=Path,
        default=ROOT / "benchmarks" / "bench.py",
        help="Python script to run for training (default: benchmarks/bench.py)",
    )
    args = parser.parse_args()

    pgo_dir = args.pgo_dir.resolve()
    pgo_dir.mkdir(parents=True, exist_ok=True)

    clean_build_dirs()
    phase_generate(pgo_dir)
    phase_train(args.train_script)
    phase_use(pgo_dir)

    print("\n=== PGO build complete ===")
    print(f"Profile data: {pgo_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

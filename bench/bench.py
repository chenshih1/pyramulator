"""Benchmark memory latency and throughput across DRAM configurations."""

import logging

from pyramulator import Config, MemorySystem, RequestType

logger = logging.getLogger(__name__)


CONFIGS = {
    "DDR3_1600": dict(standard="DDR3", speed="DDR3_1600K", org="DDR3_2Gb_x8"),
    "DDR4_2400": dict(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8"),
    "DDR4_3200": dict(standard="DDR4", speed="DDR4_3200AA", org="DDR4_8Gb_x8"),
    "LPDDR3_1600": dict(standard="LPDDR3", speed="LPDDR3_1600", org="LPDDR3_8Gb_x32"),
    "LPDDR4_2400": dict(standard="LPDDR4", speed="LPDDR4_2400", org="LPDDR4_8Gb_x16"),
}

NUM_REQUESTS = 256
CACHELINE = 64


def make_config(params, channels=1, ranks=1):
    return Config(channels=channels, ranks=ranks, **params)


def bench_latency(params, channels=1, ranks=1):
    """Measure average read latency in DRAM clock cycles."""
    cfg = make_config(params, channels, ranks)
    latencies = []

    with MemorySystem(cfg, cacheline=CACHELINE) as mem:
        for i in range(NUM_REQUESTS):
            addr = i * CACHELINE
            while not mem.send_read(addr, callback=lambda info: latencies.append(
                    info.depart - info.arrive)):
                mem.tick()

        mem.run_until_idle()
        tck = mem.tck

    if not latencies:
        return None

    avg = sum(latencies) / len(latencies)
    return {"avg": avg, "min": min(latencies), "max": max(latencies),
            "tck": tck, "completed": len(latencies)}


def bench_throughput(params, channels=1, ranks=1):
    """Measure sustained read throughput (GB/s) with a full queue."""
    cfg = make_config(params, channels, ranks)
    completed = [0]
    first_clk = [None]
    last_clk = [0]

    def on_done(info):
        completed[0] += 1
        if first_clk[0] is None:
            first_clk[0] = info.depart
        last_clk[0] = info.depart

    with MemorySystem(cfg, cacheline=CACHELINE) as mem:
        issued = 0
        addr = 0
        while completed[0] < NUM_REQUESTS and mem.clk < 200_000:
            while issued - completed[0] < 32 and issued < NUM_REQUESTS:
                if mem.send_read(addr, callback=on_done):
                    issued += 1
                    addr += CACHELINE
                else:
                    break
            mem.tick()
        tck = mem.tck

    if first_clk[0] is None or completed[0] < 2:
        return None

    active_cycles = last_clk[0] - first_clk[0]
    if active_cycles == 0:
        return None

    bytes_transferred = completed[0] * CACHELINE
    seconds = active_cycles * tck * 1e-9
    bandwidth_gbs = bytes_transferred / seconds / 1e9

    return {"bandwidth_gbs": bandwidth_gbs, "completed": completed[0],
            "cycles": active_cycles, "tck": tck}


def bench_random(params, channels=1, ranks=1, seed=42):
    """Measure latency with random access pattern (row buffer misses)."""
    import random
    rng = random.Random(seed)
    max_addr = 1 << 26

    cfg = make_config(params, channels, ranks)
    latencies = []
    addrs = [rng.randrange(0, max_addr, CACHELINE) for _ in range(NUM_REQUESTS)]

    with MemorySystem(cfg, cacheline=CACHELINE) as mem:
        for addr in addrs:
            while not mem.send_read(addr, callback=lambda info: latencies.append(
                    info.depart - info.arrive)):
                mem.tick()

        mem.run_until_idle()
        tck = mem.tck

    if not latencies:
        return None

    avg = sum(latencies) / len(latencies)
    return {"avg": avg, "min": min(latencies), "max": max(latencies),
            "tck": tck, "completed": len(latencies)}


def run_all():
    logger.info("=" * 78)
    logger.info("%s", f"{'Pyramulator Benchmark':^78}")
    logger.info("%s", f"{'requests=' + str(NUM_REQUESTS) + '  cacheline=' + str(CACHELINE) + 'B':^78}")
    logger.info("=" * 78)

    logger.info("")
    logger.info("%s", f"{'--- Read Latency (sequential, closed-page) ---':^78}")
    logger.info("%s %s %s %s %s %s",
                f"{'Config':<16}", f"{'Avg(cyc)':>9}", f"{'Min':>6}",
                f"{'Max':>6}", f"{'Avg(ns)':>9}", f"{'tck(ns)':>8}")
    logger.info("-" * 78)
    for name, params in CONFIGS.items():
        result = bench_latency(params)
        if result:
            logger.info("%s %s", f"{name:<16}",
                        f"{result['avg']:>9.1f} {result['min']:>6} "
                        f"{result['max']:>6} {result['avg'] * result['tck']:>9.2f} "
                        f"{result['tck']:>8.3f}")
        else:
            logger.warning("%s %s", f"{name:<16}", f"{'FAILED':>9}")

    logger.info("")
    logger.info("%s", f"{'--- Read Latency (random access) ---':^78}")
    logger.info("%s %s %s %s %s %s",
                f"{'Config':<16}", f"{'Avg(cyc)':>9}", f"{'Min':>6}",
                f"{'Max':>6}", f"{'Avg(ns)':>9}", f"{'tck(ns)':>8}")
    logger.info("-" * 78)
    for name, params in CONFIGS.items():
        result = bench_random(params)
        if result:
            logger.info("%s %s", f"{name:<16}",
                        f"{result['avg']:>9.1f} {result['min']:>6} "
                        f"{result['max']:>6} {result['avg'] * result['tck']:>9.2f} "
                        f"{result['tck']:>8.3f}")
        else:
            logger.warning("%s %s", f"{name:<16}", f"{'FAILED':>9}")

    logger.info("")
    logger.info("%s", f"{'--- Sustained Read Throughput (queue depth=32) ---':^78}")
    logger.info("%s %s %s %s %s",
                f"{'Config':<16}", f"{'BW(GB/s)':>10}", f"{'Completed':>10}",
                f"{'Cycles':>10}", f"{'tck(ns)':>8}")
    logger.info("-" * 78)
    for name, params in CONFIGS.items():
        result = bench_throughput(params)
        if result:
            logger.info("%s %s", f"{name:<16}",
                        f"{result['bandwidth_gbs']:>10.2f} "
                        f"{result['completed']:>10} {result['cycles']:>10} "
                        f"{result['tck']:>8.3f}")
        else:
            logger.warning("%s %s", f"{name:<16}", f"{'FAILED':>10}")

    logger.info("")
    logger.info("%s", f"{'--- Throughput Scaling (DDR4_2400, channels=1,2,4) ---':^78}")
    logger.info("%s %s %s", f"{'Channels':<16}", f"{'BW(GB/s)':>10}", f"{'Speedup':>10}")
    logger.info("-" * 78)
    base_bw = None
    for num_channels in [1, 2, 4]:
        result = bench_throughput(CONFIGS["DDR4_2400"], channels=num_channels)
        if result:
            if base_bw is None:
                base_bw = result["bandwidth_gbs"]
            speedup = result["bandwidth_gbs"] / base_bw
            logger.info("%s %s", f"{num_channels:<16}",
                        f"{result['bandwidth_gbs']:>10.2f} {speedup:>10.2f}x")

    logger.info("=" * 78)
    logger.info("Done.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_all()

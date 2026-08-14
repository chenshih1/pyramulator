"""Benchmark memory latency and throughput across DRAM configurations."""

import logging

from pyramulator import Config, benchmark_bandwidth, benchmark_latency

logger = logging.getLogger(__name__)


CONFIGS = {
    "DDR3_1600": {"standard": "DDR3", "speed": "DDR3_1600K", "org": "DDR3_2Gb_x8"},
    "DDR4_2400": {"standard": "DDR4", "speed": "DDR4_2400R", "org": "DDR4_4Gb_x8"},
    "DDR4_3200": {"standard": "DDR4", "speed": "DDR4_3200AA", "org": "DDR4_8Gb_x8"},
    "LPDDR3_1600": {"standard": "LPDDR3", "speed": "LPDDR3_1600",
                     "org": "LPDDR3_8Gb_x32"},
    "LPDDR4_2400": {"standard": "LPDDR4", "speed": "LPDDR4_2400",
                     "org": "LPDDR4_8Gb_x16"},
}

NUM_REQUESTS = 256
CACHELINE = 64


def make_config(params, channels=1, ranks=1):
    return Config(channels=channels, ranks=ranks, **params)


def run_all():
    logger.info("=" * 78)
    logger.info("%s", f"{'Pyramulator Benchmark':^78}")
    header = f"requests={NUM_REQUESTS}  cacheline={CACHELINE}B"
    logger.info("%s", f"{header:^78}")
    logger.info("=" * 78)

    logger.info("")
    logger.info("%s", f"{'--- Read Latency (sequential, closed-page) ---':^78}")
    logger.info("%s %s %s %s %s %s",
                f"{'Config':<16}", f"{'Avg(cyc)':>9}", f"{'Min':>6}",
                f"{'Max':>6}", f"{'Avg(ns)':>9}", f"{'tck(ns)':>8}")
    logger.info("-" * 78)
    for name, params in CONFIGS.items():
        result = benchmark_latency(make_config(params), NUM_REQUESTS)
        if result and result["completed"]:
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
        result = benchmark_latency(make_config(params), NUM_REQUESTS,
                                   mode="random", seed=42)
        if result and result["completed"]:
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
        result = benchmark_bandwidth(make_config(params), NUM_REQUESTS)
        if result and result["completed"]:
            logger.info("%s %s", f"{name:<16}",
                        f"{result['bandwidth_gbs']:>10.2f} "
                        f"{result['completed']:>10} {result['cycles']:>10} "
                        f"{result['tck']:>8.3f}")
        else:
            logger.warning("%s %s", f"{name:<16}", f"{'FAILED':>10}")

    logger.info("")
    logger.info("%s", f"{'--- Throughput Scaling (DDR4_2400, channels=1,2,4) ---':^78}")
    logger.info("%s %s %s", f"{'Channels':<16}",
                f"{'BW(GB/s)':>10}", f"{'Speedup':>10}")
    logger.info("-" * 78)
    base_bw = None
    for num_channels in [1, 2, 4]:
        result = benchmark_bandwidth(make_config(CONFIGS["DDR4_2400"],
                                                 channels=num_channels),
                                     NUM_REQUESTS)
        if result and result["completed"]:
            if base_bw is None:
                base_bw = result["bandwidth_gbs"]
            speedup = result["bandwidth_gbs"] / base_bw
            logger.info("%s %s", f"{num_channels:<16}",
                        f"{result['bandwidth_gbs']:>10.2f} {speedup:>10.2f}x")
        else:
            logger.warning("%s %s", f"{num_channels:<16}", f"{'FAILED':>10}")

    logger.info("=" * 78)
    logger.info("Done.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_all()

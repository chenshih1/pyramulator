"""Metrics, workload, and benchmark helper tests."""

import pytest

from pyramulator import (
    MemorySystem,
    addresses,
    avg_read_latency,
    benchmark_bandwidth,
    benchmark_latency,
    read_write_mix,
    row_hit_rate,
)


class TestMetrics:
    def test_summary(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        mem.reset_stats()
        mem.send_reads_range(0, 32, 64)
        mem.run_until_idle()
        m = mem.metrics()
        assert m["read_requests"] == 32
        assert m["avg_read_latency_cycles"] > 0
        assert m["bandwidth_gbs"] > 0
        assert 0.0 <= m["row_hit_rate"] <= 1.0

    def test_metrics_no_finish_needed(self, ddr4_config):
        """avg latency derived from raw sums, not the finish()-only field."""
        mem = MemorySystem(ddr4_config)
        mem.send_read(0x1000)
        mem.run_until_idle()
        stats = mem.get_stats()
        assert avg_read_latency(stats) > 0
        assert stats["read_latency_avg_0"] == 0  # ramulator leaves this 0

    def test_row_hit_rate_sequential(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        mem.send_reads_range(0, 64, 64)
        mem.run_until_idle()
        assert row_hit_rate(mem.get_stats()) > 0.5


class TestWorkload:
    def test_sequential(self):
        addrs = addresses("sequential", 4, cacheline=64)
        assert addrs == [0, 64, 128, 192]

    def test_strided(self):
        addrs = addresses("strided", 3, cacheline=64, start=1024, stride=256)
        assert addrs == [1024, 1280, 1536]

    def test_random_deterministic(self):
        a1 = addresses("random", 100, cacheline=64, seed=42)
        a2 = addresses("random", 100, cacheline=64, seed=42)
        assert a1 == a2
        assert all(a % 64 == 0 for a in a1)

    def test_unknown_mode(self):
        with pytest.raises(ValueError, match="unknown address mode"):
            addresses("bogus", 4)

    def test_read_write_mix(self):
        addrs = addresses("sequential", 100)
        reads, writes = read_write_mix(addrs, write_fraction=0.25, seed=1)
        assert len(reads) + len(writes) == 100
        assert 0 < len(writes) < 100


class TestBenchmarkHelpers:
    def test_benchmark_latency(self, ddr4_config):
        result = benchmark_latency(ddr4_config, num_requests=64)
        assert result["completed"] == 64
        assert 10 < result["avg"] < 500

    def test_benchmark_bandwidth(self, ddr4_config):
        result = benchmark_bandwidth(ddr4_config, num_requests=64)
        assert result["completed"] == 64
        assert result["bandwidth_gbs"] > 1.0

    def test_benchmark_all(self, ddr4_config):
        from pyramulator import benchmark_all

        result = benchmark_all(ddr4_config, num_requests=64)
        assert result["latency"]["completed"] == 64
        assert result["bandwidth"]["completed"] == 64

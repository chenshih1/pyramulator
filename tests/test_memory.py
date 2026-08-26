"""MemorySystem core simulation tests."""

from __future__ import annotations

import pytest

from pyramulator import Config, RequestType
from pyramulator._engine import MemorySystem
from tests.conftest import DDR4_2400R_CFG


class TestMemorySystem:
    def test_create(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        assert mem.tck > 0
        assert mem.clk == 0
        assert mem.pending == 0

    def test_create_from_dict(self) -> None:
        mem = MemorySystem(
            {
                "standard": "DDR4",
                "channels": "1",
                "ranks": "1",
                "speed": "DDR4_2400R",
                "org": "DDR4_4Gb_x8",
            }
        )
        assert mem.tck > 0

    def test_tick(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.tick()
        assert mem.clk == 1

    def test_run(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.run(100)
        assert mem.clk == 100

    def test_read_callback(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        results = []
        mem.send_read(0x1000, callback=lambda info: results.append(info))
        mem.run(1000)
        assert len(results) == 1
        assert results[0].addr == 0x1000
        assert results[0].type == RequestType.READ
        assert results[0].latency > 0

    def test_write_callback(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        results = []
        for i in range(32):
            mem.send_write(i * 64, callback=lambda info: results.append(info))
        mem.run(10000)
        assert len(results) > 0
        assert all(info.type == RequestType.WRITE for info in results)

    def test_run_until_idle(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        results = []
        for i in range(8):
            mem.send_read(i * 64, callback=lambda info: results.append(info))
        mem.run_until_idle()
        assert len(results) == 8
        assert mem.pending == 0

    def test_backpressure(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        results = [mem.send_read(i * 64) for i in range(64)]
        assert all(results[:32])

    def test_send_reads_batch(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        results = []
        mem.send_reads([0x0, 0x40, 0x80], callback=lambda info: results.append(info))
        mem.run_until_idle()
        assert len(results) == 3

    def test_send_writes_batch(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        results = []
        mem.send_writes(
            [0x0, 0x40, 0x80, 0xC0] * 8, callback=lambda info: results.append(info)
        )
        mem.run(10000)
        assert len(results) > 0

    def test_write_queue_watermark(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.set_write_queue_watermark(high=0.9, low=0.1)
        mem.send_write(0x0)
        mem.run(100)

    def test_repr(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        r = repr(mem)
        assert "MemorySystem" in r
        assert "tck=" in r

    def test_multi_core(self) -> None:
        cfg = Config(channels=1, **DDR4_2400R_CFG)
        mem = MemorySystem(cfg, num_cores=4)
        results = []
        for core in range(4):
            mem.send_read(
                core * 0x1000, core_id=core, callback=lambda info: results.append(info)
            )
        mem.run_until_idle()
        assert len(results) == 4


class TestMultiStandard:
    @pytest.mark.parametrize(
        "standard,speed,org",
        [
            ("DDR3", "DDR3_1600K", "DDR3_2Gb_x8"),
            ("DDR4", "DDR4_2400R", "DDR4_4Gb_x8"),
            ("LPDDR3", "LPDDR3_1600", "LPDDR3_8Gb_x32"),
            ("LPDDR4", "LPDDR4_2400", "LPDDR4_8Gb_x16"),
        ],
    )
    def test_standard_read_completes(self, standard, speed, org) -> None:
        cfg = Config(standard=standard, speed=speed, org=org)
        mem = MemorySystem(cfg)
        results = []
        mem.send_read(0x1000, callback=lambda info: results.append(info))
        mem.run_until_idle()
        assert len(results) == 1
        assert results[0].latency > 0

    def test_multichannel(self) -> None:
        cfg = Config(channels=2, **DDR4_2400R_CFG)
        mem = MemorySystem(cfg)
        results = []
        for i in range(16):
            mem.send_read(i * 64, callback=lambda info: results.append(info))
        mem.run_until_idle()
        assert len(results) == 16


class TestBenchmark:
    def test_sequential_latency(self, ddr4_config) -> None:
        """Sequential reads should have bounded, positive latency."""
        mem = MemorySystem(ddr4_config)
        latencies = []
        num_requests = 64

        for i in range(num_requests):
            addr = i * 64
            while not mem.send_read(
                addr, callback=lambda info: latencies.append(info.latency)
            ):
                mem.tick()

        mem.run_until_idle()
        assert len(latencies) == num_requests
        assert all(lat > 0 for lat in latencies)
        avg = sum(latencies) / len(latencies)
        assert 10 < avg < 500

    def test_random_latency_higher_than_sequential(self) -> None:
        """Random access should have higher avg latency than sequential."""
        import random

        rng = random.Random(42)
        cfg = Config(**DDR4_2400R_CFG)

        seq_lats = []
        mem = MemorySystem(cfg)
        for i in range(64):
            while not mem.send_read(
                i * 64, callback=lambda info: seq_lats.append(info.latency)
            ):
                mem.tick()
        mem.run_until_idle()

        rand_lats = []
        addrs = [rng.randrange(0, 1 << 24, 64) for _ in range(64)]
        mem = MemorySystem(cfg)
        for addr in addrs:
            while not mem.send_read(
                addr, callback=lambda info: rand_lats.append(info.latency)
            ):
                mem.tick()
        mem.run_until_idle()

        seq_avg = sum(seq_lats) / len(seq_lats)
        rand_avg = sum(rand_lats) / len(rand_lats)
        assert rand_avg >= seq_avg

    def test_throughput_positive(self, ddr4_config) -> None:
        """Sustained reads should achieve measurable bandwidth."""
        mem = MemorySystem(ddr4_config)
        completed = [0]
        first_clk = [None]
        last_clk = [0]
        num_requests = 128

        def on_done(info):
            completed[0] += 1
            if first_clk[0] is None:
                first_clk[0] = info.depart_cycle
            last_clk[0] = info.depart_cycle

        issued = 0
        addr = 0
        while completed[0] < num_requests and mem.clk < 100_000:
            while issued - completed[0] < 32 and issued < num_requests:
                if mem.send_read(addr, callback=on_done):
                    issued += 1
                    addr += 64
                else:
                    break
            mem.tick()

        assert completed[0] == num_requests
        active = last_clk[0] - first_clk[0]
        assert active > 0
        bandwidth = completed[0] * 64 / (active * mem.tck * 1e-9) / 1e9
        assert bandwidth > 1.0

    def test_multichannel_throughput_scales(self) -> None:
        """2-channel should achieve higher throughput than 1-channel."""

        def measure_bw(channels):
            cfg = Config(
                standard="DDR4",
                channels=channels,
                speed="DDR4_2400R",
                org="DDR4_4Gb_x8",
            )
            mem = MemorySystem(cfg)
            completed = [0]
            first = [None]
            last = [0]

            def on_done(info):
                completed[0] += 1
                if first[0] is None:
                    first[0] = info.depart_cycle
                last[0] = info.depart_cycle

            issued = 0
            addr = 0
            while completed[0] < 128 and mem.clk < 100_000:
                while issued - completed[0] < 32 and issued < 128:
                    if mem.send_read(addr, callback=on_done):
                        issued += 1
                        addr += 64
                    else:
                        break
                mem.tick()

            active = last[0] - first[0]
            return completed[0] * 64 / (active * mem.tck * 1e-9) / 1e9

        bw1 = measure_bw(1)
        bw2 = measure_bw(2)
        assert bw2 > bw1 * 1.5


class TestStats:
    def test_get_stats_dict(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.reset_stats()
        mem.send_reads_range(0, 16, 64)
        mem.run_until_idle()
        stats = mem.get_stats()
        assert stats["read_requests"] == 16
        assert stats["read_latency_sum_0"] > 0
        assert stats["dram_cycles"] > 0

    def test_reset_stats(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.send_read(0x1000)
        mem.run_until_idle()
        mem.reset_stats()
        stats = mem.get_stats()
        assert stats["read_requests"] == 0
        assert stats["dram_cycles"] == 0

    def test_instances_isolated(self, ddr4_config) -> None:
        m1 = MemorySystem(ddr4_config)
        m2 = MemorySystem(ddr4_config)
        m1.send_read(0x1000)
        m1.run_until_idle()
        m2.send_read(0x1000)
        m2.run_until_idle()
        m2.reset_stats()
        assert m1.get_stats()["read_requests"] == 1
        assert m2.get_stats()["read_requests"] == 0


class TestRangeSend:
    def test_reads_range(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        completed = []
        accepted = mem.send_reads_range(
            0, 32, 64, callback=lambda i: completed.append(i)
        )
        assert all(accepted)
        mem.flush()
        assert len(completed) == 32
        assert completed[0].addr == 0
        assert completed[31].addr == 31 * 64

    def test_reads_range_default_stride(self, ddr4_config) -> None:
        """Stride defaults to the cacheline."""
        cfg = Config(standard="LPDDR4", speed="LPDDR4_2400", org="LPDDR4_8Gb_x16")
        mem = MemorySystem(cfg, cacheline=32)
        completed = []
        mem.send_reads_range(0, 8, callback=lambda i: completed.append(i))
        mem.flush()
        assert len(completed) == 8
        assert completed[1].addr == 32

    def test_writes_range(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        completed = []
        accepted = mem.send_writes_range(
            0, 8, 64, callback=lambda i: completed.append(i)
        )
        assert all(accepted)
        assert len(completed) == 8
        assert all(i.type == RequestType.WRITE for i in completed)

    def test_core_id_in_request_info(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config, num_cores=4)
        infos = []
        mem.send_read(0x1000, core_id=2, callback=lambda i: infos.append(i))
        mem.send_read(0x2000, core_id=3, callback=lambda i: infos.append(i))
        mem.run_until_idle()
        assert {i.core_id for i in infos} == {2, 3}
        assert infos[0].core_id == 2

    def test_flush_drains_writes(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.send_writes([i * 64 for i in range(32)])
        mem.flush()
        assert mem.pending == 0

    def test_callback_exception_keeps_dispatching(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        seen = []

        def bad(info):
            raise RuntimeError("boom")

        def good(info):
            seen.append(info.addr)

        mem.send_read(0x0, callback=bad)
        mem.send_read(0x40, callback=good)
        with pytest.raises(RuntimeError, match="boom"):
            mem.run_until_idle()
        assert seen == [0x40]


class TestCachelineValidation:
    def test_not_power_of_two(self, ddr4_config) -> None:
        with pytest.raises(ValueError, match="power of two"):
            MemorySystem(ddr4_config, cacheline=100)

    def test_too_small_for_standard(self) -> None:
        cfg = Config(**DDR4_2400R_CFG)
        with pytest.raises(ValueError, match="multiple of the DDR4"):
            MemorySystem(cfg, cacheline=32)

    def test_lpddr4_small_cacheline_ok(self) -> None:
        cfg = Config(standard="LPDDR4", speed="LPDDR4_2400", org="LPDDR4_8Gb_x16")
        mem = MemorySystem(cfg, cacheline=32)
        assert mem.tck > 0


class TestDrive:
    def test_drive_completes_all(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        done = []
        issued = mem.drive(
            [i * 64 for i in range(64)], callback=lambda i: done.append(i)
        )
        assert issued == 64
        assert len(done) == 64
        assert mem.pending == 0

    def test_drive_range_matches_manual_loop(self, ddr4_config) -> None:
        def run_manual():
            m = MemorySystem(ddr4_config)
            done = []
            issued = 0
            addr = 0
            while len(done) < 128 and m.clk < 1_000_000:
                while issued - len(done) < 32 and issued < 128:
                    if m.send_read(addr, callback=lambda i: done.append(i)):
                        issued += 1
                        addr += 64
                    else:
                        break
                m.run(200)
            return m, len(done)

        def run_drive():
            m = MemorySystem(ddr4_config)
            done = []
            issued = m.drive_range(
                0, 128, 64, batch=200, callback=lambda i: done.append(i)
            )
            return m, issued, len(done)

        m1, done1 = run_manual()
        m2, issued2, done2 = run_drive()
        assert issued2 == 128
        assert done2 == 128
        assert done1 == 128
        # drive drains exactly; no more cycles than the manual loop (batch granularity)
        assert m2.clk <= m1.clk

    def test_drive_no_callback(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        issued = mem.drive_range(0, 64, 64, batch=200)
        assert issued == 64
        assert mem.pending == 0
        assert mem.get_stats()["read_requests"] == 64

    def test_drive_max_cycles(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        issued = mem.drive_range(0, 100_000, 64, max_cycles=100)
        assert issued < 100_000  # 超时截断
        assert mem.clk <= 100

    def test_time_advancing_returns_cycles(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        assert mem.tick() == 1
        assert mem.run(10) == 10
        mem.send_read(0x1000)
        assert mem.run_until_idle() >= 0
        assert mem.flush() >= 0

    def test_get_stats(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.send_read(0x1000)
        mem.run_until_idle()
        stats = mem.get_stats()
        assert isinstance(stats, dict)
        assert stats["read_requests"] == 1.0

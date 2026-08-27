"""Extreme/extreme simulation tests: push MemorySystem and DES limits."""

from __future__ import annotations

import pytest

from pyramulator import Config
from pyramulator._engine import MemorySystem, RequestType


class TestExtremeCycles:
    """Very long simulation runs."""

    def test_run_million_cycles_idle(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        result = mem.run(1_000_000)
        assert result == 1_000_000
        assert mem.clk == 1_000_000

    def test_run_until_idle_very_long(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.send_read(0x1000)
        cycles = mem.run_until_idle(max_cycles=10_000_000)
        assert cycles > 0
        assert cycles <= 10_000_000

    def test_tick_extended(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        for _ in range(500):
            assert mem.tick() == 1
        assert mem.clk == 500


class TestExtremeBatch:
    """Very large request batches."""

    def test_batch_read_1000_requests(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        completed = []
        addrs = [i * 64 for i in range(1000)]
        accepted = mem.send_reads(
            addrs,
            callback=lambda info: completed.append(info),
        )
        # Queue depth limits accept count; process what was accepted
        assert sum(1 for ok in accepted if ok) > 0
        mem.run_until_idle()
        assert len(completed) == sum(1 for ok in accepted if ok)

    def test_batch_write_500_requests(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        completed = []
        addrs = [i * 64 for i in range(500)]
        accepted = mem.send_writes(
            addrs,
            callback=lambda info: completed.append(info),
        )
        assert sum(1 for ok in accepted if ok) > 0
        mem.run_until_idle()
        assert len(completed) == sum(1 for ok in accepted if ok)

    def test_range_very_large(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        issued = mem.send_reads_range(0, 2000, 64)
        assert len(issued) == 2000


class TestHBMExtreme:
    """HBM stress: largest org and multi-channel configurations."""

    @pytest.fixture
    def hbm_max_config(self) -> Config:
        return Config(standard="HBM", speed="HBM_1Gbps", org="HBM_4Gb")

    def test_hbm_max_config_create(self, hbm_max_config) -> None:
        mem = MemorySystem(hbm_max_config)
        assert mem.tck > 0
        assert mem.capacity > 0

    def test_hbm_max_batch_reads(self, hbm_max_config) -> None:
        mem = MemorySystem(hbm_max_config)
        completed = []
        addrs = [i * 128 for i in range(256)]
        accepted = mem.send_reads(
            addrs,
            callback=lambda info: completed.append(info),
        )
        assert sum(1 for ok in accepted if ok) > 0
        mem.run_until_idle()
        assert len(completed) == sum(1 for ok in accepted if ok)

    def test_hbm_max_channel(self, hbm_max_config) -> None:
        mem = MemorySystem(hbm_max_config, cacheline=128)
        completed = []
        mem.send_read(0x1000, callback=lambda i: completed.append(i))
        mem.run_until_idle()
        assert len(completed) == 1
        assert completed[0].type == RequestType.READ


class TestBackpressureExtreme:
    """Push queue-full conditions repeatedly."""

    def test_repeated_send_until_full(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        total_issued = 0
        for _ in range(100):
            accepted = False
            while mem.send_read(0x1000 + total_issued * 64):
                total_issued += 1
                accepted = True
                if total_issued >= 500:  # extreme/extreme target
                    break
            mem.tick()
            if accepted:
                mem.run_until_idle()
        assert total_issued > 0  # at least some progress under extreme/extreme pressure

    def test_write_saturation_then_flush(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        for _ in range(64):
            mem.send_write(0x2000)
        cycles = mem.flush(max_cycles=1_000_000)
        assert cycles >= 0
        assert cycles < 1_000_000


class TestExtremeMemorySpace:
    """Very large address spaces (does not allocate full space)."""

    def test_very_large_address_read(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        completed = []
        mem.send_read(1 << 24, callback=lambda info: completed.append(info))
        mem.run_until_idle()
        assert len(completed) == 1

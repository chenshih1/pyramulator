"""Edge cases and boundary-condition tests for the MemorySystem engine."""

from __future__ import annotations

import pytest

from pyramulator import Config
from pyramulator._engine import MemorySystem


class TestMemorySystemEdgeCases:
    """Boundary and corner cases that should not crash or corrupt state."""

    def test_empty_batch_is_noop(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        assert mem.send_reads([]) == []
        assert mem.send_writes([]) == []
        mem.run_until_idle()
        assert mem.clk == 0
        assert mem.pending == 0

    def test_zero_cycles_run(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        assert mem.run(0) == 0
        assert mem.clk == 0

    def test_address_zero(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        completed = []
        mem.send_read(0, callback=lambda info: completed.append(info))
        mem.run_until_idle()
        assert len(completed) == 1
        assert completed[0].addr == 0

    def test_core_id_max_valid(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config, num_cores=4)
        completed = []
        mem.send_read(0x1000, core_id=3, callback=lambda info: completed.append(info))
        mem.run_until_idle()
        assert len(completed) == 1
        assert completed[0].core_id == 3

    def test_core_id_out_of_range(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config, num_cores=2)
        with pytest.raises(ValueError):
            mem.send_read(0x1000, core_id=2)

    def test_send_after_flush(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.send_write(0x1000)
        mem.flush()
        completed = []
        mem.send_read(0x2000, callback=lambda info: completed.append(info))
        mem.run_until_idle()
        assert len(completed) == 1

    def test_interleaved_read_write(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        reads, writes = [], []
        for i in range(16):
            mem.send_read(i * 64, callback=lambda info: reads.append(info))
            mem.send_write(i * 64 + 0x10000, callback=lambda info: writes.append(info))
        mem.flush()
        assert len(reads) == 16
        assert len(writes) == 16  # writes complete on acceptance

    def test_reset_stats_mid_run(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.send_read(0x1000)
        mem.run_until_idle()
        mem.reset_stats()
        mem.send_read(0x2000)
        mem.run_until_idle()
        stats = mem.get_stats()
        assert stats["read_requests"] == 1.0

    def test_send_range_count_zero(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        assert mem.send_reads_range(0, 0, 64) == []
        mem.run_until_idle()
        assert mem.clk == 0

    def test_run_until_idle_when_already_idle(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        cycles = mem.run_until_idle()
        assert cycles == 0

    def test_multiple_flushes_idempotent(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        mem.send_read(0x1000)
        c1 = mem.flush()
        c2 = mem.flush()
        assert c1 >= 0
        assert c2 == 0

    def test_max_int_address_does_not_crash(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        # Address near max int; DRAM wraps internally, should not overflow Python.
        mem.send_read(2**63 - 64)
        mem.run_until_idle()


class TestConfigEdgeCases:
    """Configuration boundary cases."""

    def test_cacheline_exact_minimum(self) -> None:
        # DDR4 minimum channel unit is 64 bytes
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")
        mem = MemorySystem(cfg, cacheline=64)
        assert mem._cacheline == 64

    def test_channels_minimum_one(self, ddr4_config) -> None:
        mem = MemorySystem(ddr4_config)
        assert mem._config.channels == 1

    def test_validate_rejects_non_power_of_two_channels(self) -> None:
        cfg = Config(
            standard="DDR4",
            speed="DDR4_2400R",
            org="DDR4_4Gb_x8",
            channels=3,
        )
        with pytest.raises(ValueError):
            cfg.validate()

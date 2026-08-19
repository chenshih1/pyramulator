"""Configuration-related tests."""

from __future__ import annotations

import pytest

from pyramulator import (
    Config,
    RequestInfo,
    RequestType,
    estimate_capacity,
    supported_orgs,
    supported_speeds,
    supported_standards,
    theoretical_bandwidth,
)
from pyramulator.configs import show


class TestConfig:
    def test_kwargs(self, ddr4_config):
        assert ddr4_config["standard"] == "DDR4"
        assert ddr4_config["speed"] == "DDR4_2400R"
        assert "channels" in ddr4_config

    def test_defaults_channels_ranks(self):
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")
        assert cfg["channels"] == "1"
        assert cfg["ranks"] == "1"

    def test_explicit_channels(self):
        cfg = Config(
            standard="DDR4", channels=4, ranks=2, speed="DDR4_2400R", org="DDR4_4Gb_x8"
        )
        assert cfg["channels"] == "4"
        assert cfg["ranks"] == "2"

    def test_from_file(self, ddr4_config_file):
        cfg = Config.from_file(str(ddr4_config_file))
        assert cfg["standard"] == "DDR4"
        assert cfg["channels"] == "1"

    def test_from_file_with_overrides(self, ddr4_config_file):
        cfg = Config.from_file(str(ddr4_config_file), channels=4, ranks=2)
        assert cfg["channels"] == "4"
        assert cfg["ranks"] == "2"
        assert cfg["standard"] == "DDR4"

    def test_validate_valid(self, ddr4_config):
        assert ddr4_config.validate() is None

    def test_validate_bad_standard(self):
        cfg = Config(standard="DDR5", speed="x", org="y")
        with pytest.raises(ValueError, match="unsupported standard"):
            cfg.validate()

    def test_validate_bad_speed(self):
        cfg = Config(standard="DDR4", speed="DDR4_9999X", org="DDR4_4Gb_x8")
        with pytest.raises(ValueError, match="invalid speed"):
            cfg.validate()

    def test_validate_bad_org(self):
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_999Gb_x8")
        with pytest.raises(ValueError, match="invalid org"):
            cfg.validate()

    def test_validate_bad_channels(self):
        cfg = Config(standard="DDR4", channels=3, speed="DDR4_2400R", org="DDR4_4Gb_x8")
        with pytest.raises(ValueError, match="power of 2"):
            cfg.validate()

    def test_repr(self, ddr4_config):
        r = repr(ddr4_config)
        assert "DDR4" in r
        assert "DDR4_2400R" in r


class TestConfigsModule:
    def test_supported_standards(self):
        stds = supported_standards()
        assert "DDR4" in stds
        assert "HBM" in stds
        assert "SALP-1" in stds
        assert len(stds) == 11

    def test_supported_speeds(self):
        speeds = supported_speeds("DDR4")
        assert "DDR4_2400R" in speeds
        assert len(speeds) > 0

    def test_supported_orgs(self):
        orgs = supported_orgs("DDR4")
        assert "DDR4_4Gb_x8" in orgs

    def test_salp_variants_share_table(self):
        assert supported_speeds("SALP-1") == supported_speeds("SALP-2")
        assert supported_orgs("SALP-1") == supported_orgs("SALP-MASA")

    def test_show(self, capsys):
        show("DDR4")
        captured = capsys.readouterr()
        assert "DDR4_2400R" in captured.out


class TestRequestInfo:
    def test_latency_property(self):
        info = RequestInfo(addr=0x1000, type=RequestType.READ, arrive=10, depart=50)
        assert info.latency == 40

    def test_fields(self):
        info = RequestInfo(addr=0x2000, type=RequestType.WRITE, arrive=5, depart=15)
        assert info.addr == 0x2000
        assert info.type == RequestType.WRITE

    def test_default_core_id(self):
        info = RequestInfo(addr=0, type=RequestType.READ, arrive=0, depart=1)
        assert info.core_id == 0


class TestTheoreticalBandwidth:
    def test_ddr4_2400_1ch(self):
        cfg = Config(standard="DDR4", channels=1, speed="DDR4_2400R", org="DDR4_4Gb_x8")
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(19.2, rel=0.01)

    def test_ddr4_2400_2ch(self):
        cfg = Config(standard="DDR4", channels=2, speed="DDR4_2400R", org="DDR4_4Gb_x8")
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(38.4, rel=0.01)

    def test_ddr3_1600_1ch(self):
        cfg = Config(standard="DDR3", channels=1, speed="DDR3_1600K", org="DDR3_2Gb_x8")
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(12.8, rel=0.01)

    def test_gddr5_qdr(self):
        cfg = Config(
            standard="GDDR5", channels=1, speed="GDDR5_6000", org="GDDR5_8Gb_x32"
        )
        bw = theoretical_bandwidth(cfg)
        # GDDR5-6000: 6000 MT/s * 4 bytes (32-bit) = 24 GB/s per channel
        assert bw == pytest.approx(24.0, rel=0.01)

    def test_scales_with_channels(self):
        cfg1 = Config(
            standard="DDR4", channels=1, speed="DDR4_2400R", org="DDR4_4Gb_x8"
        )
        cfg4 = Config(
            standard="DDR4", channels=4, speed="DDR4_2400R", org="DDR4_4Gb_x8"
        )
        assert theoretical_bandwidth(cfg4) == pytest.approx(
            4 * theoretical_bandwidth(cfg1), rel=0.01
        )

    def test_accepts_dict(self):
        bw = theoretical_bandwidth(
            {
                "standard": "DDR4",
                "channels": "1",
                "speed": "DDR4_2400R",
                "org": "DDR4_4Gb_x8",
            }
        )
        assert bw > 0


class TestCapacity:
    def test_ddr4_4gb_x8(self, ddr4_config):
        from pyramulator import MemorySystem

        assert MemorySystem(ddr4_config).capacity == 4 * 2**30

    def test_ddr4_scales_with_channels(self):
        from pyramulator import MemorySystem

        cfg = Config(standard="DDR4", channels=2, speed="DDR4_2400R", org="DDR4_4Gb_x8")
        assert MemorySystem(cfg).capacity == 8 * 2**30

    def test_lpddr4_8gb_x16(self):
        assert estimate_capacity("LPDDR4", "LPDDR4_8Gb_x16") == 2**30

    def test_stack_org(self):
        assert estimate_capacity("HBM", "HBM_1Gb") == 2**27
        assert estimate_capacity("WideIO", "WideIO_1Gb") == 2**27

    def test_salp(self):
        assert estimate_capacity("SALP-1", "SALP_512Mb_x4") == 2**30


class TestMapping:
    def test_valid_mapping_accepted(self):
        cfg = Config(
            standard="DDR3",
            speed="DDR3_1600K",
            org="DDR3_2Gb_x8",
            mapping="cacheline_interleaving",
        )
        assert cfg.validate() is None

    def test_default_mapping_accepted(self):
        cfg = Config(
            standard="DDR3",
            speed="DDR3_1600K",
            org="DDR3_2Gb_x8",
            mapping="defaultmapping",
        )
        assert cfg.validate() is None

    def test_invalid_mapping_rejected(self):
        cfg = Config(
            standard="DDR3",
            speed="DDR3_1600K",
            org="DDR3_2Gb_x8",
            mapping="bogus_mapping",
        )
        with pytest.raises(ValueError, match="invalid mapping"):
            cfg.validate()

    def test_ddr3_runs_with_mapping(self):
        from pyramulator import MemorySystem

        cfg = Config(
            standard="DDR3",
            speed="DDR3_1600K",
            org="DDR3_2Gb_x8",
            mapping="cacheline_interleaving",
        )
        mem = MemorySystem(cfg)
        done = []
        mem.drive_range(0, 16, 64, callback=lambda i: done.append(i))
        assert len(done) == 16

    def test_attribute_access(self, ddr4_config):
        assert ddr4_config.standard == "DDR4"
        assert ddr4_config.speed == "DDR4_2400R"
        assert ddr4_config.org == "DDR4_4Gb_x8"
        assert ddr4_config.channels == 1
        assert ddr4_config.ranks == 1
        assert isinstance(ddr4_config.mapping, str)

    def test_attribute_access_matches_dict(self, ddr4_config):
        cfg = Config(
            standard="DDR4", channels=4, ranks=2, speed="DDR4_2400R", org="DDR4_4Gb_x8"
        )
        assert cfg.channels == int(cfg["channels"])
        assert cfg.ranks == int(cfg["ranks"])

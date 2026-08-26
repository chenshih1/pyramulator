"""Configuration-related tests."""

from __future__ import annotations

import pytest

from pyramulator import (
    Config,
    RequestInfo,
    RequestType,
    config_dir,
    estimate_capacity,
    supported_orgs,
    supported_speeds,
    supported_standards,
    theoretical_bandwidth,
)
from pyramulator.configs import show
from tests.conftest import DDR3_1600K_CFG, DDR4_2400R_CFG


class TestConfig:
    def test_kwargs(self, ddr4_config) -> None:
        assert ddr4_config["standard"] == "DDR4"
        assert ddr4_config["speed"] == "DDR4_2400R"
        assert "channels" in ddr4_config

    def test_defaults_channels_ranks(self) -> None:
        cfg = Config(**DDR4_2400R_CFG)
        assert cfg["channels"] == "1"
        assert cfg["ranks"] == "1"

    def test_explicit_channels(self) -> None:
        cfg = Config(channels=4, ranks=2, **DDR4_2400R_CFG)
        assert cfg["channels"] == "4"
        assert cfg["ranks"] == "2"

    def test_from_file(self, ddr4_config_file) -> None:
        cfg = Config.from_file(str(ddr4_config_file))
        assert cfg["standard"] == "DDR4"
        assert cfg["channels"] == "1"

    def test_from_file_with_overrides(self, ddr4_config_file) -> None:
        cfg = Config.from_file(str(ddr4_config_file), channels=4, ranks=2)
        assert cfg["channels"] == "4"
        assert cfg["ranks"] == "2"
        assert cfg["standard"] == "DDR4"

    def test_validate_valid(self, ddr4_config) -> None:
        assert ddr4_config.validate() is None

    def test_validate_bad_standard(self) -> None:
        cfg = Config(standard="DDR5", speed="x", org="y")
        with pytest.raises(ValueError, match="unsupported standard"):
            cfg.validate()

    def test_validate_bad_speed(self) -> None:
        cfg = Config(**{**DDR4_2400R_CFG, "speed": "DDR4_9999X"})
        with pytest.raises(ValueError, match="invalid speed"):
            cfg.validate()

    def test_validate_bad_org(self) -> None:
        cfg = Config(**{**DDR4_2400R_CFG, "org": "DDR4_999Gb_x8"})
        with pytest.raises(ValueError, match="invalid org"):
            cfg.validate()

    def test_validate_bad_channels(self) -> None:
        cfg = Config(channels=3, **DDR4_2400R_CFG)
        with pytest.raises(ValueError, match="power of 2"):
            cfg.validate()

    def test_repr(self, ddr4_config) -> None:
        r = repr(ddr4_config)
        assert "DDR4" in r
        assert "DDR4_2400R" in r


class TestConfigsModule:
    def test_supported_standards(self) -> None:
        stds = supported_standards()
        assert "DDR4" in stds
        assert "HBM" in stds
        assert "SALP-1" in stds
        assert len(stds) == 11

    def test_supported_speeds(self) -> None:
        speeds = supported_speeds("DDR4")
        assert "DDR4_2400R" in speeds
        assert len(speeds) > 0

    def test_supported_orgs(self) -> None:
        orgs = supported_orgs("DDR4")
        assert "DDR4_4Gb_x8" in orgs

    def test_salp_variants_share_table(self) -> None:
        assert supported_speeds("SALP-1") == supported_speeds("SALP-2")
        assert supported_orgs("SALP-1") == supported_orgs("SALP-MASA")

    def test_show(self, capsys) -> None:
        show("DDR4")
        captured = capsys.readouterr()
        assert "DDR4_2400R" in captured.out


class TestRequestInfo:
    def test_latency_property(self) -> None:
        info = RequestInfo(
            addr=0x1000, type=RequestType.READ, arrive_cycle=10, depart_cycle=50
        )
        assert info.latency == 40

    def test_fields(self) -> None:
        info = RequestInfo(
            addr=0x2000, type=RequestType.WRITE, arrive_cycle=5, depart_cycle=15
        )
        assert info.addr == 0x2000
        assert info.type == RequestType.WRITE

    def test_default_core_id(self) -> None:
        info = RequestInfo(
            addr=0, type=RequestType.READ, arrive_cycle=0, depart_cycle=1
        )
        assert info.core_id == 0


class TestTheoreticalBandwidth:
    def test_ddr4_2400_1ch(self) -> None:
        cfg = Config(standard="DDR4", channels=1, speed="DDR4_2400R", org="DDR4_4Gb_x8")
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(19.2, rel=0.01)

    def test_ddr4_2400_2ch(self) -> None:
        cfg = Config(channels=2, **DDR4_2400R_CFG)
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(38.4, rel=0.01)

    def test_ddr3_1600_1ch(self) -> None:
        cfg = Config(channels=1, **DDR3_1600K_CFG)
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(12.8, rel=0.01)

    def test_gddr5_qdr(self) -> None:
        cfg = Config(
            standard="GDDR5", channels=1, speed="GDDR5_6000", org="GDDR5_8Gb_x32"
        )
        bw = theoretical_bandwidth(cfg)
        # GDDR5-6000: 6000 MT/s * 4 bytes (32-bit) = 24 GB/s per channel
        assert bw == pytest.approx(24.0, rel=0.01)

    def test_scales_with_channels(self) -> None:
        cfg1 = Config(channels=1, **DDR4_2400R_CFG)
        cfg4 = Config(channels=4, **DDR4_2400R_CFG)
        assert theoretical_bandwidth(cfg4) == pytest.approx(
            4 * theoretical_bandwidth(cfg1), rel=0.01
        )

    def test_accepts_dict(self) -> None:
        bw = theoretical_bandwidth({"channels": "1", **DDR4_2400R_CFG})
        assert bw > 0


class TestCapacity:
    def test_ddr4_4gb_x8(self, ddr4_config) -> None:
        from pyramulator._engine import MemorySystem

        assert MemorySystem(ddr4_config).capacity == 4 * 2**30

    def test_ddr4_scales_with_channels(self) -> None:
        from pyramulator._engine import MemorySystem

        cfg = Config(channels=2, **DDR4_2400R_CFG)
        assert MemorySystem(cfg).capacity == 8 * 2**30

    def test_lpddr4_8gb_x16(self) -> None:
        assert estimate_capacity("LPDDR4", "LPDDR4_8Gb_x16") == 2**30

    def test_stack_org(self) -> None:
        assert estimate_capacity("HBM", "HBM_1Gb") == 2**27
        assert estimate_capacity("WideIO", "WideIO_1Gb") == 2**27

    def test_salp(self) -> None:
        assert estimate_capacity("SALP-1", "SALP_512Mb_x4") == 2**30


class TestMapping:
    def test_valid_mapping_accepted(self) -> None:
        cfg = Config(
            standard="DDR3",
            speed="DDR3_1600K",
            org="DDR3_2Gb_x8",
            mapping="cacheline_interleaving",
        )
        assert cfg.validate() is None

    def test_default_mapping_accepted(self) -> None:
        cfg = Config(
            standard="DDR3",
            speed="DDR3_1600K",
            org="DDR3_2Gb_x8",
            mapping="defaultmapping",
        )
        assert cfg.validate() is None

    def test_invalid_mapping_rejected(self) -> None:
        cfg = Config(**DDR3_1600K_CFG, mapping="bogus_mapping")
        with pytest.raises(ValueError, match="invalid mapping"):
            cfg.validate()

    def test_ddr3_runs_with_mapping(self) -> None:
        from pyramulator._engine import MemorySystem

        cfg = Config(**DDR3_1600K_CFG, mapping="cacheline_interleaving")
        mem = MemorySystem(cfg)
        done = []
        mem.drive_range(0, 16, 64, callback=lambda i: done.append(i))
        assert len(done) == 16

    def test_attribute_access(self, ddr4_config) -> None:
        assert ddr4_config.standard == "DDR4"
        assert ddr4_config.speed == "DDR4_2400R"
        assert ddr4_config.org == "DDR4_4Gb_x8"
        assert ddr4_config.channels == 1
        assert ddr4_config.ranks == 1
        assert isinstance(ddr4_config.mapping, str)

    def test_attribute_access_matches_dict(self, ddr4_config) -> None:
        cfg = Config(
            standard="DDR4", channels=4, ranks=2, speed="DDR4_2400R", org="DDR4_4Gb_x8"
        )
        assert cfg.channels == int(cfg["channels"])
        assert cfg.ranks == int(cfg["ranks"])


class TestTheoreticalBandwidthEdgeCases:
    def test_unknown_speed_raises(self) -> None:
        cfg = Config(**{**DDR4_2400R_CFG, "speed": "DDR4_9999Z"})
        with pytest.raises(ValueError, match="unknown data rate"):
            theoretical_bandwidth(cfg)


class TestConfigDir:
    def test_config_dir_found(self) -> None:
        path = config_dir()
        assert path.is_dir()
        assert (path / "DDR4-config.cfg").exists()

    def test_config_dir_not_found_raises(self, monkeypatch) -> None:
        """When the bundled configs directory is absent, raise FileNotFoundError."""
        import pyramulator.configs

        def _fake_files(_pkg: str):
            from pathlib import Path

            return Path("/nonexistent")

        monkeypatch.setattr(pyramulator.configs, "_pkg_files", _fake_files)
        with pytest.raises(FileNotFoundError, match="package data missing"):
            config_dir()

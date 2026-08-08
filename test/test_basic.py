import pytest
from pyramulator import (
    Config, MemorySystem, RequestType, RequestInfo,
    supported_standards, supported_speeds, supported_orgs,
    theoretical_bandwidth,
)
from pyramulator.configs import show


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ddr4_config():
    return Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")


@pytest.fixture
def ddr3_config():
    return Config(standard="DDR3", speed="DDR3_1600K", org="DDR3_2Gb_x8")


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

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
        cfg = Config(standard="DDR4", channels=4, ranks=2,
                     speed="DDR4_2400R", org="DDR4_4Gb_x8")
        assert cfg["channels"] == "4"
        assert cfg["ranks"] == "2"

    def test_from_file(self):
        path = "/home/chens/workspace/pyramulator/src/ramulator/configs/DDR4-config.cfg"
        cfg = Config.from_file(path)
        assert cfg["standard"] == "DDR4"
        assert cfg["channels"] == "1"

    def test_from_file_with_overrides(self):
        path = "/home/chens/workspace/pyramulator/src/ramulator/configs/DDR4-config.cfg"
        cfg = Config.from_file(path, channels=4, ranks=2)
        assert cfg["channels"] == "4"
        assert cfg["ranks"] == "2"
        assert cfg["standard"] == "DDR4"

    def test_validate_valid(self, ddr4_config):
        assert ddr4_config.validate() is True

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
        cfg = Config(standard="DDR4", channels=3,
                     speed="DDR4_2400R", org="DDR4_4Gb_x8")
        with pytest.raises(ValueError, match="power of 2"):
            cfg.validate()

    def test_repr(self, ddr4_config):
        r = repr(ddr4_config)
        assert "DDR4" in r
        assert "DDR4_2400R" in r

    def test_set_overwrites(self):
        cfg = Config(standard="DDR4", channels=1,
                     speed="DDR4_2400R", org="DDR4_4Gb_x8")
        cfg.set("channels", "8")
        assert cfg["channels"] == "8"


# ---------------------------------------------------------------------------
# Configs module tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# RequestInfo tests
# ---------------------------------------------------------------------------

class TestRequestInfo:
    def test_latency_property(self):
        info = RequestInfo(addr=0x1000, type=RequestType.READ,
                           arrive=10, depart=50)
        assert info.latency == 40

    def test_fields(self):
        info = RequestInfo(addr=0x2000, type=RequestType.WRITE,
                           arrive=5, depart=15)
        assert info.addr == 0x2000
        assert info.type == RequestType.WRITE


# ---------------------------------------------------------------------------
# theoretical_bandwidth tests
# ---------------------------------------------------------------------------

class TestTheoreticalBandwidth:
    def test_ddr4_2400_1ch(self):
        cfg = Config(standard="DDR4", channels=1,
                     speed="DDR4_2400R", org="DDR4_4Gb_x8")
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(19.2, rel=0.01)

    def test_ddr4_2400_2ch(self):
        cfg = Config(standard="DDR4", channels=2,
                     speed="DDR4_2400R", org="DDR4_4Gb_x8")
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(38.4, rel=0.01)

    def test_ddr3_1600_1ch(self):
        cfg = Config(standard="DDR3", channels=1,
                     speed="DDR3_1600K", org="DDR3_2Gb_x8")
        bw = theoretical_bandwidth(cfg)
        assert bw == pytest.approx(12.8, rel=0.01)

    def test_gddr5_qdr(self):
        cfg = Config(standard="GDDR5", channels=1,
                     speed="GDDR5_6000", org="GDDR5_8Gb_x32")
        bw = theoretical_bandwidth(cfg)
        # GDDR5-6000: 6000 MT/s * 4 bytes (32-bit) = 24 GB/s per channel
        assert bw == pytest.approx(24.0, rel=0.01)

    def test_scales_with_channels(self):
        cfg1 = Config(standard="DDR4", channels=1,
                      speed="DDR4_2400R", org="DDR4_4Gb_x8")
        cfg4 = Config(standard="DDR4", channels=4,
                      speed="DDR4_2400R", org="DDR4_4Gb_x8")
        assert theoretical_bandwidth(cfg4) == pytest.approx(
            4 * theoretical_bandwidth(cfg1), rel=0.01)

    def test_accepts_dict(self):
        bw = theoretical_bandwidth(
            {"standard": "DDR4", "channels": "1",
             "speed": "DDR4_2400R", "org": "DDR4_4Gb_x8"})
        assert bw > 0


# ---------------------------------------------------------------------------
# MemorySystem core tests
# ---------------------------------------------------------------------------

class TestMemorySystem:
    def test_create(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        assert mem.tck > 0
        assert mem.clk == 0
        assert mem.pending == 0

    def test_create_from_dict(self):
        mem = MemorySystem({"standard": "DDR4", "channels": "1",
                            "ranks": "1", "speed": "DDR4_2400R",
                            "org": "DDR4_4Gb_x8"})
        assert mem.tck > 0

    def test_tick(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        mem.tick()
        assert mem.clk == 1

    def test_run(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        mem.run(100)
        assert mem.clk == 100

    def test_read_callback(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        results = []
        mem.send_read(0x1000, callback=lambda info: results.append(info))
        mem.run(1000)
        assert len(results) == 1
        assert results[0].addr == 0x1000
        assert results[0].type == RequestType.READ
        assert results[0].latency > 0

    def test_write_callback(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        results = []
        for i in range(32):
            mem.send_write(i * 64, callback=lambda info: results.append(info))
        mem.run(10000)
        assert len(results) > 0
        assert all(info.type == RequestType.WRITE for info in results)

    def test_run_until_idle(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        results = []
        for i in range(8):
            mem.send_read(i * 64, callback=lambda info: results.append(info))
        mem.run_until_idle()
        assert len(results) == 8
        assert mem.pending == 0

    def test_backpressure(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        results = [mem.send_read(i * 64) for i in range(64)]
        assert all(results[:32])

    def test_context_manager(self, ddr4_config):
        with MemorySystem(ddr4_config) as mem:
            mem.send_read(0x0)
            mem.run(100)

    def test_send_reads_batch(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        results = []
        accepted = mem.send_reads([0x0, 0x40, 0x80],
                                  callback=lambda info: results.append(info))
        assert all(accepted)
        mem.run_until_idle()
        assert len(results) == 3

    def test_send_writes_batch(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        results = []
        accepted = mem.send_writes([0x0, 0x40, 0x80, 0xC0] * 8,
                                   callback=lambda info: results.append(info))
        mem.run(10000)
        assert len(results) > 0

    def test_write_queue_watermark(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        mem.set_write_queue_watermark(high=0.9, low=0.1)
        mem.send_write(0x0)
        mem.run(100)

    def test_repr(self, ddr4_config):
        mem = MemorySystem(ddr4_config)
        r = repr(mem)
        assert "MemorySystem" in r
        assert "tck=" in r

    def test_multi_core(self):
        cfg = Config(standard="DDR4", channels=1,
                     speed="DDR4_2400R", org="DDR4_4Gb_x8")
        mem = MemorySystem(cfg, num_cores=4)
        results = []
        for core in range(4):
            mem.send_read(core * 0x1000, core_id=core,
                          callback=lambda info: results.append(info))
        mem.run_until_idle()
        assert len(results) == 4


# ---------------------------------------------------------------------------
# Multi-standard tests
# ---------------------------------------------------------------------------

class TestMultiStandard:
    @pytest.mark.parametrize("standard,speed,org", [
        ("DDR3", "DDR3_1600K", "DDR3_2Gb_x8"),
        ("DDR4", "DDR4_2400R", "DDR4_4Gb_x8"),
        ("LPDDR3", "LPDDR3_1600", "LPDDR3_8Gb_x32"),
        ("LPDDR4", "LPDDR4_2400", "LPDDR4_8Gb_x16"),
    ])
    def test_standard_read_completes(self, standard, speed, org):
        cfg = Config(standard=standard, speed=speed, org=org)
        mem = MemorySystem(cfg)
        results = []
        mem.send_read(0x1000, callback=lambda info: results.append(info))
        mem.run_until_idle()
        assert len(results) == 1
        assert results[0].latency > 0

    def test_multichannel(self):
        cfg = Config(standard="DDR4", channels=2,
                     speed="DDR4_2400R", org="DDR4_4Gb_x8")
        mem = MemorySystem(cfg)
        results = []
        for i in range(16):
            mem.send_read(i * 64, callback=lambda info: results.append(info))
        mem.run_until_idle()
        assert len(results) == 16


# ---------------------------------------------------------------------------
# Benchmark integration tests
# ---------------------------------------------------------------------------

class TestBenchmark:
    def test_sequential_latency(self, ddr4_config):
        """Sequential reads should have bounded, positive latency."""
        mem = MemorySystem(ddr4_config)
        latencies = []
        num_requests = 64

        for i in range(num_requests):
            addr = i * 64
            while not mem.send_read(addr, callback=lambda info:
                                    latencies.append(info.latency)):
                mem.tick()

        mem.run_until_idle()
        assert len(latencies) == num_requests
        assert all(lat > 0 for lat in latencies)
        avg = sum(latencies) / len(latencies)
        assert 10 < avg < 500

    def test_random_latency_higher_than_sequential(self):
        """Random access should have higher avg latency than sequential."""
        import random
        rng = random.Random(42)
        cfg = Config(standard="DDR4", speed="DDR4_2400R", org="DDR4_4Gb_x8")

        seq_lats = []
        with MemorySystem(cfg) as mem:
            for i in range(64):
                while not mem.send_read(i * 64, callback=lambda info:
                                        seq_lats.append(info.latency)):
                    mem.tick()
            mem.run_until_idle()

        rand_lats = []
        addrs = [rng.randrange(0, 1 << 24, 64) for _ in range(64)]
        with MemorySystem(cfg) as mem:
            for addr in addrs:
                while not mem.send_read(addr, callback=lambda info:
                                        rand_lats.append(info.latency)):
                    mem.tick()
            mem.run_until_idle()

        seq_avg = sum(seq_lats) / len(seq_lats)
        rand_avg = sum(rand_lats) / len(rand_lats)
        assert rand_avg >= seq_avg

    def test_throughput_positive(self, ddr4_config):
        """Sustained reads should achieve measurable bandwidth."""
        mem = MemorySystem(ddr4_config)
        completed = [0]
        first_clk = [None]
        last_clk = [0]
        num_requests = 128

        def on_done(info):
            completed[0] += 1
            if first_clk[0] is None:
                first_clk[0] = info.depart
            last_clk[0] = info.depart

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

    def test_multichannel_throughput_scales(self):
        """2-channel should achieve higher throughput than 1-channel."""
        def measure_bw(channels):
            cfg = Config(standard="DDR4", channels=channels,
                         speed="DDR4_2400R", org="DDR4_4Gb_x8")
            mem = MemorySystem(cfg)
            completed = [0]
            first = [None]
            last = [0]

            def on_done(info):
                completed[0] += 1
                if first[0] is None:
                    first[0] = info.depart
                last[0] = info.depart

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

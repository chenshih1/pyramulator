"""DES kernel, hardware primitives, and Dram component tests."""

from __future__ import annotations

import pytest

from pyramulator import (
    FIFO,
    Clock,
    Component,
    Config,
    Dram,
    Pipe,
    RequestType,
    Simulator,
)
from tests.conftest import DDR4_2400R_CFG


class TestSimulator:
    def test_next_event_time_advance(self) -> None:
        sim = Simulator()
        seen = []
        sim.schedule(5, lambda: seen.append(sim.now))
        sim.schedule(2, lambda: seen.append(sim.now))
        sim.schedule(9, lambda: seen.append(sim.now))
        assert sim.run() == 3
        assert seen == [2, 5, 9]
        assert sim.now == 9
        assert sim.pending == 0

    def test_fifo_order_at_same_time(self) -> None:
        sim = Simulator()
        order = []
        sim.schedule(0, lambda: order.append("a"))
        sim.schedule(0, lambda: order.append("b"))
        sim.schedule(0, lambda: order.append("c"))
        sim.run()
        assert order == ["a", "b", "c"]

    def test_priority_order(self) -> None:
        sim = Simulator()
        order = []
        sim.schedule(0, lambda: order.append("p0"), priority=5)
        sim.schedule(0, lambda: order.append("p1"), priority=1)
        sim.schedule(0, lambda: order.append("p2"), priority=3)
        sim.run()
        assert order == ["p1", "p2", "p0"]

    def test_delta_events_run_after_queued(self) -> None:
        sim = Simulator()
        order = []
        sim.schedule(
            0, lambda: (order.append("a"), sim.schedule(0, lambda: order.append("d")))
        )
        sim.schedule(0, lambda: order.append("b"))
        sim.run()
        assert order == ["a", "b", "d"]

    def test_cancel(self) -> None:
        sim = Simulator()
        seen = []
        eid = sim.schedule(0, lambda: seen.append(1))
        sim.schedule(0, lambda: seen.append(2))
        assert sim.cancel(eid) is True
        assert sim.cancel(eid) is False  # already cancelled
        sim.run()
        assert seen == [2]
        assert sim.pending == 0

    def test_negative_delay_rejected(self) -> None:
        sim = Simulator()
        with pytest.raises(ValueError, match="negative delay"):
            sim.schedule(-1, lambda: None)

    def test_at_in_past_rejected(self) -> None:
        sim = Simulator()
        sim.schedule(5, lambda: None)
        sim.run()
        with pytest.raises(ValueError, match="cannot schedule"):
            sim.at(3, lambda: None)

    def test_at_absolute(self) -> None:
        sim = Simulator()
        seen = []
        sim.schedule(3, lambda: None)
        sim.run()
        sim.at(sim.now + 7, lambda: seen.append(sim.now))
        sim.run()
        assert seen == [10]

    def test_run_until_inclusive(self) -> None:
        sim = Simulator()
        seen = []
        sim.schedule(2, lambda: seen.append(2))
        sim.schedule(4, lambda: seen.append(4))
        sim.schedule(6, lambda: seen.append(6))
        assert sim.run(until=4) == 2
        assert seen == [2, 4]
        assert sim.now == 4
        assert sim.pending == 1

    def test_run_max_events(self) -> None:
        sim = Simulator()
        for _ in range(10):
            sim.schedule(0, lambda: None)
        assert sim.run(max_events=3) == 3
        assert sim.pending == 7

    def test_step_empty(self) -> None:
        assert Simulator().step() is False

    def test_deterministic_order(self) -> None:
        def run_once():
            sim = Simulator()
            order = []
            for t, p in [(3, 2), (1, 0), (3, 0), (2, 1), (3, 1)]:
                sim.schedule(t, lambda p=p: order.append(p), priority=p)
            sim.run()
            return order

        assert run_once() == run_once()

    def test_exception_propagates_and_state_consistent(self) -> None:
        sim = Simulator()
        sim.schedule(0, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        sim.schedule(5, lambda: None)
        with pytest.raises(RuntimeError, match="boom"):
            sim.run()
        assert sim.now == 0
        assert sim.pending == 1
        assert sim.run() == 1
        assert sim.now == 5

    def test_processed_counter(self) -> None:
        sim = Simulator()
        sim.schedule(0, lambda: None)
        sim.schedule(1, lambda: None)
        assert sim.processed == 0
        sim.step()
        assert sim.processed == 1
        sim.run()
        assert sim.processed == 2


class TestClock:
    def test_cycles(self) -> None:
        clk = Clock(1000, "host")
        assert clk.period_ps == 1000
        assert clk.cycles(4) == 4000
        assert clk.cycles(0) == 0

    def test_invalid_period(self) -> None:
        with pytest.raises(ValueError):
            Clock(0)
        with pytest.raises(ValueError):
            Clock(-5)

    def test_negative_cycles_rejected(self) -> None:
        with pytest.raises(ValueError):
            Clock(1000).cycles(-1)

    def test_repr(self) -> None:
        assert repr(Clock(1000, "host")) == "Clock('host', 1000ps)"


class TestComponent:
    def test_schedule_ps(self) -> None:
        sim = Simulator()
        seen = []
        c = Component(sim, Clock(1000), "c")
        c.schedule_ps(5, lambda: seen.append(1))
        sim.run()
        assert seen == [1]
        assert sim.now == 5

    def test_reset_hook(self) -> None:
        class MyComp(Component):
            def reset(self) -> None:
                self.flag = True

        sim = Simulator()
        c = MyComp(sim, Clock(1), "my")
        assert not hasattr(c, "flag")
        c.reset()
        assert c.flag is True

    def test_repr(self) -> None:
        sim = Simulator()
        c = Component(sim, Clock(1), "c")
        assert repr(c) == "Component('c')"


class TestFIFO:
    def test_put_get_order(self) -> None:
        sim = Simulator()
        fifo = FIFO(sim, Clock(1), capacity=3)
        assert fifo.put(1) and fifo.put(2) and fifo.put(3)
        assert not fifo.put(4)  # full
        assert fifo.full and not fifo.empty
        assert fifo.level == 3
        assert fifo.peek() == 1
        assert fifo.get() == 1
        assert fifo.get() == 2
        assert fifo.can_put()
        assert fifo.put(4)
        assert fifo.get() == 3
        assert fifo.get() == 4
        assert fifo.empty
        assert not fifo.can_get()
        with pytest.raises(IndexError):
            fifo.get()

    def test_clear(self) -> None:
        sim = Simulator()
        fifo = FIFO(sim, Clock(1), capacity=2)
        fifo.put("x")
        fifo.clear()
        assert fifo.empty and fifo.level == 0

    def test_capacity_rejected(self) -> None:
        with pytest.raises(ValueError):
            FIFO(Simulator(), Clock(1), capacity=0)

    def test_capacity_property(self) -> None:
        sim = Simulator()
        fifo = FIFO(sim, Clock(1), capacity=5)
        assert fifo.capacity == 5


class TestPipe:
    def test_delivery_latency(self) -> None:
        sim = Simulator()
        got = []
        pipe = Pipe(sim, Clock(1000), latency_cycles=4, consumer=got.append)
        assert pipe.put("a")
        assert sim.pending == 1
        assert sim.step() is True
        assert got == ["a"]
        assert sim.now == 4000  # time jumped straight to the delivery
        assert pipe.in_flight == 0

    def test_slots_bound(self) -> None:
        sim = Simulator()
        got = []
        pipe = Pipe(sim, Clock(1), latency_cycles=2, slots=2, consumer=got.append)
        assert pipe.put(1) and pipe.put(2)
        assert not pipe.put(3)
        assert pipe.full and pipe.in_flight == 2
        sim.run_until_idle()
        assert got == [1, 2]
        assert pipe.in_flight == 0

    def test_consumer_required(self) -> None:
        with pytest.raises(ValueError, match="consumer"):
            Pipe(Simulator(), Clock(1), latency_cycles=1)

    def test_invalid_params(self) -> None:
        with pytest.raises(ValueError):
            Pipe(Simulator(), Clock(1), latency_cycles=0)
        with pytest.raises(ValueError):
            Pipe(Simulator(), Clock(1), latency_cycles=1, slots=0)

    def test_properties(self) -> None:
        sim = Simulator()
        pipe = Pipe(sim, Clock(1), latency_cycles=3, slots=4, consumer=lambda x: x)
        assert pipe.latency_cycles == 3
        assert pipe.slots == 4
        assert pipe.can_put()
        assert not pipe.full

    def test_stall_then_accept(self) -> None:
        """Consumer stalls once then accepts; _retry drains the queue."""
        sim = Simulator()
        accepted = []
        stall = [True]

        def consumer(item):
            if stall[0]:
                stall[0] = False
                return False
            accepted.append(item)
            return None

        pipe = Pipe(sim, Clock(1), latency_cycles=1, slots=2, consumer=consumer)
        assert pipe.put("a")
        sim.run_until_idle()
        assert accepted == ["a"]
        assert pipe.in_flight == 0


def _ddr4(**kw):
    sim = Simulator()
    return sim, Dram(sim, Config(**DDR4_2400R_CFG), **kw)


class TestDram:
    def test_read_completion(self) -> None:
        sim, dram = _ddr4()
        done = []
        assert dram.read(0x1000, callback=done.append)
        assert dram.pending == 1
        sim.run_until_idle()
        assert len(done) == 1
        info = done[0]
        assert info.addr == 0x1000
        assert info.type == RequestType.READ
        assert info.latency > 0
        assert dram.pending == 0
        assert dram.cycles == info.depart_cycle  # engine ticked exactly to departure

    def test_no_events_when_idle(self) -> None:
        sim, _ = _ddr4()
        assert sim.pending == 0  # an idle DRAM schedules nothing

    def test_backpressure_and_retry(self) -> None:
        sim, dram = _ddr4()
        accepted = [dram.read(i * 64) for i in range(64)]
        assert not all(accepted)  # the queue is bounded
        assert sum(accepted) > 0
        done = []
        for i, ok in enumerate(accepted):
            if not ok:
                while not dram.read(i * 64, callback=done.append):
                    sim.step()
        sim.run_until_idle()
        assert dram.pending == 0

    def test_write_completes_on_acceptance(self) -> None:
        sim, dram = _ddr4()
        done = []
        assert dram.write(0x1000, callback=done.append)
        assert len(done) == 0  # acceptance completion runs as a delta event
        sim.run_until_idle()
        assert len(done) == 1
        info = done[0]
        assert info.type == RequestType.WRITE
        assert info.latency == 0
        assert dram.pending == 0

    def test_flush_barrier(self) -> None:
        _, dram = _ddr4()
        for i in range(16):
            dram.write(i * 64)
        assert dram.pending > 0
        processed = dram.flush()
        assert dram.pending == 0
        assert processed > 0

    def test_flush_returns_zero_when_idle(self) -> None:
        _, dram = _ddr4()
        assert dram.flush() == 0

    def test_read_latency_matches_engine(self) -> None:
        # The DES wrapper must preserve the engine's exact timing.
        from pyramulator._engine import MemorySystem

        sim, dram = _ddr4()
        done = []
        dram.read(0x1000, callback=done.append)
        sim.run_until_idle()

        mem = MemorySystem(Config(**DDR4_2400R_CFG))
        ref = []
        mem.send_read(0x1000, callback=ref.append)
        mem.run_until_idle()
        assert done[0].latency == ref[0].latency
        assert done[0].arrive_cycle == ref[0].arrive_cycle
        assert done[0].depart_cycle == ref[0].depart_cycle

    def test_metrics(self) -> None:
        sim, dram = _ddr4()
        for i in range(32):  # 32 fits the read queue; all accepted
            dram.read(i * 64)
        sim.run_until_idle()
        m = dram.metrics()
        assert m["read_requests"] == 32
        assert m["avg_read_latency_cycles"] > 0
        assert 0.0 <= m["row_hit_rate"] <= 1.0
        assert m["bandwidth_gbs"] > 0

    def test_completion_priority_ordering(self) -> None:
        sim = Simulator()
        cfg = Config(**DDR4_2400R_CFG)
        dram_a = Dram(sim, cfg, completion_priority=0, name="dram_a")
        dram_b = Dram(sim, cfg, completion_priority=10, name="dram_b")
        order = []
        dram_a.read(0x1000, callback=lambda info: order.append("a"))
        dram_b.read(0x1000, callback=lambda info: order.append("b"))
        sim.run_until_idle()
        assert order == ["a", "b"]

    def test_core_id_out_of_range(self) -> None:
        _, dram = _ddr4()
        with pytest.raises(ValueError, match="core_id"):
            dram.read(0x1000, core_id=1)

    def test_multi_core(self) -> None:
        sim = Simulator()
        cfg = Config(**DDR4_2400R_CFG)
        dram = Dram(sim, cfg, num_cores=4)
        done = []
        for core in range(4):
            dram.read(0x1000 + core * 64, core_id=core, callback=done.append)
        sim.run_until_idle()
        assert len(done) == 4
        assert {info.core_id for info in done} == {0, 1, 2, 3}

    def test_dict_config(self) -> None:
        sim = Simulator()
        dram = Dram(
            sim,
            dict(DDR4_2400R_CFG),
        )
        done = []
        dram.read(0x1000, callback=done.append)
        sim.run_until_idle()
        assert len(done) == 1

    def test_completion_time_matches_depart_cycle(self) -> None:
        sim, dram = _ddr4()
        done: list[tuple[int, int]] = []

        def on_complete(info):
            done.append((sim.now, info.depart_cycle))

        dram.read(0x1000, callback=on_complete)
        sim.run_until_idle()
        now, depart = done[0]
        assert now == depart * dram.period_ps
        assert dram.cycles == depart

    def test_empty_cycles_coalesced(self) -> None:
        """Idle DRAM cycles between completions are not simulator events."""
        sim, dram = _ddr4()
        done = []
        dram.read(0x1000, callback=done.append)
        sim.run_until_idle()
        assert done[0].latency > 1
        assert sim.processed < dram.cycles
        assert sim.now == done[0].depart_cycle * dram.period_ps

    def test_coalesce_does_not_skip_other_events(self) -> None:
        sim, dram = _ddr4()
        seen: list[tuple[str, int]] = []
        dram.read(
            0x1000,
            callback=lambda info: seen.append(("read", sim.now)),
        )
        mid = 10 * dram.period_ps
        sim.schedule(mid, lambda: seen.append(("host", sim.now)))
        sim.run_until_idle()
        assert seen[0] == ("host", mid)
        assert seen[1][0] == "read"
        assert seen[1][1] == dram.cycles * dram.period_ps
        assert seen[1][1] > mid

    def test_distinct_callbacks_not_confused(self) -> None:
        sim, dram = _ddr4()
        a: list = []
        b: list = []
        assert dram.read(0x1000, callback=a.append)
        assert dram.read(0x2000, callback=b.append)
        sim.run_until_idle()
        assert [info.addr for info in a] == [0x1000]
        assert [info.addr for info in b] == [0x2000]


class TestSimulatorProfiling:
    def test_next_time(self) -> None:
        sim = Simulator()
        assert sim.next_time is None
        sim.schedule(1000, lambda: None)
        assert sim.next_time == 1000
        sim.run()
        assert sim.next_time is None

    def test_event_counts_by_source(self) -> None:
        sim = Simulator()
        sim.schedule(0, lambda: None, source="a")
        sim.schedule(0, lambda: None, source="b")
        sim.schedule(0, lambda: None)
        assert sim.event_counts == {"a": 1, "b": 1, None: 1}
        sim.run()
        assert sim.event_counts == {"a": 1, "b": 1, None: 1}  # cumulative

    def test_component_events_attributed(self) -> None:
        sim = Simulator()
        clk = Clock(1)
        comp = Component(sim, clk, "core0")
        comp.schedule_cycles(1, lambda: None)
        assert sim.event_counts == {"core0": 1}


class TestSimulatorAdvance:
    def test_advance_to_empty(self) -> None:
        sim = Simulator()
        sim._advance_to(100)
        assert sim.now == 100

    def test_advance_to_rejects_past(self) -> None:
        sim = Simulator()
        sim.schedule(5, lambda: None)
        sim.run()
        with pytest.raises(ValueError, match="cannot advance"):
            sim._advance_to(3)

    def test_advance_to_rejects_skipping_event(self) -> None:
        sim = Simulator()
        sim.schedule(10, lambda: None)
        sim._advance_to(10)  # landing on the next event is ok
        assert sim.now == 10
        with pytest.raises(RuntimeError, match="event pending"):
            sim._advance_to(11)


class TestPipeBackpressure:
    def test_stall_then_accept(self) -> None:
        sim = Simulator()
        got = []
        state = {"stalled": True}

        def consumer(item):
            if state["stalled"]:
                state["stalled"] = False
                return False  # downstream full
            got.append(item)

        pipe = Pipe(sim, Clock(1000), latency_cycles=2, consumer=consumer)
        assert pipe.put("x")
        sim.run_until_idle()
        assert got == ["x"]
        assert pipe.in_flight == 0
        assert sim.now == 3000  # 2 cycles latency + 1 cycle stall retry

    def test_in_flight_held_while_stalled(self) -> None:
        sim = Simulator()
        state = {"rejected": 0}

        def consumer(item):
            state["rejected"] += 1
            return state["rejected"] != 1  # reject the first delivery only

        pipe = Pipe(sim, Clock(1), latency_cycles=1, consumer=consumer)
        assert pipe.put("x")
        assert pipe.in_flight == 1
        sim.step()  # first delivery: stalled -> in_flight held
        assert pipe.in_flight == 1
        sim.step()  # retry: accepted -> released
        assert pipe.in_flight == 0
        assert state["rejected"] == 2


class TestDramBatch:
    def test_reads(self) -> None:
        sim, dram = _ddr4()
        done = []
        accepted = dram.reads(range(0, 32 * 64, 64), callback=done.append)
        assert len(accepted) == 32 and all(accepted)
        sim.run_until_idle()
        assert len(done) == 32
        assert all(info.latency > 0 for info in done)
        assert dram.pending == 0

    def test_reads_backpressure(self) -> None:
        sim, dram = _ddr4()
        accepted = dram.reads(range(0, 64 * 64, 64))
        assert not all(accepted)
        assert sum(accepted) > 0
        sim.run_until_idle()
        assert dram.pending == 0

    def test_writes(self) -> None:
        sim, dram = _ddr4()
        done = []
        accepted = dram.writes(range(0, 16 * 64, 64), callback=done.append)
        assert len(accepted) == 16 and all(accepted)
        assert len(done) == 0  # acceptance events are delivered as events
        sim.run_until_idle()
        assert len(done) == 16
        assert all(info.latency == 0 for info in done)
        assert dram.pending == 0


class TestDramIdleRefresh:
    def _idle_dram(self, batch=512):
        sim = Simulator()
        cfg = Config(**DDR4_2400R_CFG)
        return sim, Dram(sim, cfg, idle_refresh=True, idle_batch_cycles=batch)

    def test_wall_clock_advances_when_idle(self) -> None:
        sim, dram = self._idle_dram()
        window_cycles = 10_000
        sim.run(until=window_cycles * dram.period_ps)
        # With adaptive back-off the exact cycle count is no longer fixed;
        # just assert that wall-clock advanced substantially and the next
        # idle event is still queued.
        assert 0 < dram.cycles < window_cycles
        assert sim.pending == 1  # the next idle batch is queued

    def test_busy_handover(self) -> None:
        sim, dram = self._idle_dram()
        done = []
        sim.schedule(
            5_000 * dram.period_ps,
            lambda: dram.read(0x1000, callback=done.append),
        )
        sim.run(until=10_000 * dram.period_ps)
        assert len(done) == 1
        assert dram.pending == 0

    def test_idle_after_busy_resumes(self) -> None:
        sim, dram = self._idle_dram()
        done = []
        for i in range(16):
            dram.read(i * 64, callback=done.append)
        sim.run(until=20_000 * dram.period_ps)
        assert len(done) == 16
        before = dram.cycles
        extra = 10_000
        max_batch = 512 * 16  # adaptive max idle batch
        sim.run(until=(before + extra) * dram.period_ps)
        # The last adaptive batch may overshoot by up to max_batch cycles.
        assert dram.cycles >= before + extra - max_batch


class TestDramMultiChannel:
    def test_reads_across_channels(self) -> None:
        sim = Simulator()
        cfg = Config(channels=2, **DDR4_2400R_CFG)
        dram = Dram(sim, cfg)
        done = []
        for i in range(64):
            dram.read(i * 64, callback=done.append)
        sim.run_until_idle()
        assert len(done) == 64
        assert dram.pending == 0
        assert dram.metrics()["read_requests"] == 64


class TestDramFlushInCallback:
    def test_flush_inside_event(self) -> None:
        """flush() may be called from within an event callback."""
        sim, dram = _ddr4()
        done = []
        events = []

        def phase():
            for i in range(16):
                dram.write(i * 64, callback=done.append)
            events.append(("flushed", dram.flush()))
            events.append(("pending", dram.pending))

        sim.schedule(0, phase)
        sim.run_until_idle()
        assert events[0][0] == "flushed" and events[0][1] > 0
        assert events[1] == ("pending", 0)


class TestPipeFifoIntegration:
    def test_pipe_feeds_fifo(self) -> None:
        sim = Simulator()
        clk = Clock(1000, "host")
        fifo = FIFO(sim, clk, capacity=4)
        pipe = Pipe(sim, clk, latency_cycles=3, slots=2, consumer=fifo.put)
        assert pipe.put("a") and pipe.put("b")
        sim.run_until_idle()
        assert fifo.level == 2
        assert fifo.get() == "a" and fifo.get() == "b"
        assert fifo.empty and pipe.in_flight == 0

    def test_full_fifo_stalls_pipe(self) -> None:
        sim = Simulator()
        clk = Clock(1000, "host")
        fifo = FIFO(sim, clk, capacity=1)
        pipe = Pipe(sim, clk, latency_cycles=2, slots=2, consumer=fifo.put)
        assert pipe.put("a") and pipe.put("b")
        sim.step()  # t=2000: deliver "a" into the fifo
        assert fifo.level == 1 and fifo.peek() == "a"
        sim.step()  # t=2000: deliver "b" -> stalled, fifo still full
        assert pipe.in_flight == 1 and fifo.level == 1
        fifo.get()  # downstream drains
        sim.step()  # t=3000: retry delivers "b"
        assert fifo.level == 1 and fifo.peek() == "b"
        assert pipe.in_flight == 0
        assert sim.now == 3000

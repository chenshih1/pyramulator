#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include <deque>
#include <map>
#include <set>
#include <string>
#include <functional>

#include "Config.h"
#include "Request.h"
#include "MemoryFactory.h"
#include "Memory.h"
#include "StatType.h"
#include "DDR3.h"
#include "DDR4.h"
#include "LPDDR3.h"
#include "LPDDR4.h"
#include "GDDR5.h"
#include "WideIO.h"
#include "HBM.h"

namespace py = pybind11;
using namespace ramulator;

// ---------------------------------------------------------------------------
// Statistics access. Ramulator keeps every stat object in the public global
// Stats::all_stats; values are read through the public virtual vresult().
// The display name lives in the protected Stats::Stat<Derived>::_name, which
// we reach through the classic derived-class static accessor trick (no
// ramulator source is modified).
// ---------------------------------------------------------------------------
namespace {

template <typename Derived>
struct StatNameHack : Stats::Stat<Derived> {
    static const std::string &get(Stats::Stat<Derived> *stat) {
        return static_cast<StatNameHack *>(stat)->_name;
    }
};

template <typename Derived>
bool stat_name_of(Stats::StatBase *stat, std::string &out) {
    auto *typed = dynamic_cast<Stats::Stat<Derived> *>(stat);
    if (!typed)
        return false;
    out = StatNameHack<Derived>::get(typed);
    return true;
}

std::string stat_name(Stats::StatBase *stat) {
    std::string name;
    if (stat_name_of<Stats::ConstValue>(stat, name) ||
        stat_name_of<Stats::Scalar>(stat, name) ||
        stat_name_of<Stats::Average>(stat, name) ||
        stat_name_of<Stats::Vector>(stat, name) ||
        stat_name_of<Stats::AverageVector>(stat, name) ||
        stat_name_of<Stats::Distribution>(stat, name) ||
        stat_name_of<Stats::Histogram>(stat, name) ||
        stat_name_of<Stats::StandardDeviation>(stat, name) ||
        stat_name_of<Stats::AverageDeviation>(stat, name)) {
        // Ramulator prefixes every stat name with "ramulator.".
        const std::string prefix = "ramulator.";
        if (name.compare(0, prefix.size(), prefix) == 0)
            name.erase(0, prefix.size());
        return name;
    }
    return "";
}

// Reads the stats owned by one live PyMemorySystem instance. Ramulator
// keeps every stat object in the process-global Stats::all_stats (raw
// pointers that dangle once their owning Memory is destroyed), so each
// instance records the index range of the stats created while it
// constructed its memory, and only ever reads within that range.
static py::dict stats_slice(size_t begin, size_t end) {
    py::dict result;
    for (size_t i = begin; i < end && i < Stats::all_stats.size(); ++i) {
        Stats::StatBase *stat = Stats::all_stats[i];
        if (!stat)
            continue;
        stat->prepare();
        std::string name = stat_name(stat);
        if (name.empty())
            continue;

        // Read values through each concrete type's own result() accessor:
        // the generic vresult() path is broken upstream (VectorBase::vresult
        // indexes an un-resized vector and crashes).
        Stats::VResult values;
        if (auto *s = dynamic_cast<Stats::Scalar *>(stat)) {
            values.assign(1, s->result());
        } else if (auto *s = dynamic_cast<Stats::Average *>(stat)) {
            values.assign(1, s->result());
        } else if (auto *s = dynamic_cast<Stats::ConstValue *>(stat)) {
            values.assign(1, s->result());
        } else if (auto *v = dynamic_cast<Stats::Vector *>(stat)) {
            v->result(values);
        } else if (auto *v = dynamic_cast<Stats::AverageVector *>(stat)) {
            v->result(values);
        } else {
            continue;  // Distribution/Histogram/... have no result accessor
        }

        if (values.size() == 1) {
            result[py::str(name)] = values[0];
        } else {
            py::list items;
            for (double v : values)
                items.append(v);
            result[py::str(name)] = items;
        }
    }
    return result;
}

// The module-level get_stats()/reset_stats() mirror gem5's printStats
// semantics, but Ramulator stats are process-global, so they only make
// sense with exactly one live MemorySystem. Defined after PyMemorySystem
// below.

}  // namespace

// Mirrors the standard-name table inside ramulator's Gem5Wrapper so we can
// raise a friendly error instead of tripping its assert in release builds.
static const std::set<std::string> supported_standards = {
    "DDR3", "DDR4", "LPDDR3", "LPDDR4",
    "GDDR5", "WideIO", "WideIO2", "HBM",
    "SALP-1", "SALP-2", "SALP-MASA",
};

// Thin Python-facing wrapper around ramulator's public API (MemoryFactory +
// MemoryBase), the same calls gem5's Gem5Wrapper makes. No ramulator source
// is modified.
class PyMemorySystem {
public:
    PyMemorySystem(Config config, int cacheline, int num_cores) {
        if (config.get_core_num() == 0)
            config.set_core_num(num_cores);
        const std::string &std_name = config["standard"];
        if (supported_standards.find(std_name) == supported_standards.end())
            throw std::invalid_argument("unsupported standard: " + std_name);
        const size_t stats_begin = Stats::all_stats.size();
        mem_ = create_memory(config, cacheline, std_name);
        stats_range_ = {stats_begin, Stats::all_stats.size()};
        tck_ = mem_->clk_ns();
        live_.insert(this);
    }

    ~PyMemorySystem() {
        live_.erase(this);
        delete mem_;
    }

    static const std::set<PyMemorySystem *> &live_instances() { return live_; }

    py::dict get_stats() { return stats_slice(stats_range_.first, stats_range_.second); }

    void reset_stats() {
        for (size_t i = stats_range_.first; i < stats_range_.second; ++i)
            if (Stats::all_stats[i])
                Stats::all_stats[i]->reset();
    }

    void tick() { mem_->tick(); }

    // Completion callback for a request. Ramulator fires the callback for
    // read completions only (writes never enter its pending list), so reads
    // are recorded into the Python-facing queue here — no GIL, no Python
    // calls from the simulation hot path; the Python side flushes them in
    // bulk via drain_completed(). Writes get a no-op: the wrapper answers
    // them upon acceptance.
    std::function<void(Request &)> make_callback(Request::Type type,
                                                 py::object callback,
                                                 int coreid) {
        if (type == Request::Type::READ && !callback.is_none()) {
            return [this, callback, coreid](Request &r) {
                completed_.push_back(
                    {r.addr, static_cast<int>(r.type), r.arrive, r.depart,
                     coreid, callback});
            };
        }
        return [](Request &) {};
    }

    bool send(long addr, Request::Type type, int coreid,
              py::object callback) {
        Request req;
        req.addr = addr;
        req.type = type;
        req.coreid = coreid;
        req.is_first_command = true;
        req.callback = make_callback(type, callback, coreid);
        return mem_->send(req);
    }

    // ------------------------------------------------------------------
    // Drive loop: the whole backpressure + tick loop runs inside C++, the
    // role gem5's MemCtrl scheduler plays. Requests are issued until the
    // in-flight count reaches queue_depth; the DRAM then advances in
    // batches of `batch` cycles (no send attempts inside a batch), until
    // every request completes or max_cycles is hit. Returns
    // (cycles_run, issued, completion_events).
    // ------------------------------------------------------------------
    template <typename Sender>
    py::tuple drive_loop(Sender send_one, long total, int queue_depth,
                         long batch, long max_cycles, py::object callback) {
        std::function<void(Request &)> cb;
        if (!callback.is_none()) {
            cb = [this, callback](Request &r) {
                completed_.push_back(
                    {r.addr, static_cast<int>(r.type), r.arrive, r.depart,
                     r.coreid, callback});
                ++completed_count_;
            };
        } else {
            cb = [this](Request &) { ++completed_count_; };
        }

        long issued = 0;
        long cycles = 0;
        while (issued < total && cycles < max_cycles) {
            // Fill the queue while slots are available.
            while (issued < total &&
                   (issued - completed_count_) < queue_depth) {
                if (!send_one(issued, cb))
                    break;  // queue full; advance and retry
                ++issued;
            }
            // Advance the DRAM for a batch of cycles without send attempts.
            // Keeping the queue drained inside the batch keeps the
            // controller's per-cycle scheduling cost low.
            long ticks = 0;
            while (ticks < batch && issued < total &&
                   cycles < max_cycles) {
                mem_->tick();
                ++cycles;
                ++ticks;
            }
        }
        // Drain in-flight requests after the last one is issued.
        while ((issued - completed_count_) > 0 && cycles < max_cycles) {
            mem_->tick();
            ++cycles;
        }
        return py::make_tuple(cycles, issued, drain_completed());
    }

    py::tuple drive(const py::list &addrs, int queue_depth, long batch,
                    long max_cycles, py::object callback) {
        const long total = static_cast<long>(addrs.size());
        return drive_loop(
            [&](long i, std::function<void(Request &)> &cb) {
                Request req;
                req.addr = addrs[static_cast<size_t>(i)].cast<long>();
                req.type = Request::Type::READ;
                req.coreid = 0;
                req.is_first_command = true;
                req.callback = cb;
                return mem_->send(req);
            },
            total, queue_depth, batch, max_cycles, callback);
    }

    py::tuple drive_range(long start, long count, long stride,
                          int queue_depth, long batch, long max_cycles,
                          py::object callback) {
        return drive_loop(
            [&](long i, std::function<void(Request &)> &cb) {
                Request req;
                req.addr = start + i * stride;
                req.type = Request::Type::READ;
                req.coreid = 0;
                req.is_first_command = true;
                req.callback = cb;
                return mem_->send(req);
            },
            count, queue_depth, batch, max_cycles, callback);
    }

    // across many requests.
    // Bulk send: build and enqueue one request per address in a single C++
    // call, returning the accept flag for each. Amortizes pybind overhead
    // across many requests.
    py::list send_batch(const py::list &addrs, Request::Type type, int coreid,
                        py::object callback) {
        py::list accepted;
        for (auto item : addrs) {
            Request req;
            req.addr = item.cast<long>();
            req.type = type;
            req.coreid = coreid;
            req.is_first_command = true;
            req.callback = make_callback(type, callback, coreid);
            accepted.append(mem_->send(req));
        }
        return accepted;
    }

    // Bulk send over a contiguous (start, count, stride) range without
    // materializing the address list in Python.
    py::list send_range(long start, long count, long stride,
                        Request::Type type, int coreid, py::object callback) {
        py::list accepted;
        long addr = start;
        for (long i = 0; i < count; ++i, addr += stride) {
            Request req;
            req.addr = addr;
            req.type = type;
            req.coreid = coreid;
            req.is_first_command = true;
            req.callback = make_callback(type, callback, coreid);
            accepted.append(mem_->send(req));
        }
        return accepted;
    }

    py::list drain_completed() {
        py::list out;
        while (!completed_.empty()) {
            CompletionEvent &e = completed_.front();
            out.append(py::make_tuple(e.addr, e.type, e.arrive, e.depart,
                                      e.core_id, e.callback));
            completed_.pop_front();
        }
        return out;
    }

    // Bulk simulation: tick many cycles in C++ and hand the completion
    // events back to Python in one call, avoiding per-cycle Python overhead.
    py::tuple run(int cycles) {
        for (int i = 0; i < cycles; ++i)
            mem_->tick();
        return py::make_tuple(cycles, drain_completed());
    }

    py::tuple run_until_idle(long max_cycles) {
        long cycles = 0;
        while (cycles < max_cycles && mem_->pending_requests() > 0) {
            mem_->tick();
            ++cycles;
        }
        return py::make_tuple(cycles, drain_completed());
    }

    void finish() { mem_->finish(); }

    int pending() const { return mem_->pending_requests(); }

    double tCK() const { return tck_; }

    void set_high_writeq_watermark(float wm) {
        mem_->set_high_writeq_watermark(wm);
    }

    void set_low_writeq_watermark(float wm) {
        mem_->set_low_writeq_watermark(wm);
    }

private:
    struct CompletionEvent {
        long addr;
        int type;
        long arrive;
        long depart;
        int core_id;
        py::object callback;
    };

    std::deque<CompletionEvent> completed_;
    long completed_count_ = 0;
    std::pair<size_t, size_t> stats_range_{0, 0};

    static std::set<PyMemorySystem *> live_;

    static MemoryBase *create_memory(const Config &config, int cacheline,
                                     const std::string &std_name) {
        static const std::map<std::string,
                              std::function<MemoryBase *(const Config &, int)>>
            name_to_func = {
                {"DDR3", &MemoryFactory<DDR3>::create},
                {"DDR4", &MemoryFactory<DDR4>::create},
                {"LPDDR3", &MemoryFactory<LPDDR3>::create},
                {"LPDDR4", &MemoryFactory<LPDDR4>::create},
                {"GDDR5", &MemoryFactory<GDDR5>::create},
                {"WideIO", &MemoryFactory<WideIO>::create},
                {"WideIO2", &MemoryFactory<WideIO2>::create},
                {"HBM", &MemoryFactory<HBM>::create},
                {"SALP-1", &MemoryFactory<SALP>::create},
                {"SALP-2", &MemoryFactory<SALP>::create},
                {"SALP-MASA", &MemoryFactory<SALP>::create},
        };
        return name_to_func.at(std_name)(config, cacheline);
    }

    MemoryBase *mem_;
    double tck_;
};

std::set<PyMemorySystem *> PyMemorySystem::live_;

namespace {

PyMemorySystem *sole_live_instance() {
    PyMemorySystem *found = nullptr;
    for (PyMemorySystem *inst : PyMemorySystem::live_instances()) {
        if (found)
            throw std::runtime_error(
                "get_stats()/reset_stats() require exactly one live "
                "MemorySystem; call the method on an instance instead");
        found = inst;
    }
    if (!found)
        throw std::runtime_error(
            "no live MemorySystem; create one before reading stats");
    return found;
}

}  // namespace

PYBIND11_MODULE(_core, m) {
    m.doc() = "Python bindings for Ramulator DRAM simulator";

    py::enum_<Request::Type>(m, "RequestType")
        .value("READ", Request::Type::READ)
        .value("WRITE", Request::Type::WRITE)
        .value("REFRESH", Request::Type::REFRESH)
        .value("POWERDOWN", Request::Type::POWERDOWN)
        .value("SELFREFRESH", Request::Type::SELFREFRESH)
        .value("EXTENSION", Request::Type::EXTENSION)
        .export_values();

    py::class_<Config>(m, "Config")
        .def(py::init<>())
        .def(py::init<const std::string &>(), py::arg("config_file"))
        .def("add", &Config::add, py::arg("name"), py::arg("value"))
        .def("contains", &Config::contains, py::arg("name"))
        .def("set_core_num", &Config::set_core_num, py::arg("num"))
        .def("__getitem__", [](const Config &c, const std::string &name) {
            return c[name];
        })
        .def("__contains__", &Config::contains);

    py::class_<PyMemorySystem>(m, "MemorySystem")
        .def(py::init<Config, int, int>(),
             py::arg("config"), py::arg("cacheline") = 64,
             py::arg("num_cores") = 1)
        .def("tick", &PyMemorySystem::tick)
        .def("drain_completed", &PyMemorySystem::drain_completed)
        .def("run", &PyMemorySystem::run, py::arg("cycles"))
        .def("run_until_idle", &PyMemorySystem::run_until_idle,
             py::arg("max_cycles") = 1000000)
        .def("send", &PyMemorySystem::send,
             py::arg("addr"), py::arg("type"),
             py::arg("core_id") = 0, py::arg("callback") = py::none())
        .def("send_batch", &PyMemorySystem::send_batch,
             py::arg("addrs"), py::arg("type"),
             py::arg("core_id") = 0, py::arg("callback") = py::none())
        .def("send_range", &PyMemorySystem::send_range,
             py::arg("start"), py::arg("count"), py::arg("stride"),
             py::arg("type"), py::arg("core_id") = 0,
             py::arg("callback") = py::none())
        .def("drive", &PyMemorySystem::drive,
             py::arg("addrs"), py::arg("queue_depth") = 32,
             py::arg("batch") = 100,
             py::arg("max_cycles") = 1000000,
             py::arg("callback") = py::none())
        .def("drive_range", &PyMemorySystem::drive_range,
             py::arg("start"), py::arg("count"), py::arg("stride"),
             py::arg("queue_depth") = 32,
             py::arg("batch") = 100,
             py::arg("max_cycles") = 1000000,
             py::arg("callback") = py::none())
        .def("finish", &PyMemorySystem::finish)
        .def("set_high_writeq_watermark",
             &PyMemorySystem::set_high_writeq_watermark, py::arg("watermark"))
        .def("set_low_writeq_watermark",
             &PyMemorySystem::set_low_writeq_watermark, py::arg("watermark"))
        .def_property_readonly("tck", &PyMemorySystem::tCK)
        .def_property_readonly("pending", &PyMemorySystem::pending)
        .def("get_stats", &PyMemorySystem::get_stats,
             "Return this memory system's statistics as a {name: value} dict.")
        .def("reset_stats", &PyMemorySystem::reset_stats,
             "Reset this memory system's statistics to zero.");

    m.def("get_stats",
          []() { return sole_live_instance()->get_stats(); },
          "Return statistics of the single live MemorySystem as a {name: "
          "value} dict.\n\n"
          "Ramulator statistics are process-global, so this requires exactly "
          "one live MemorySystem; with several, use the per-instance method.")
        .def("reset_stats",
             []() { sole_live_instance()->reset_stats(); },
             "Reset the single live MemorySystem's statistics to zero.");
}

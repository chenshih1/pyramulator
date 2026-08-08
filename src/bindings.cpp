#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include <map>
#include <string>
#include <functional>

#include "Config.h"
#include "Request.h"
#include "MemoryFactory.h"
#include "Memory.h"
#include "DDR3.h"
#include "DDR4.h"
#include "LPDDR3.h"
#include "LPDDR4.h"
#include "GDDR5.h"
#include "WideIO.h"
#include "WideIO2.h"
#include "HBM.h"
#include "SALP.h"

namespace py = pybind11;
using namespace ramulator;

static std::map<std::string, std::function<MemoryBase *(const Config &, int)>>
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

class PyMemorySystem {
public:
    PyMemorySystem(Config config, int cacheline, int num_cores) {
        if (config.get_core_num() == 0)
            config.set_core_num(num_cores);
        const std::string &std_name = config["standard"];
        if (name_to_func.find(std_name) == name_to_func.end())
            throw std::invalid_argument("unsupported standard: " + std_name);
        mem_ = name_to_func[std_name](config, cacheline);
        tck_ = mem_->clk_ns();
    }

    ~PyMemorySystem() { delete mem_; }

    void tick() { mem_->tick(); }

    bool send(long addr, Request::Type type, int coreid,
              py::object callback) {
        Request req;
        req.addr = addr;
        req.type = type;
        req.coreid = coreid;
        req.is_first_command = true;

        if (!callback.is_none()) {
            req.callback = [callback](Request &r) {
                py::gil_scoped_acquire acquire;
                callback(r.addr, static_cast<int>(r.type),
                         r.arrive, r.depart);
            };
        } else {
            req.callback = [](Request &) {};
        }

        return mem_->send(req);
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
    MemoryBase *mem_;
    double tck_;
};

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
        .def("set", &Config::set, py::arg("name"), py::arg("value"))
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
        .def("send", &PyMemorySystem::send,
             py::arg("addr"), py::arg("type"),
             py::arg("core_id") = 0, py::arg("callback") = py::none())
        .def("finish", &PyMemorySystem::finish)
        .def("set_high_writeq_watermark",
             &PyMemorySystem::set_high_writeq_watermark, py::arg("watermark"))
        .def("set_low_writeq_watermark",
             &PyMemorySystem::set_low_writeq_watermark, py::arg("watermark"))
        .def_property_readonly("tck", &PyMemorySystem::tCK)
        .def_property_readonly("pending", &PyMemorySystem::pending);
}

pyramulator
===========

**pyramulator** is a discrete-event simulation (DES) framework for hardware
architecture, with a cycle-accurate DRAM timing model (Ramulator) embedded
as a Python component. Its kernel is a classic **event-scheduling** DES
with next-event time advance (Banks / Law-Kelton model): a future-event
list, deterministic simultaneous-event rules, and zero-delay delta
events.

Quick links
-----------

- :doc:`quickstart` — install and run your first simulation
- :doc:`api/sim` — the ``Simulator`` kernel
- :doc:`api/hardware` — ``Clock``, ``Component``, ``FIFO``, ``Pipe``
- :doc:`api/dram` — the ``Dram`` component
- :doc:`api/benchmark` — one-call benchmarks

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   api/sim
   api/hardware
   api/dram
   api/benchmark
   api/metrics
   api/workload
   api/configs
   examples

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

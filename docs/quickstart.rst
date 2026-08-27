Quick Start
===========

Install
-------

Build from source (requires Python >= 3.10 and a C++17 compiler):

.. code-block:: bash

   git clone --recurse-submodules https://github.com/chenshih1/pyramulator.git
   cd pyramulator
   pip install ".[dev]"

Run the test suite to confirm everything works:

.. code-block:: bash

   pytest

First simulation
----------------

.. code-block:: python

   from pyramulator import Simulator, Dram, Config

   sim = Simulator()
   dram = Dram(sim, Config(standard="DDR4", speed="DDR4_2400R",
                           org="DDR4_4Gb_x8"))

   completed = []
   dram.read(0x1000, callback=lambda info: completed.append(info))
   sim.run_until_idle()

   print(completed[0].latency)   # latency in DRAM clock cycles

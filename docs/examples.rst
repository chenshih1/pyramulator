Examples
========

The ``examples/`` directory contains runnable architecture models.

Pipe + FIFO + Dram
------------------

``examples/pipe_fifo_dram.py`` is the composition template: a 1 GHz copy
engine that wires :class:`~pyramulator.hardware.Pipe` and
:class:`~pyramulator.hardware.FIFO` to :class:`~pyramulator.dram.Dram`
(two clocks, consumer backpressure, no nested ``flush()``).

.. code-block:: bash

   python examples/pipe_fifo_dram.py

SpMM on HBM
-----------

``examples/spmm_hbm.py`` demonstrates a naive single-PE sparse-matrix
 dense-matrix multiply accelerator streaming from HBM.

.. code-block:: bash

   python examples/spmm_hbm.py [channels]

Vector Accelerator
------------------

``examples/accel_sim.py`` simulates a multi-lane vector accelerator with a
LOAD / COMPUTE / STORE pipeline per tile.

Examples
========

The ``examples/`` directory contains runnable architecture models.

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

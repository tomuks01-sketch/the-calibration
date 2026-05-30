"""Feature layers for the calibrated signal system (see SIGNAL_SPEC.md).

Each layer returns a plain dict carrying its values plus an ``available``
flag, a ``source``, and (where relevant) a ``timestamp``. Missing data is
always ``available: False`` with null values — never invented.
"""

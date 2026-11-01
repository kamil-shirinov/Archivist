"""P33: what Muse Spark Open costs, how fast it is and how often it answers empty, measured on
development pages only (results/openw_measure/REPORT.md). Not a result; it pre-registers nothing.

Everything here is new: no committed config, template or frozen path is edited. The scripts reach
the models only through archivist.models (registry -> cache -> budget -> backend), with a
recorder outermost and a thin shim in place of the committed backend, so that the calls are
capped and in the ledger as usual.
"""

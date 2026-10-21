"""Model-specific GeometryAdapter implementations.

Nothing is re-exported here: import a submodule (e.g. rt_mapping.adapters.da3_metric)
explicitly. Heavy frameworks (torch, model packages) are imported only when a
model is actually loaded, so importing rt_mapping stays light.
"""

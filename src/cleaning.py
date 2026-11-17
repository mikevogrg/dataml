"""Compatibility exports for the standard-library cleaning implementation."""
from .core import CleaningPipeline,hampel_flags,stuck_flags,impute,_iforest_flags

def range_flags(values,ch):
    lo,hi=__import__("src.config",fromlist=["PHYSICAL_RANGE"]).PHYSICAL_RANGE[ch]
    return [x is not None and (x<lo or x>hi) for x in values]

def build_features(rows,ch):
    from .core import _features
    vals=[r.get(ch) for r in rows]
    return _features(rows,ch,vals)

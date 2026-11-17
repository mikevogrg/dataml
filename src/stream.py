"""Causal online cleaner; no third-party dependencies."""
from .core import stream_clean
class StreamCleaner:
    def process(self,rows): return stream_clean(rows)
def run_stream(rows,cleaner=None): return stream_clean(rows)

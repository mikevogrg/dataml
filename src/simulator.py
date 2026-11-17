"""Synthetic sensor-network data generator (standard-library implementation)."""
from .core import generate
FAULT_TYPES=["spike","stuck","bias","drift","sentinel","missing","burst"]

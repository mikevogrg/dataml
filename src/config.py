"""Central configuration. Change numbers HERE, not inside the algorithms.

WHY: Every threshold below is a design decision you must be able to defend in
the M2 (Design) milestone. Keeping them in one place makes experiments and
ablations easy ("what if the Hampel window is 21?").
"""

CHANNELS = ["temperature", "humidity", "light", "voltage"]

# Physical plausibility limits (rule-based layer). Values outside are impossible.
PHYSICAL_RANGE = {
    "temperature": (-10.0, 50.0),   # deg C, indoor lab
    "humidity": (0.0, 100.0),       # % relative
    "light": (0.0, 2000.0),         # lux
    "voltage": (1.8, 3.3),          # V, 2xAA mote battery
}

SAMPLE_MINUTES = 5

# Hampel filter (robust outlier detector)
HAMPEL_WINDOW = 11          # samples (centered)
HAMPEL_NSIGMA = 4.0
# Local noise estimates from 11 points are unreliable; never let sigma fall below this
# multiple of the typical (median) sigma, or clean data gets flagged (see ERROR_LOG E-02)
HAMPEL_SIGMA_FLOOR = 1.0

# Stuck-at detector: this many identical consecutive readings is suspicious
STUCK_MIN_RUN = 8
# Light is legitimately 0 at night, so identical zeros are NOT a fault
STUCK_IGNORE_VALUE = {"light": 0.0}

# Spatial-consistency detector (slow faults: bias/drift)
SPATIAL_WINDOW = 15
SPATIAL_NSIGMA = 5.0

# ML layer
LONG_WINDOW = 61            # for slow faults (bias / drift)
IFOREST_TREES = 200
IFOREST_CONTAMINATION = 0.03   # fraction of points the model is allowed to flag
RANDOM_STATE = 42

# Imputation
SHORT_GAP = 3               # gaps <= this use linear interpolation, longer use spatial model

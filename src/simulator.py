"""Synthetic IoT sensor-network simulator with ground-truth fault labels.

WHY a simulator? Real datasets (Intel Lab) have no per-point labels, so you
cannot measure precision/recall. Here we know exactly which points are faulty
and what the true value was, so we can *score* the cleaning model honestly.
Fault taxonomy follows de Bruijn et al. (2016): random(spike), stuck/malfunction,
bias, drift, plus missing data and out-of-range sentinel values (seen in Intel Lab).
"""
import numpy as np
import pandas as pd
from .config import CHANNELS, SAMPLE_MINUTES

FAULT_TYPES = ["spike", "stuck", "bias", "drift", "sentinel", "missing"]


def _clean_signals(n_motes, n_steps, rng):
    t = np.arange(n_steps) * SAMPLE_MINUTES / 60.0            # hours
    day = 2 * np.pi * t / 24.0
    # shared building-level signals => neighbouring motes correlate (spatial redundancy)
    base_t = 21 + 3.0 * np.sin(day - 1.5)
    base_t = base_t + np.cumsum(rng.normal(0, 0.02, n_steps))      # slow weather wander
    sig = {}
    for m in range(1, n_motes + 1):
        off = rng.normal(0, 0.6)
        ar = np.zeros(n_steps)
        for i in range(1, n_steps):
            ar[i] = 0.9 * ar[i - 1] + rng.normal(0, 0.06)
        temp = base_t + off + ar
        hum = 45 - 1.6 * (temp - 21) + rng.normal(0, 0.25, n_steps) + rng.normal(0, 1)
        light = np.clip(450 * np.sin(day - np.pi / 2 + 0.2) + 120, 0, None)
        light = np.where(light > 0, light * rng.uniform(0.7, 1.1) + rng.normal(0, 8, n_steps), 0.0)
        light = np.clip(light, 0, None)
        volt = 2.75 - 0.0004 * t + rng.normal(0, 0.004, n_steps)
        sig[m] = dict(temperature=temp, humidity=hum, light=light, voltage=volt)
    return sig


def _inject(clean, ch, rng, rate):
    """Return (faulty_values, labels) for ONE mote/channel."""
    n = len(clean)
    x = clean.copy()
    lab = np.array([""] * n, dtype=object)
    scale = np.nanstd(clean) + 1e-9
    budget = int(n * rate)            # rate = target FRACTION OF POINTS that are faulty
    free = np.ones(n, dtype=bool)

    def take(length):
        for _ in range(20):
            s = rng.integers(0, n - length)
            if free[max(0, s - 3): s + length + 3].all():
                free[s: s + length] = False
                return s
        return None

    for _ in range(10000):
        if (~free).sum() >= budget:
            break
        kind = rng.choice(FAULT_TYPES, p=[0.35, 0.15, 0.10, 0.10, 0.10, 0.20])
        if kind == "spike":
            s = take(1)
            if s is None: continue
            x[s] += rng.choice([-1, 1]) * rng.uniform(6, 14) * scale
        elif kind == "stuck":
            L = int(rng.integers(12, 40)); s = take(L)
            if s is None: continue
            x[s:s + L] = x[s]
        elif kind == "bias":
            L = int(rng.integers(60, 150)); s = take(L)
            if s is None: continue
            x[s:s + L] += rng.choice([-1, 1]) * rng.uniform(2.5, 4) * scale
        elif kind == "drift":
            L = int(rng.integers(100, 250)); s = take(L)
            if s is None: continue
            x[s:s + L] += np.linspace(0, rng.choice([-1, 1]) * rng.uniform(3, 5) * scale, L)
        elif kind == "sentinel":
            s = take(1)
            if s is None: continue
            x[s] = {"temperature": 122.153, "humidity": -3.9, "light": 54612.0, "voltage": 0.0}[ch]
        elif kind == "missing":
            L = int(rng.integers(1, 20)); s = take(L)
            if s is None: continue
            x[s:s + L] = np.nan
        else:
            continue
        lab[s: s + (L if kind not in ("spike", "sentinel") else 1)] = kind
    return x, lab


def _add_bursts(x, lab, n_bursts, rng):
    """NOVEL fault (no dedicated rule): noise variance suddenly x8 for 20-60 samples.
    Used to test whether the ML layer catches fault types nobody wrote a rule for."""
    n = len(x); noise = np.nanstd(np.diff(x)) + 1e-9
    for _ in range(n_bursts):
        L = int(rng.integers(20, 60)); s = int(rng.integers(0, n - L))
        if (lab[s:s + L] != "").any():
            continue
        x[s:s + L] += rng.normal(0, 8 * noise, L); lab[s:s + L] = "burst"
    return x, lab


def generate(n_motes=8, days=7, fault_rate=0.08, seed=7, bursts=0):
    """Return a long dataframe: one row per (timestamp, mote)."""
    rng = np.random.default_rng(seed)
    n_steps = int(days * 24 * 60 / SAMPLE_MINUTES)
    clean = _clean_signals(n_motes, n_steps, rng)
    brng = np.random.default_rng(seed + 1000)          # separate stream: default data unchanged when bursts=0
    ts = pd.date_range("2026-03-01", periods=n_steps, freq=f"{SAMPLE_MINUTES}min")
    frames = []
    for m, d in clean.items():
        df = pd.DataFrame({"timestamp": ts, "mote_id": m})
        for ch in CHANNELS:
            x, lab = _inject(d[ch], ch, rng, fault_rate)
            if bursts:
                x, lab = _add_bursts(x, lab, bursts, brng)
            df[ch] = x
            df[f"true_{ch}"] = d[ch]
            df[f"fault_{ch}"] = lab
        frames.append(df)
    return pd.concat(frames, ignore_index=True).sort_values(["timestamp", "mote_id"]).reset_index(drop=True)


if __name__ == "__main__":
    df = generate()
    df.to_csv("data/synthetic_iot.csv", index=False)
    print(df.shape)

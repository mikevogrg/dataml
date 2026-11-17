"""Hybrid IoT data-cleaning pipeline: rules + robust statistics + spatial check + Isolation Forest + imputation.

Layers (cheap & explainable first, ML last):
  1. Range rule      - physically impossible values (sentinels like 122.15 C)
  2. Hampel filter   - isolated spikes (robust to outliers, unlike mean/std)
  3. Stuck-at rule   - sensor frozen on one value
  4. Spatial check   - a mote disagrees with its neighbours for a sustained stretch (bias/drift)
  5. Isolation Forest- learns "normal" from engineered features (no labels needed)
  6. Imputation      - short gaps: linear; long gaps: neighbour-based spatial model
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler
from . import config as C


# ---------- 0. structure ----------
def regularise(df):
    """Sort, drop duplicate (timestamp, mote) rows, and reindex onto a regular grid
    so dropped packets become explicit NaN rows instead of silently missing."""
    df = df.sort_values(["mote_id", "timestamp"]).drop_duplicates(["mote_id", "timestamp"], keep="first")
    parts = []
    for m, g in df.groupby("mote_id"):
        idx = pd.date_range(g.timestamp.min(), g.timestamp.max(), freq=f"{C.SAMPLE_MINUTES}min")
        g = g.set_index("timestamp").reindex(idx)
        g["mote_id"] = m
        g.index.name = "timestamp"
        parts.append(g.reset_index())
    return pd.concat(parts, ignore_index=True)


# ---------- 1-3. rule & statistical detectors (all return boolean arrays) ----------
def range_flags(x, ch):
    lo, hi = C.PHYSICAL_RANGE[ch]
    return ((x < lo) | (x > hi)).to_numpy()


def _window_mad(w):
    return np.median(np.abs(w - np.median(w)))


def hampel_flags(x, window=C.HAMPEL_WINDOW, nsigma=C.HAMPEL_NSIGMA):
    """Flag points far from the window median, measured in robust sigmas.
    sigma = 1.4826 * MAD of the WINDOW VALUES around the window median (classic Hampel)."""
    med = x.rolling(window, center=True, min_periods=3).median()
    mad = x.rolling(window, center=True, min_periods=3).apply(_window_mad, raw=True)
    sigma = 1.4826 * mad
    pos = sigma[sigma > 0]
    floor = pos.median() * C.HAMPEL_SIGMA_FLOOR if len(pos) else 1e-6   # ignore all-zero windows (e.g. night light)
    sigma = sigma.clip(lower=max(floor, 1e-6))
    return ((x - med).abs() > nsigma * sigma).fillna(False).to_numpy()


def stuck_flags(x, ch, min_run=C.STUCK_MIN_RUN):
    same = x.diff().abs().fillna(1) == 0
    grp = (~same).cumsum()
    run = same.groupby(grp).transform("sum") + 1       # run length incl. first element
    flag = (run >= min_run) & x.notna()
    ign = C.STUCK_IGNORE_VALUE.get(ch)
    if ign is not None:
        flag &= x != ign
    return flag.to_numpy()



def spatial_residual(df, ch, x=None):
    """How much does a mote disagree with its neighbours (median across motes at the same time)?
    Temperature/humidity/voltage: additive difference, minus the mote's own typical offset.
    Light: each mote has its own GAIN, estimated from daytime only (night is all zeros),
    so r = (x - gain * neighbours) / (neighbours + 50)."""
    x = df[ch] if x is None else x
    cross = x.groupby(df["timestamp"]).transform("median")
    if ch == "light":
        gain = (x / cross).where(cross > 100).groupby(df["mote_id"]).transform("median")
        return (x - gain * cross) / (cross + 50.0)
    r = x - cross
    return r - r.groupby(df["mote_id"]).transform("median")


def spatial_flags(df, ch, masked):
    """Detects slow faults (bias, drift) that a point-wise filter cannot see: the mote
    disagrees with its neighbours for a sustained stretch. Smoothing over a window
    separates a sustained disagreement from random noise."""
    r = spatial_residual(df, ch, masked)
    out = np.zeros(len(df), bool)
    pos = {i: p for p, i in enumerate(df.index)}
    for m, idx in df.groupby("mote_id").groups.items():
        s = r.loc[idx]
        sm = s.rolling(C.SPATIAL_WINDOW, center=True, min_periods=C.SPATIAL_WINDOW // 2).median()
        dev = np.abs(sm - np.nanmedian(sm))
        dev = dev[dev > 0]                       # exact zeros (e.g. night light) carry no noise info
        sigma = max(1.4826 * np.nanmedian(dev), 1e-9) if len(dev) else 1e-9
        out[[pos[i] for i in idx]] = (sm.abs() > C.SPATIAL_NSIGMA * sigma).fillna(False).to_numpy()
    return out


# ---------- 4. ML layer ----------
def build_features(df, ch):
    """Per-point features. Computed on a copy with impossible values masked, so
    sentinels don't poison the rolling statistics."""
    d = df[["timestamp", "mote_id", ch]].copy()
    d.loc[range_flags(d[ch], ch), ch] = np.nan
    feats = []
    for m, g in d.groupby("mote_id", sort=False):
        x = g[ch]
        med_s = x.rolling(C.HAMPEL_WINDOW, center=True, min_periods=3).median()
        med_l = x.rolling(C.LONG_WINDOW, center=True, min_periods=10).median()
        f = pd.DataFrame(index=g.index)
        f["res_short"] = x - med_s
        f["res_long"] = x - med_l
        f["d1"] = x.diff()
        f["rstd"] = x.rolling(C.HAMPEL_WINDOW, center=True, min_periods=3).std()
        feats.append(f)
    f = pd.concat(feats).loc[d.index]
    # spatial feature: deviation from the median of ALL motes at the same timestamp
    f["spatial"] = spatial_residual(d, ch)
    f["spatial_smooth"] = f["spatial"].groupby(d["mote_id"]).transform(
        lambda s: s.rolling(C.SPATIAL_WINDOW, center=True, min_periods=C.SPATIAL_WINDOW // 2).median())
    return f


class MLDetector:
    """Isolation Forest per channel (unsupervised: needs NO labels)."""

    def __init__(self):
        self.models = {}

    def fit_predict(self, df, ch):
        f = build_features(df, ch)
        ok = f.notna().all(axis=1) & df[ch].notna() & ~pd.Series(range_flags(df[ch], ch), index=df.index)
        X = RobustScaler().fit_transform(f[ok])
        iso = IsolationForest(n_estimators=C.IFOREST_TREES, contamination=C.IFOREST_CONTAMINATION,
                              random_state=C.RANDOM_STATE, n_jobs=-1)
        pred = iso.fit_predict(X) == -1
        flags = pd.Series(False, index=df.index)
        flags[ok] = pred
        self.models[ch] = iso
        return flags.to_numpy()


# ---------- 5. imputation ----------
def impute(df, ch, bad):
    """Replace flagged/missing values. Short gaps: linear interpolation.
    Long gaps: neighbour-based estimate = cross-mote median + this mote's typical offset."""
    x = df[ch].copy()
    x[bad] = np.nan
    out = x.copy()
    lin = pd.Series(np.nan, index=df.index)
    spatial = pd.Series(np.nan, index=df.index)
    for m, idx in df.groupby("mote_id").groups.items():
        xs = x.loc[idx]
        lin.loc[idx] = xs.interpolate(limit_area="inside", limit_direction="both")
    # clean-values-only cross-mote median, aligned by timestamp
    cross = x.groupby(df["timestamp"]).transform("median")
    offset = (x - cross).groupby(df["mote_id"]).transform("median")
    spatial = cross + offset
    # gap length of each NaN run, per mote
    gap_len = pd.Series(0, index=df.index)
    for m, idx in df.groupby("mote_id").groups.items():
        isn = x.loc[idx].isna()
        grp = (~isn).cumsum()
        gap_len.loc[idx] = isn.groupby(grp).transform("sum").where(isn, 0)
    use_spatial = (gap_len > C.SHORT_GAP) & spatial.notna()
    filled = lin.where(~use_spatial, spatial)
    filled = filled.fillna(spatial)           # leading/trailing NaNs
    out = x.where(x.notna(), filled)
    return out


# ---------- orchestration ----------
class CleaningPipeline:
    METHODS = ["range", "hampel", "stuck", "spatial", "iforest"]

    def __init__(self, use=("range", "hampel", "stuck", "spatial", "iforest")):
        self.use = tuple(use)

    def run(self, raw):
        df = regularise(raw)
        cleaned = df.copy()
        report = {}
        flags_all = {}
        for ch in C.CHANNELS:
            comp = {}
            if "range" in self.use:
                comp["range"] = range_flags(df[ch], ch)
            masked = df[ch].where(~comp.get("range", np.zeros(len(df), bool)))
            if "hampel" in self.use:
                comp["hampel"] = \
                    self._per_mote(df, masked, hampel_flags)
            if "stuck" in self.use:
                comp["stuck"] = self._per_mote(df, masked, lambda s: stuck_flags(s, ch))
            if "spatial" in self.use:
                comp["spatial"] = spatial_flags(df, ch, masked)
            if "iforest" in self.use:
                comp["iforest"] = MLDetector().fit_predict(df, ch)
            bad = np.zeros(len(df), bool)
            for v in comp.values():
                bad |= v
            flags_all[ch] = bad
            flags_all[f"{ch}__parts"] = comp
            cleaned[ch] = impute(df, ch, pd.Series(bad, index=df.index) | df[ch].isna())
            report[ch] = {"flagged": int(bad.sum()), "missing": int(df[ch].isna().sum()),
                          **{k: int(v.sum()) for k, v in comp.items()}}
        return df, cleaned, flags_all, report

    @staticmethod
    def _per_mote(df, series, fn):
        out = np.zeros(len(df), bool)
        pos = {i: p for p, i in enumerate(df.index)}
        for m, idx in df.groupby("mote_id").groups.items():
            res = fn(series.loc[idx])
            out[[pos[i] for i in idx]] = res
        return out

"""Scoring against ground truth (only possible on the simulator)."""
import numpy as np
import pandas as pd
from . import config as C
from .simulator import FAULT_TYPES


def detection_scores(df, flags, channels=C.CHANNELS):
    """Precision / recall / F1 for detecting *non-missing* faults (missing values are
    trivially known, so including them would inflate recall)."""
    rows = []
    for ch in channels:
        lab = df[f"fault_{ch}"].fillna("")
        truth = (lab != "") & (lab != "missing")
        pred = flags[ch] & df[ch].notna().to_numpy()
        tp = int((truth & pred).sum()); fp = int((~truth & pred).sum()); fn = int((truth & ~pred).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        rows.append(dict(channel=ch, precision=p, recall=r, f1=f1, tp=tp, fp=fp, fn=fn))
    return pd.DataFrame(rows)


def recall_by_fault(df, flags, channels=C.CHANNELS):
    out = {}
    for ft in FAULT_TYPES:
        if ft == "missing":
            continue
        hit = tot = 0
        for ch in channels:
            m = (df[f"fault_{ch}"].fillna("") == ft).to_numpy()
            tot += int(m.sum()); hit += int((flags[ch] & m).sum())
        out[ft] = hit / tot if tot else np.nan
    return pd.Series(out)


def value_rmse(df, cleaned, channels=C.CHANNELS):
    """RMSE of values vs. the hidden true signal: raw vs cleaned."""
    rows = []
    for ch in channels:
        truth = df[f"true_{ch}"]
        raw = df[ch].where(df[ch].notna(), np.nan)
        # raw with NaN filled by linear interpolation = fairest 'do nothing smart' baseline
        raw_f = raw.groupby(df.mote_id).transform(lambda s: s.interpolate(limit_direction="both"))
        rmse = lambda a: float(np.sqrt(np.nanmean((a - truth) ** 2)))
        rows.append(dict(channel=ch, raw_rmse=rmse(raw_f), cleaned_rmse=rmse(cleaned[ch]),
                         raw_mae=float(np.nanmean(np.abs(raw_f - truth))),
                         cleaned_mae=float(np.nanmean(np.abs(cleaned[ch] - truth)))))
    r = pd.DataFrame(rows)
    r["improvement_%"] = 100 * (1 - r.cleaned_rmse / r.raw_rmse)
    return r

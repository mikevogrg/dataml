"""Online (causal) cleaner: processes one TIME TICK at a time, like an edge gateway would.

It only ever looks at the past, so it can run live. The Isolation Forest is NOT included
here: its features use centred windows (they peek into the future). It stays in the
offline/batch layer, which is retrained periodically (see docs/M2_DESIGN.md).

Layers: range rule -> trailing Hampel -> stuck-at run -> spatial consistency (vs neighbours).
"""
from collections import deque
import numpy as np
from . import config as C

WARMUP_TICKS = 40
MIN_NOISE_SAMPLES = 60


class _ChanState:
    def __init__(self):
        self.good = deque(maxlen=C.HAMPEL_WINDOW)        # recent in-range readings (accepted or not)
        self.sigmas = deque(maxlen=500)                   # history of window sigmas (for the floor)
        self.res = deque(maxlen=C.SPATIAL_WINDOW)         # recent spatial residuals
        self.sm_hist = deque(maxlen=1000)
        self.same_run = 0
        self.last = None
        self.offset = None                                # additive offset or light gain (running mean -> EWMA)
        self.n_off = 0
        self.last_good = None


class StreamCleaner:
    ALPHA = 0.02

    def __init__(self):
        self.state = {}
        self.tick = 0

    def _st(self, mote, ch):
        return self.state.setdefault((mote, ch), _ChanState())

    # ---- single-reading checks -------------------------------------------------
    @staticmethod
    def _in_range(x, ch):
        lo, hi = C.PHYSICAL_RANGE[ch]
        return lo <= x <= hi

    def _hampel(self, s, x):
        if len(s.good) < 5:
            return False
        w = np.asarray(s.good)
        med = np.median(w)
        sig = 1.4826 * np.median(np.abs(w - med))
        if sig > 0:
            s.sigmas.append(sig)
        pos = [v for v in s.sigmas if v > 0]
        floor = np.median(pos) * C.HAMPEL_SIGMA_FLOOR if pos else 1e-6
        return abs(x - med) > C.HAMPEL_NSIGMA * max(sig, floor, 1e-6)

    def _stuck(self, s, x, ch):
        s.same_run = s.same_run + 1 if (s.last is not None and x == s.last) else 1
        s.last = x
        ign = C.STUCK_IGNORE_VALUE.get(ch)
        return s.same_run >= C.STUCK_MIN_RUN and not (ign is not None and x == ign)

    # ---- one tick ---------------------------------------------------------------
    def process_tick(self, ts, readings):
        """readings: {mote_id: {channel: value or NaN}} -> list of result dicts."""
        self.tick += 1
        out = []
        for ch in C.CHANNELS:
            vals = {m: r.get(ch, np.nan) for m, r in readings.items()}
            valid = {m: v for m, v in vals.items() if v is not None and np.isfinite(v) and self._in_range(v, ch)}
            cross = float(np.median(list(valid.values()))) if valid else np.nan
            for m, x in vals.items():
                s = self._st(m, ch)
                reasons = []
                missing = x is None or not np.isfinite(x)
                if missing:
                    reasons.append("missing")
                elif not self._in_range(x, ch):
                    reasons.append("range")
                else:
                    if self._hampel(s, x): reasons.append("hampel")
                    s.good.append(x)      # Hampel memory = ALL in-range readings (see ERROR_LOG E-05)
                    if self._stuck(s, x, ch): reasons.append("stuck")
                    r = self._spatial_residual(s, x, cross, ch)
                    if r is not None and self._spatial(s, r): reasons.append("spatial")
                    self._update_offset(s, x, cross, ch, accepted=not reasons)
                bad = bool(reasons)
                if not bad:
                    s.last_good = x
                    clean = x
                else:
                    clean = self._repair(s, m, cross, ch)
                out.append(dict(timestamp=ts, mote_id=m, channel=ch, raw=None if missing else x,
                                cleaned=clean, flagged=bad and reasons != ["missing"], missing=missing,
                                reasons=reasons))
        return out

    # ---- spatial layer ----------------------------------------------------------
    def _spatial_residual(self, s, x, cross, ch):
        if not np.isfinite(cross) or s.offset is None:
            return None
        if ch == "light":
            return (x - s.offset * cross) / (cross + 50.0)
        return x - cross - s.offset

    def _spatial(self, s, r):
        s.res.append(r)
        if self.tick < WARMUP_TICKS or len(s.res) < C.SPATIAL_WINDOW // 2:
            return False
        sm = float(np.median(s.res))
        s.sm_hist.append(sm)
        h = np.asarray(s.sm_hist)
        dev = np.abs(h - np.median(h)); dev = dev[dev > 0]
        if len(dev) < MIN_NOISE_SAMPLES or s.n_off < MIN_NOISE_SAMPLES:   # cold start: not enough evidence yet
            return False
        sigma = max(1.4826 * np.median(dev), 1e-9) if len(dev) else 1e-9
        return abs(sm) > C.SPATIAL_NSIGMA * sigma

    def _update_offset(self, s, x, cross, ch, accepted):
        if not np.isfinite(cross):
            return
        if ch == "light":
            if cross <= 100: return
            target = x / cross
        else:
            target = x - cross
        if s.offset is None:
            s.offset, s.n_off = target, 1
        elif accepted:
            s.n_off += 1
            a = max(self.ALPHA, 1.0 / s.n_off)      # running mean at first, then slow EWMA
            s.offset = (1 - a) * s.offset + a * target

    # ---- repair -------------------------------------------------------------------
    def _repair(self, s, m, cross, ch):
        if np.isfinite(cross) and s.offset is not None:
            est = s.offset * cross if ch == "light" else cross + s.offset
            return float(est)
        return s.last_good if s.last_good is not None else (np.nan if not np.isfinite(cross) else cross)


def run_stream(df, cleaner=None):
    """Feed a long dataframe (timestamp, mote_id, channels...) tick by tick. Returns a dataframe of results."""
    import pandas as pd
    cleaner = cleaner or StreamCleaner()
    rows = []
    for ts, g in df.groupby("timestamp", sort=True):
        readings = {int(r.mote_id): {c: getattr(r, c) for c in C.CHANNELS} for r in g.itertuples()}
        rows.extend(cleaner.process_tick(ts, readings))
    return pd.DataFrame(rows)

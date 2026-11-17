# ERROR_LOG - bugs found while building, and how to test each fix

Format: symptom -> cause -> fix -> how YOU can test it.

## E-01  Simulator made 25-30% of all points faulty
- **Symptom:** Temperature/humidity "faulty share" printed 0.25-0.31; detectors looked terrible.
- **Cause:** `fault_rate` counted *events*, but bias/drift events last 60-250 samples each, so a "1% rate" corrupted a quarter of the data. Real sensors are mostly healthy.
- **Fix:** `fault_rate` is now a budget of *points* (default 8%, measured ~10%). `src/simulator.py::_inject`.
- **Test:** `python -c "from src.simulator import generate; d=generate(); print((d.fault_temperature!='').mean())"` -> about 0.10.

## E-02  Hampel filter flagged ~10% of clean data (false positives far from any fault)
- **Symptom:** Hampel precision 0.36; 1,900 false alarms on temperature, none near real faults.
- **Cause (two layers):** (a) I computed the noise scale as a rolling median of residuals against each point's *own* median. In smooth data those residuals are almost all 0, so sigma ~ 0.003 and everything looked like an outlier. Correct Hampel: MAD of the *window values* around the *window median*. (b) The sigma floor was only 0.5x typical, i.e. a ~2 sigma threshold.
- **Fix:** `hampel_flags` now uses `_window_mad`; floor = 1.0x median of the *positive* sigmas (`HAMPEL_SIGMA_FLOOR`).
- **Test:** `pytest tests -k hampel` (clean noise -> <=5 flags; a +5 spike -> flagged).

## E-03  Light channel: thousands of false alarms every night
- **Symptom:** Light precision 0.35; FPs clustered at hours 18-03 (spatial detector).
- **Cause:** Motes have different light *gain*. I removed each mote's offset using a median over day+night, but night is all zeros, so the offset was wrong for one half of the day.
- **Fix:** Light uses a multiplicative gain estimated on daytime only: `(x - gain*neighbours)/(neighbours+50)` in `spatial_residual`.
- **Test:** `results/report.md` light precision should be > 0.85; false alarms no longer cluster at night.

## E-04  Spatial detector's noise estimate collapsed to 0 on light
- **Symptom:** After E-03, light FPs got *worse* (2,542).
- **Cause:** Half of the residuals are exactly 0 at night, so the MAD (a median) was 0 -> any tiny deviation = "5 sigma".
- **Fix:** Estimate sigma only from non-zero deviations (`spatial_flags`). Same lesson as E-02: robust statistics fail when >50% of values are identical.
- **Test:** light precision 0.89, recall 0.95 in `results/report.md`.

## E-05  Online Hampel flagged ~60% of all readings
- **Symptom:** `StreamCleaner` recall was fine (0.9) but precision 0.14-0.47; Hampel alone flagged 9,800 of 16,128 temperature readings.
- **Cause:** Flagged values were never added to the detector's memory window. After a long fault (bias, stuck, drift: 60-250 samples) the window held stale values from before the fault, so *every* later reading looked far from it, was flagged, and was again kept out of the window. A self-reinforcing loop.
- **Fix:** The Hampel window now stores every in-range reading, accepted or not (`src/stream.py`, comment "see ERROR_LOG E-05"). Batch code never had this bug because it uses all values.
- **Test:** `python demo.py --stream` should print repairs for real faults, not a flood; `tests/test_pipeline.py::test_stream_cleaner_is_accurate_and_causal` needs precision > 0.7.

## E-06  Online cleaner: many false alarms on day 1 of the light channel
- **Symptom:** After E-05, light precision was 0.59; 678 of 787 spatial false positives fell on the first day.
- **Cause:** Cold start. The simulation begins at night, so the per-mote light gain and the noise scale were estimated from almost no daytime data (one noisy sample set the gain).
- **Fix:** Offsets use a running mean at first, then a slow EWMA (`max(ALPHA, 1/n)`); the spatial layer may not flag until it has 60 non-zero noise samples (`MIN_NOISE_SAMPLES`).
- **Test:** online light F1 0.86; side-effect to know: very short runs (2 days) still flag more than long ones because of this warm-up.

## E-07  Documentation drift (caught in review)
- **Symptom:** The header comment of `src/cleaning.py` still listed four layers after the spatial layer was added.
- **Fix:** Docstring updated. Rule: when a layer is added, update the docstring, README table and docs/M2_DESIGN.md in the same change.

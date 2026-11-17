# AI Data Cleaning for IoT Sensor Streams

A layered, explainable system that detects and repairs faulty readings in multi-sensor IoT data (temperature, humidity, light, voltage). Raw readings are retained in a SQLite audit database with cleaning reasons. The simulator supplies labelled ground truth for evaluation.

## Compatibility repair

The application now runs on the Python standard library only. This removes NumPy, pandas, scikit-learn and Matplotlib binary dependencies that were blocked by Windows Smart App Control. No security policy changes and no package installation are required.

The offline path retains the five detection layers: range, Hampel, stuck-at, spatial consistency and a pure-Python Isolation Forest. The online path remains causal and excludes Isolation Forest. Short gaps use linear interpolation; longer gaps use a cross-sensor estimate. The Isolation Forest implementation is algorithmically equivalent in purpose, but its random trees and scores can differ from scikit-learn; previously reported metrics must not be presented as newly reproduced results until experiments are rerun.

## Quick start (PowerShell)

Run from the repository root:

```powershell
python --version
python -m unittest discover -s tests -v
python demo.py
python main.py simulate --out data/demo.csv
python main.py clean --input data/demo.csv --mode batch --db results/audit.db
python main.py report --db results/audit.db
python main.py explain --db results/audit.db --mote 3 --channel humidity
python main.py clean --input data/demo.csv --mode stream --db results/stream_audit.db
python demo.py --stream
python demo.py --intel data.txt.gz
python experiments.py
python experiments_novel.py
```

No `pip install` step is needed.

## Architecture

```
CSV / stream -> schema validation, ordering and regular five-minute grid
  -> ONLINE cleaner: range | Hampel | stuck | spatial (past data only)
  -> OFFLINE cleaner: same layers + Isolation Forest (batch context)
  -> repair: linear interpolation for short gaps, cross-sensor estimate for long gaps
  -> SQLite audit store: raw + cleaned + flag + reason
  -> reports and explanation
```

Thresholds remain centralised in `src/config.py`. Project objectives, sensor channels, dataset assumptions and evaluation scenarios remain documented in `docs/` and `results/`.

## Important evaluation note

The existing report and presentation results describe the original NumPy/pandas/scikit-learn implementation. The compatibility implementation preserves the intended methods but uses a pure-Python Isolation Forest and a standard-library simulator/processing path. Run `python experiments.py` and update the research tables only after validating the new outputs. Do not silently reuse old scores as if they came from the repaired code.

"""End-to-end system CLI (M4 integration).

  python main.py simulate --out data/synthetic_iot.csv        # make a labelled test network
  python main.py clean  --input data/synthetic_iot.csv --mode batch  --db results/audit.db
  python main.py clean  --input data/synthetic_iot.csv --mode stream --db results/audit.db
  python main.py report --db results/audit.db                  # flagged % per channel
  python main.py explain --db results/audit.db --mote 3 --channel humidity
Pipeline:  ingest CSV -> validate schema -> clean (batch or online) -> audit DB (raw never deleted) -> report
"""
import argparse, os
import pandas as pd
from src import config as C
from src.simulator import generate
from src.cleaning import CleaningPipeline
from src.stream import run_stream
from src import store

REQUIRED = ["timestamp", "mote_id"] + C.CHANNELS


def ingest(path):
    df = pd.read_csv(path, parse_dates=["timestamp"])
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise SystemExit(f"Input is missing required columns: {missing}")
    return df


def to_long(df, cleaned, flags):
    """Reshape batch output into the same long format the online cleaner emits."""
    rows = []
    for ch in C.CHANNELS:
        parts = flags[f"{ch}__parts"]
        reasons = [[k for k, v in parts.items() if v[i]] for i in range(len(df))]
        rows.append(pd.DataFrame({
            "timestamp": df.timestamp, "mote_id": df.mote_id, "channel": ch,
            "raw": df[ch], "cleaned": cleaned[ch],
            "flagged": flags[ch] & df[ch].notna().to_numpy(), "missing": df[ch].isna(),
            "reasons": [r if df[ch].iloc[i] == df[ch].iloc[i] else ["missing"] for i, r in enumerate(reasons)]}))
    return pd.concat(rows, ignore_index=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate"); s.add_argument("--out", default="data/synthetic_iot.csv")
    s.add_argument("--motes", type=int, default=8); s.add_argument("--days", type=int, default=7)
    s.add_argument("--seed", type=int, default=7)
    c = sub.add_parser("clean"); c.add_argument("--input", required=True)
    c.add_argument("--mode", choices=["batch", "stream"], default="batch")
    c.add_argument("--db", default="results/audit.db"); c.add_argument("--csv-out")
    r = sub.add_parser("report"); r.add_argument("--db", default="results/audit.db")
    e = sub.add_parser("explain"); e.add_argument("--db", default="results/audit.db")
    e.add_argument("--mote", type=int, required=True); e.add_argument("--channel", required=True, choices=C.CHANNELS)
    a = ap.parse_args()

    if a.cmd == "simulate":
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        generate(a.motes, a.days, seed=a.seed).to_csv(a.out, index=False); print("wrote", a.out)
    elif a.cmd == "clean":
        df = ingest(a.input)
        if a.mode == "batch":
            d, cleaned, flags, _ = CleaningPipeline().run(df)
            res = to_long(d, cleaned, flags)
        else:
            res = run_stream(df)
        os.makedirs(os.path.dirname(a.db) or ".", exist_ok=True)
        if os.path.exists(a.db): os.remove(a.db)
        con = store.open_db(a.db); store.save_results(con, res)
        print(f"[{a.mode}] cleaned {len(res):,} readings -> {a.db}"); print(store.summary(con).to_string(index=False))
        if a.csv_out:
            res.pivot_table(index=["timestamp", "mote_id"], columns="channel", values="cleaned").reset_index().to_csv(a.csv_out, index=False)
    elif a.cmd == "report":
        print(store.summary(store.open_db(a.db)).to_string(index=False))
    elif a.cmd == "explain":
        print(store.explain(store.open_db(a.db), a.mote, a.channel).to_string(index=False))


if __name__ == "__main__":
    main()

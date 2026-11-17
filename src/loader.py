"""Load the REAL Intel Berkeley Lab dataset (data.txt.gz) into the same schema.

Download: https://db.csail.mit.edu/labdata/labdata.html  (data.txt.gz, 34 MB)
Format (space separated): date time epoch moteid temperature humidity light voltage
The real data has no fault labels, so use it for a qualitative demo
(before/after plots, % of points flagged), NOT for precision/recall.
"""
import pandas as pd


def load_intel_lab(path, motes=None, resample_min=5):
    cols = ["date", "time", "epoch", "mote_id", "temperature", "humidity", "light", "voltage"]
    df = pd.read_csv(path, sep=r"\s+", names=cols, header=None, on_bad_lines="skip",
                     engine="python", compression="infer")
    df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"], errors="coerce")
    df = df.dropna(subset=["timestamp", "mote_id"])
    df["mote_id"] = pd.to_numeric(df["mote_id"], errors="coerce")
    df = df.dropna(subset=["mote_id"]); df["mote_id"] = df["mote_id"].astype(int)
    for c in ["temperature", "humidity", "light", "voltage"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if motes:
        df = df[df.mote_id.isin(motes)]
    out = (df.set_index("timestamp").groupby("mote_id")[["temperature", "humidity", "light", "voltage"]]
             .resample(f"{resample_min}min").median().reset_index())
    return out

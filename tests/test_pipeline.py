import numpy as np, pandas as pd
from src.simulator import generate
from src.cleaning import CleaningPipeline, hampel_flags, stuck_flags, range_flags
from src.evaluate import detection_scores, value_rmse
from src.loader import load_intel_lab


def test_hampel_catches_spike_but_not_clean_noise():
    rng = np.random.default_rng(0)
    x = pd.Series(20 + rng.normal(0, .1, 500)); x[250] += 5
    f = hampel_flags(x)
    assert f[250] and f.sum() <= 5


def test_stuck_detected_but_night_light_zeros_ignored():
    x = pd.Series(np.r_[np.random.rand(20), [5.0] * 12, np.random.rand(20)])
    assert stuck_flags(x, "temperature")[20:32].all()
    z = pd.Series([0.0] * 50)
    assert not stuck_flags(z, "light").any()


def test_range_rule():
    assert range_flags(pd.Series([21.0, 122.153]), "temperature").tolist() == [False, True]


def test_hybrid_beats_raw_and_is_accurate():
    raw = generate(n_motes=6, days=4)
    df, cleaned, flags, _ = CleaningPipeline().run(raw)
    assert detection_scores(df, flags).f1.mean() > 0.8
    assert (value_rmse(df, cleaned)["improvement_%"] > 80).all()
    assert cleaned[["temperature", "humidity", "light", "voltage"]].notna().all().all()


def test_intel_loader_format(tmp_path):
    p = tmp_path / "data.txt"
    p.write_text("2004-03-31 03:38:15.757551 2 1 122.153 -3.91901 11.04 2.03397\n"
                 "2004-03-31 03:38:45.757551 3 1 19.9884 37.0933 45.08 2.69964\n")
    out = load_intel_lab(str(p))
    assert {"timestamp", "mote_id", "temperature"} <= set(out.columns) and len(out) >= 1


# ---------- M4: integration tests ----------
import subprocess, sys, sqlite3
from src.stream import run_stream, StreamCleaner
from src import store


def test_stream_cleaner_is_accurate_and_causal():
    raw = generate(n_motes=6, days=4)
    res = run_stream(raw)
    assert res.cleaned.notna().all()
    d = raw.sort_values(["timestamp", "mote_id"]).reset_index(drop=True)
    r = res[res.channel == "temperature"].sort_values(["timestamp", "mote_id"]).reset_index(drop=True)
    truth = (d.fault_temperature.fillna("") != "") & (d.fault_temperature.fillna("") != "missing")
    pred = r.flagged.to_numpy() & r.raw.notna().to_numpy()
    recall = (truth & pred).sum() / truth.sum(); prec = (truth & pred).sum() / max(pred.sum(), 1)
    assert recall > 0.75 and prec > 0.7
    # causality: changing FUTURE data must not change past output
    raw2 = raw.copy(); cut = raw.timestamp.sort_values().iloc[len(raw) // 2]
    raw2.loc[raw2.timestamp > cut, "temperature"] += 50
    res2 = run_stream(raw2)
    a = res[res.timestamp <= cut].reset_index(drop=True); b = res2[res2.timestamp <= cut].reset_index(drop=True)
    assert a.cleaned.equals(b.cleaned)


def test_store_roundtrip_and_explain():
    raw = generate(n_motes=4, days=2)
    con = store.open_db(); store.save_results(con, run_stream(raw))
    s = store.summary(con)
    assert set(s.channel) == set(["temperature", "humidity", "light", "voltage"]) and s.flagged.sum() > 0
    n_raw_kept = con.execute("SELECT COUNT(*) FROM readings WHERE raw IS NOT NULL").fetchone()[0]
    assert n_raw_kept > 0                       # raw values are never deleted
    assert len(store.explain(con, 1, "temperature")) >= 0


def test_cli_end_to_end(tmp_path):
    csv = tmp_path / "d.csv"; db = tmp_path / "a.db"
    run = lambda *args: subprocess.run([sys.executable, "main.py", *args], capture_output=True, text=True, check=True)
    run("simulate", "--out", str(csv), "--motes", "4", "--days", "2")
    for mode in ("batch", "stream"):
        out = run("clean", "--input", str(csv), "--mode", mode, "--db", str(db)).stdout
        assert "temperature" in out
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM readings").fetchone()[0] > 0


def test_ingest_rejects_bad_schema(tmp_path):
    bad = tmp_path / "bad.csv"; bad.write_text("timestamp,mote_id,temperature\n2026-01-01,1,20\n")
    r = subprocess.run([sys.executable, "main.py", "clean", "--input", str(bad)], capture_output=True, text=True)
    assert r.returncode != 0 and "missing required columns" in (r.stderr + r.stdout)

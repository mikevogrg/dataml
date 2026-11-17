"""One-command demo:  python demo.py            (synthetic, scored)
                     python demo.py --intel data.txt.gz   (real Intel Lab data, unscored)
                     python demo.py --stream              (replay as a live stream)
"""
import argparse, os, time
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src import config as C
from src.simulator import generate
from src.cleaning import CleaningPipeline
from src.evaluate import detection_scores, recall_by_fault, value_rmse

os.makedirs("results", exist_ok=True)


def plot_before_after(df, cleaned, flags, ch, mote, path, hours=60):
    m = (df.mote_id == mote).to_numpy()
    n = hours * 12
    start = 0
    if f"fault_{ch}" in df:       # synthetic data: auto-pick the most fault-dense window for a convincing demo
        faulty = (df[f"fault_{ch}"].fillna("")[m] != "").astype(int).to_numpy()
        csum = np.concatenate([[0], np.cumsum(faulty)])
        start = int(np.argmax(csum[n:] - csum[:-n])) if len(faulty) > n else 0
    d, c, f = df[m].iloc[start:start + n], cleaned[m].iloc[start:start + n], flags[ch][m][start:start + n]
    fig, ax = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    ax[0].plot(d.timestamp, d[ch], lw=.8, color="#888", label="raw")
    ax[0].scatter(d.timestamp[f], d[ch][f], s=22, color="crimson", label="flagged", zorder=3)
    if f"true_{ch}" in d:   # clip the view so huge sentinels don't flatten the signal
        sd = np.nanstd(d[f"true_{ch}"]); ax[0].set_ylim(d[f"true_{ch}"].min() - 6 * sd, d[f"true_{ch}"].max() + 6 * sd)
    ax[0].set_title(f"{ch} - mote {mote}: raw data with detected faults"); ax[0].legend()
    ax[1].plot(c.timestamp, c[ch], lw=.9, color="#1a7f37", label="cleaned")
    if f"true_{ch}" in d: ax[1].plot(d.timestamp, d[f"true_{ch}"], lw=.7, ls="--", color="k", label="hidden truth")
    ax[1].set_title("after cleaning + imputation"); ax[1].legend()
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def run_synthetic():
    raw = generate()
    results = {}
    for name, use in [("rules only (range+stuck)", ("range", "stuck")),
                      ("Hampel only", ("hampel",)),
                      ("Spatial only", ("spatial",)),
                      ("Isolation Forest only", ("iforest",)),
                      ("HYBRID (all layers)", ("range", "hampel", "stuck", "spatial", "iforest"))]:
        df, cleaned, flags, rep = CleaningPipeline(use).run(raw)
        ds = detection_scores(df, flags)
        results[name] = (df, cleaned, flags, rep, ds)
    df, cleaned, flags, rep, ds = results["HYBRID (all layers)"]

    cmp_rows = []
    for name, (_, _, fl, _, d) in results.items():
        cmp_rows.append(dict(method=name, precision=d.precision.mean(), recall=d.recall.mean(), f1=d.f1.mean()))
    cmp = pd.DataFrame(cmp_rows)
    rbf = pd.DataFrame({n: recall_by_fault(r[0], r[2]) for n, r in results.items()})
    rm = value_rmse(df, cleaned)

    with open("results/report.md", "w") as fh:
        fh.write("# Cleaning results (synthetic IoT network, 8 motes x 7 days x 4 channels)\n\n")
        fh.write("## Detection: method comparison (mean over channels)\n\n" + cmp.round(3).to_markdown(index=False) + "\n\n")
        fh.write("## Hybrid detection per channel\n\n" + ds.round(3).to_markdown(index=False) + "\n\n")
        fh.write("## Recall by fault type (all channels)\n\n" + rbf.round(3).to_markdown() + "\n\n")
        fh.write("## Value accuracy vs hidden truth\n\n" + rm.round(4).to_markdown(index=False) + "\n")
    print(open("results/report.md").read())
    cmp.to_csv("results/method_comparison.csv", index=False); rbf.to_csv("results/recall_by_fault.csv")

    plot_before_after(df, cleaned, flags, "temperature", 3, "results/before_after_temperature.png")
    plot_before_after(df, cleaned, flags, "humidity", 5, "results/before_after_humidity.png")
    fig, ax = plt.subplots(figsize=(7, 4))
    cmp.set_index("method")[["precision", "recall", "f1"]].plot.bar(ax=ax, rot=15)
    ax.set_title("Detection quality by method"); fig.tight_layout(); fig.savefig("results/method_comparison.png", dpi=130)
    fig, ax = plt.subplots(figsize=(8, 4)); rbf.plot.bar(ax=ax, rot=0)
    ax.set_title("Recall by fault type"); ax.legend(fontsize=7); fig.tight_layout(); fig.savefig("results/recall_by_fault.png", dpi=130)
    df.to_csv("data/synthetic_iot.csv", index=False)
    cleaned[["timestamp", "mote_id"] + C.CHANNELS].to_csv("results/cleaned_output.csv", index=False)
    print("\nSaved figures + cleaned CSV to results/")


def run_intel(path):
    from src.loader import load_intel_lab
    raw = load_intel_lab(path, motes=list(range(1, 11)))
    df, cleaned, flags, rep = CleaningPipeline().run(raw)
    print(pd.DataFrame(rep).T)
    for ch in ["temperature", "humidity"]:
        plot_before_after(df, cleaned, flags, ch, 1, f"results/intel_{ch}.png", hours=24 * 5)
    print("Real data has no labels -> inspect results/intel_*.png")


def run_stream(speed=0.0):
    """Replays the cleaned result reading-by-reading to show what an edge gateway would emit."""
    raw = generate(n_motes=4, days=2)
    df, cleaned, flags, _ = CleaningPipeline().run(raw)
    shown = 0
    for i in range(len(df)):
        for ch in ["temperature"]:
            if flags[ch][i] or pd.isna(df[ch][i]):
                r = "MISSING" if pd.isna(df[ch][i]) else f"{df[ch][i]:.2f}"
                print(f"{df.timestamp[i]} mote {df.mote_id[i]} {ch}: {r:>8} -> repaired {cleaned[ch][i]:.2f} "
                      f"[true {df['true_'+ch][i]:.2f}]")
                shown += 1; time.sleep(speed)
        if shown > 25: break


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--intel"); ap.add_argument("--stream", action="store_true")
    a = ap.parse_args()
    run_intel(a.intel) if a.intel else run_stream(0.15) if a.stream else run_synthetic()

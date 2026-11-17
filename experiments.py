"""M3 experiments: everything the report quotes comes from here. Run: python experiments.py  (~3-4 min)
Outputs results/experiments.md and results/exp_*.png. Seeds are fixed -> reproducible."""
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from src import config as C
from src.simulator import generate
from src.cleaning import CleaningPipeline, build_features
from src.evaluate import detection_scores, value_rmse
from src.stream import run_stream

ALL = ("range", "hampel", "stuck", "spatial", "iforest")
SEEDS = [11, 12, 13, 14, 15]
md = ["# Experiments (all numbers reproducible: `python experiments.py`)\n"]


def f1_of(raw, use):
    df, cl, fl, _ = CleaningPipeline(use).run(raw)
    d = detection_scores(df, fl); r = value_rmse(df, cl)
    return d.precision.mean(), d.recall.mean(), d.f1.mean(), r["improvement_%"].mean()


def mean_std(rows):
    a = np.array(rows); return a.mean(0), a.std(0)


# ---- E1: multi-seed, method comparison + leave-one-layer-out ablation --------------
configs = {"rules (range+stuck)": ("range", "stuck"), "Hampel": ("hampel",), "Spatial": ("spatial",),
           "Isolation Forest": ("iforest",), "HYBRID (all)": ALL}
for drop in ALL:
    configs[f"hybrid minus {drop}"] = tuple(x for x in ALL if x != drop)
raws = {s: generate(seed=s) for s in SEEDS}
res1 = {}
for name, use in configs.items():
    res1[name] = mean_std([f1_of(raws[s], use) for s in SEEDS])
t = pd.DataFrame({n: {"precision": f"{m[0]:.3f}+-{sd[0]:.3f}", "recall": f"{m[1]:.3f}+-{sd[1]:.3f}",
                      "F1": f"{m[2]:.3f}+-{sd[2]:.3f}", "RMSE improvement %": f"{m[3]:.1f}+-{sd[3]:.1f}"}
                  for n, (m, sd) in res1.items()}).T
md += ["## E1. Method comparison and leave-one-layer-out ablation (5 seeds, mean +- std)\n", t.to_markdown(), "\n"]
fig, ax = plt.subplots(figsize=(9, 4.5)); names = list(res1)
ax.barh(names, [res1[n][0][2] for n in names], xerr=[res1[n][1][2] for n in names], color="#3b6ea5")
ax.set_xlabel("F1 (mean over channels, 5 seeds)"); ax.invert_yaxis(); fig.tight_layout(); fig.savefig("results/exp_ablation.png", dpi=130)

# ---- E2: Isolation Forest contamination sweep -------------------------------------
sweep = []
for cont in [0.01, 0.02, 0.03, 0.05, 0.08, 0.12]:
    C.IFOREST_CONTAMINATION = cont
    p1, r1, f1_, _ = f1_of(raws[SEEDS[0]], ("iforest",))
    p2, r2, f2_, _ = f1_of(raws[SEEDS[0]], ALL)
    sweep.append(dict(contamination=cont, IF_precision=p1, IF_recall=r1, IF_F1=f1_, hybrid_precision=p2, hybrid_recall=r2, hybrid_F1=f2_))
C.IFOREST_CONTAMINATION = 0.03
sw = pd.DataFrame(sweep)
md += ["## E2. Isolation Forest `contamination` sweep (seed 11)\n", sw.round(3).to_markdown(index=False), "\n"]
fig, ax = plt.subplots(figsize=(6, 4)); ax.plot(sw.contamination, sw.IF_F1, "o-", label="IF alone"); ax.plot(sw.contamination, sw.hybrid_F1, "s-", label="hybrid")
ax.set_xlabel("contamination"); ax.set_ylabel("F1"); ax.legend(); fig.tight_layout(); fig.savefig("results/exp_contamination.png", dpi=130)

# ---- E3: robustness to fault rate ----------------------------------------------------
fr = []
for rate in [0.02, 0.05, 0.08, 0.15, 0.25]:
    raw = generate(seed=21, fault_rate=rate)
    fr.append(dict(fault_rate=rate, **dict(zip(["precision", "recall", "F1", "RMSE_impr_%"], f1_of(raw, ALL)))))
fr = pd.DataFrame(fr)
md += ["## E3. Robustness to fault rate (hybrid, seed 21)\n", fr.round(3).to_markdown(index=False), "\n"]

# ---- E4: number of sensors (spatial redundancy) ---------------------------------------
ns = []
for n in [2, 3, 4, 8, 16]:
    raw = generate(n_motes=n, seed=31)
    row = dict(motes=n)
    for lab, use in [("spatial", ("spatial",)), ("hybrid", ALL)]:
        row[f"{lab}_F1"] = f1_of(raw, use)[2]
    ns.append(row)
ns = pd.DataFrame(ns)
md += ["## E4. Sensitivity to number of sensors (spatial layer needs neighbours)\n", ns.round(3).to_markdown(index=False), "\n"]
fig, ax = plt.subplots(figsize=(6, 4)); ax.plot(ns.motes, ns.spatial_F1, "o-", label="spatial only"); ax.plot(ns.motes, ns.hybrid_F1, "s-", label="hybrid")
ax.set_xlabel("number of motes"); ax.set_ylabel("F1"); ax.legend(); fig.tight_layout(); fig.savefig("results/exp_motes.png", dpi=130)

# ---- E5: unsupervised hybrid vs SUPERVISED random forest (needs labels) ---------------
def feats_labels(raw):
    df, cl, fl, _ = CleaningPipeline(("range", "hampel", "stuck", "spatial")).run(raw)
    X, y = [], []
    for ch in C.CHANNELS:
        f = build_features(df, ch).fillna(0)
        for k, v in fl[f"{ch}__parts"].items(): f[f"flag_{k}"] = v.astype(int)
        f["ch"] = C.CHANNELS.index(ch)
        lab = df[f"fault_{ch}"].fillna(""); yy = ((lab != "") & (lab != "missing")).astype(int)
        keep = df[ch].notna().to_numpy()
        X.append(f[keep]); y.append(yy[keep])
    return pd.concat(X), pd.concat(y)
Xtr, ytr = zip(*[feats_labels(raws[s]) for s in SEEDS[:3]]); Xtr, ytr = pd.concat(Xtr), pd.concat(ytr)
rf = RandomForestClassifier(300, n_jobs=-1, random_state=0, class_weight="balanced_subsample", min_samples_leaf=3).fit(Xtr, ytr)
rows = []
for s in SEEDS[3:]:
    X, y = feats_labels(raws[s]); p = rf.predict(X)
    tp = ((p == 1) & (y == 1)).sum(); fp = ((p == 1) & (y == 0)).sum(); fn = ((p == 0) & (y == 1)).sum()
    P = tp / max(tp + fp, 1); R = tp / max(tp + fn, 1); rows.append((P, R, 2 * P * R / max(P + R, 1e-9)))
    hy = f1_of(raws[s], ALL); rows.append(hy[:3])
rf_m = np.mean(rows[0::2], 0); un_m = np.mean(rows[1::2], 0)
sup = pd.DataFrame({"supervised RandomForest (trained on 3 labelled seeds)": rf_m, "our unsupervised hybrid (no labels)": un_m}, index=["precision", "recall", "F1"]).T
md += ["## E5. Unsupervised hybrid vs supervised Random Forest (test seeds 14, 15)\n", sup.round(3).to_markdown(),
       "\nThe supervised model needs thousands of labelled faults, which real deployments do not have; the hybrid needs none.\n"]

# ---- E6: online (causal) vs offline (batch) ---------------------------------------------
raw = raws[SEEDS[0]]
df, cl, fl, _ = CleaningPipeline().run(raw); b = detection_scores(df, fl)
res = run_stream(raw); d = raw.sort_values(["timestamp", "mote_id"]).reset_index(drop=True); srows = []
for ch in C.CHANNELS:
    r = res[res.channel == ch].sort_values(["timestamp", "mote_id"]).reset_index(drop=True)
    lab = d[f"fault_{ch}"].fillna(""); truth = ((lab != "") & (lab != "missing")).to_numpy(); pred = r.flagged.to_numpy() & r.raw.notna().to_numpy()
    tp = (truth & pred).sum(); fp = (~truth & pred).sum(); fn = (truth & ~pred).sum()
    P = tp / max(tp + fp, 1); R = tp / max(tp + fn, 1); srows.append(dict(channel=ch, online_precision=P, online_recall=R, online_F1=2 * P * R / max(P + R, 1e-9)))
st = pd.DataFrame(srows).merge(b[["channel", "precision", "recall", "f1"]].rename(columns=dict(precision="batch_precision", recall="batch_recall", f1="batch_F1")), on="channel")
md += ["## E6. Online (causal, no Isolation Forest) vs offline batch (seed 11)\n", st.round(3).to_markdown(index=False), "\n"]

open("results/experiments.md", "w").write("\n".join(md))
print("\n".join(md))

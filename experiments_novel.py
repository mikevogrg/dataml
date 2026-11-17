"""E7: what is the ML layer FOR?  Test on a NOVEL fault type ('burst') no rule targets.
Run after experiments.py; appends/replaces the E7 section of results/experiments.md."""
import numpy as np, pandas as pd
from src import config as C
from src.simulator import generate
from src.cleaning import CleaningPipeline
from src.evaluate import detection_scores

ALL = ("range", "hampel", "stuck", "spatial", "iforest"); NOIF = ALL[:-1]
C.IFOREST_CONTAMINATION = 0.03
rows = []
for seed in [11, 12, 13]:
    for scenario, bursts in [("known faults only", 0), ("known + novel burst fault", 6)]:
        raw = generate(seed=seed, bursts=bursts)
        for name, use in [("rules+Hampel+spatial (no ML)", NOIF), ("full hybrid (+Isolation Forest)", ALL)]:
            df, cl, fl, _ = CleaningPipeline(use).run(raw); d = detection_scores(df, fl)
            br = np.nan
            if bursts:
                m = {ch: (df[f"fault_{ch}"].fillna("") == "burst").to_numpy() for ch in C.CHANNELS}
                br = sum((fl[ch] & m[ch]).sum() for ch in C.CHANNELS) / sum(m[ch].sum() for ch in C.CHANNELS)
            rows.append(dict(scenario=scenario, method=name, F1=d.f1.mean(), precision=d.precision.mean(), recall=d.recall.mean(), burst_recall=br))
t = pd.DataFrame(rows).groupby(["scenario", "method"]).mean().round(3).reset_index()
sec = ("## E7. Role of the ML layer: novel (unanticipated) fault type, 3 seeds\n\n" + t.to_markdown(index=False) +
       "\n\nReading: on faults we wrote rules for, the ML layer costs a little precision; when a NEW fault type appears it "
       "adds recall that no hand-written rule provides.\n")
p = "results/experiments.md"; txt = open(p).read()
if "## E7." in txt: txt = txt[:txt.index("## E7.")]
open(p, "w").write(txt.rstrip() + "\n\n" + sec); print(sec)

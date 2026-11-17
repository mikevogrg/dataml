"""Reproducible standard-library evaluation run."""
from pathlib import Path
from src.core import generate,CleaningPipeline
from src.evaluate import detection_scores,value_rmse
from src import config as C

def run():
    seeds=(11,12,13,14,15); methods={"rules (range+stuck)":("range","stuck"),"Hampel":("hampel",),"Spatial":("spatial",),"Isolation Forest":("iforest",),"HYBRID (all)":CleaningPipeline.METHODS}
    lines=["# Experiments","", "Metrics are recalculated using the pure-Python compatibility implementation."]
    for name,use in methods.items():
        scores=[]
        for seed in seeds:
            rows,cleaned,flags,_=CleaningPipeline(use).run(generate(seed=seed))
            d=detection_scores(rows,flags)
            scores.append(tuple(sum(x[k] for x in d)/len(d) for k in ("precision","recall","f1")))
        avg=[sum(x[i] for x in scores)/len(scores) for i in range(3)]
        lines += ["",f"## {name}",f"- Precision: {avg[0]:.3f}",f"- Recall: {avg[1]:.3f}",f"- F1: {avg[2]:.3f}"]
    Path("results").mkdir(exist_ok=True); Path("results/experiments.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
if __name__=="__main__": run()

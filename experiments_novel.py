"""Novel-fault experiment using the project's existing evaluation design."""
from pathlib import Path
from src.core import generate,CleaningPipeline
from src.evaluate import detection_scores

def run():
    lines=["# E7. Role of the ML layer: novel fault scenario",""]
    for seed in (11,12,13):
        for label,bursts in (("known faults only",0),("known + novel burst fault",6)):
            rows,cleaned,flags,_=CleaningPipeline().run(generate(seed=seed,bursts=bursts))
            d=detection_scores(rows,flags)
            lines.append(f"- Seed {seed}, {label}: mean F1 {sum(x['f1'] for x in d)/len(d):.3f}")
    p=Path("results/experiments.md"); p.parent.mkdir(exist_ok=True)
    p.write_text(p.read_text(encoding="utf-8")+"\n"+"\n".join(lines)+"\n" if p.exists() else "\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
if __name__=="__main__": run()

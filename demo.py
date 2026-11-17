"""One-command synthetic demo, online replay, or real Intel Lab inspection."""
import argparse
from pathlib import Path
from src.core import generate,CleaningPipeline,write_csv,read_csv,stream_clean,load_intel_lab,open_db,save_results,summary,to_long
from src import config as C

def run_synthetic():
    raw=generate(); rows,cleaned,flags,report=CleaningPipeline().run(raw)
    Path("results").mkdir(exist_ok=True); Path("data").mkdir(exist_ok=True)
    write_csv("data/synthetic_iot.csv",raw)
    write_csv("results/cleaned_output.csv",[{"timestamp":r["timestamp"],"mote_id":r["mote_id"],**{ch:cleaned[i][ch] for ch in C.CHANNELS}} for i,r in enumerate(rows)])
    results=to_long(rows,cleaned,flags); con=open_db("results/audit.db")
    con.execute("DELETE FROM readings"); save_results(con,results)
    lines=["# Cleaning results","","| Channel | Flagged | Missing |","|---|---:|---:|"]
    for ch,v in report.items(): lines.append(f"| {ch} | {v['flagged']} | {v['missing']} |")
    Path("results/report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines)); print("Saved data/synthetic_iot.csv, results/cleaned_output.csv and results/audit.db")

def run_stream():
    rows=generate(n_motes=4,days=2); out=stream_clean(rows); shown=0
    for r in out:
        if r["flagged"] or r["missing"]:
            print(f"{r['timestamp']} mote {r['mote_id']} {r['channel']}: {r['raw']} -> {r['cleaned']} [{','.join(r['reasons'])}]")
            shown+=1
            if shown>=30: break

def run_intel(path):
    rows=load_intel_lab(path,motes=list(range(1,11)))
    _,_,_,report=CleaningPipeline().run(rows)
    print("Real Intel Lab data (unlabelled; qualitative inspection only)")
    for ch,v in report.items(): print(ch,v)

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--intel"); p.add_argument("--stream",action="store_true"); a=p.parse_args()
    run_intel(a.intel) if a.intel else run_stream() if a.stream else run_synthetic()

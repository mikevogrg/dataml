"""Run a compact synthetic demonstration without third-party packages."""
from pathlib import Path
from src.core import generate,CleaningPipeline,write_csv,to_long,open_db,save_results,summary
from src import config as C

def run():
    raw=generate()
    rows,cleaned,flags,report=CleaningPipeline().run(raw)
    Path("results").mkdir(exist_ok=True); Path("data").mkdir(exist_ok=True)
    write_csv("data/synthetic_iot.csv",raw)
    write_csv("results/cleaned_output.csv",[{"timestamp":r["timestamp"],"mote_id":r["mote_id"],**{ch:cleaned[i][ch] for ch in C.CHANNELS}} for i,r in enumerate(rows)])
    results=to_long(rows,cleaned,flags); con=open_db("results/audit.db"); con.execute("DELETE FROM readings"); save_results(con,results)
    lines=["# Cleaning results","", "| Channel | Flagged | Missing |", "|---|---:|---:|"]
    for ch,v in report.items(): lines.append(f"| {ch} | {v['flagged']} | {v['missing']} |")
    Path("results/report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines)); print("Saved cleaned CSV and SQLite audit database.")
if __name__=="__main__": run()

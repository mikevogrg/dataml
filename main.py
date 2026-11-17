"""Command-line interface for the IoT sensor data cleaning system (standard library only)."""
import argparse, os
from pathlib import Path
from src import config as C
from src.core import generate,read_csv,write_csv,CleaningPipeline,stream_clean,open_db,save_results,summary,explain,to_long

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("simulate"); s.add_argument("--out",default="data/synthetic_iot.csv"); s.add_argument("--motes",type=int,default=8); s.add_argument("--days",type=int,default=7); s.add_argument("--seed",type=int,default=7)
    c=sub.add_parser("clean"); c.add_argument("--input",required=True); c.add_argument("--mode",choices=["batch","stream"],default="batch"); c.add_argument("--db",default="results/audit.db"); c.add_argument("--csv-out")
    r=sub.add_parser("report"); r.add_argument("--db",default="results/audit.db")
    e=sub.add_parser("explain"); e.add_argument("--db",default="results/audit.db"); e.add_argument("--mote",type=int,required=True); e.add_argument("--channel",choices=C.CHANNELS,required=True)
    a=ap.parse_args()
    if a.cmd=="simulate":
        rows=generate(a.motes,a.days,seed=a.seed); write_csv(a.out,rows); print("wrote",a.out)
    elif a.cmd=="clean":
        raw=read_csv(a.input)
        if a.mode=="batch":
            d,cleaned,flags,_=CleaningPipeline().run(raw); results=to_long(d,cleaned,flags)
        else: results=stream_clean(raw)
        Path(a.db).parent.mkdir(parents=True,exist_ok=True)
        if os.path.exists(a.db): os.remove(a.db)
        con=open_db(a.db); save_results(con,results)
        print(f"[{a.mode}] cleaned {len(results):,} readings -> {a.db}")
        print("channel | readings | flagged | missing | pct flagged")
        for row in summary(con): print(" | ".join(str(x) for x in row))
        if a.csv_out:
            grouped={}
            for r in results: grouped.setdefault((r["timestamp"],r["mote_id"]),{"timestamp":r["timestamp"],"mote_id":r["mote_id"]})[r["channel"]]=r["cleaned"]
            write_csv(a.csv_out,list(grouped.values()))
    elif a.cmd=="report":
        for row in summary(open_db(a.db)): print(row)
    elif a.cmd=="explain":
        for row in explain(open_db(a.db),a.mote,a.channel): print(row)

if __name__=="__main__": main()

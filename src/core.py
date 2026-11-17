"""Standard-library IoT data cleaning engine.

Preserves the project's five detection layers, batch/online paths, imputation,
and SQLite audit trail without third-party binary dependencies.
"""
import csv, math, random, statistics, sqlite3
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from . import config as C

def number(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError): return None

def med(values):
    a=sorted(x for x in values if x is not None and math.isfinite(x))
    if not a: return None
    n=len(a); return (a[n//2] if n%2 else (a[n//2-1]+a[n//2])/2)

def mean(values):
    a=[x for x in values if x is not None and math.isfinite(x)]
    return sum(a)/len(a) if a else None

def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    required=["timestamp","mote_id"]+C.CHANNELS
    if not rows: raise ValueError("Input CSV contains no data rows.")
    missing=[x for x in required if x not in rows[0]]
    if missing: raise ValueError("Input is missing required columns: "+str(missing))
    out=[]
    for r in rows:
        q=dict(r); q["mote_id"]=int(float(r["mote_id"]))
        for ch in C.CHANNELS: q[ch]=number(r.get(ch))
        out.append(q)
    return out

def write_csv(path, rows, fields=None):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    if not rows: return
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow({k:("" if r.get(k) is None else r.get(k)) for k in fields})

def generate(n_motes=8,days=7,fault_rate=.08,seed=7,bursts=0):
    rng=random.Random(seed); steps=int(days*24*60/C.SAMPLE_MINUTES)
    base=[]; ar=0.0; t=datetime(2026,3,1)
    for i in range(steps):
        hour=(i*C.SAMPLE_MINUTES/60)%24
        ar=.9*ar+rng.gauss(0,.06)
        temp=21+3*math.sin(2*math.pi*hour/24-1.5)+ar
        light=max(0,(450*math.sin(2*math.pi*hour/24-math.pi/2+.2)+120))
        base.append((temp,light))
    rows=[]
    for m in range(1,n_motes+1):
        off=rng.gauss(0,.6); hum_noise=rng.gauss(0,1); prev=[0.0]*4
        signals=[]
        for i,(bt,bl) in enumerate(base):
            temp=bt+off+prev[0]
            prev[0]=.9*prev[0]+rng.gauss(0,.06)
            vals=[temp,45-1.6*(temp-21)+hum_noise+rng.gauss(0,.25),
                  max(0,bl*rng.uniform(.7,1.1)+rng.gauss(0,8)) if bl else 0,
                  2.75-.0004*(i*C.SAMPLE_MINUTES/60)+rng.gauss(0,.004)]
            signals.append(vals)
        faulty=[v[:] for v in signals]; labels=[[""]*steps for _ in C.CHANNELS]
        for ci,ch in enumerate(C.CHANNELS):
            x=faulty
            budget=int(steps*fault_rate); used=set(); attempts=0
            while len(used)<budget and attempts<steps*3:
                attempts+=1; kind=rng.choices(["spike","stuck","bias","drift","sentinel","missing"],[.35,.15,.1,.1,.1,.2])[0]
                length=1 if kind in ("spike","sentinel") else rng.randint(12, min(39,steps))
                start=rng.randrange(max(1,steps-length+1))
                if any(j in used for j in range(max(0,start-3),min(steps,start+length+3))): continue
                scale=statistics.pstdev([z[ci] for z in signals])+1e-9
                for j in range(start,start+length):
                    used.add(j); labels[ci][j]=kind
                    if kind=="spike": x[j][ci]+=rng.choice([-1,1])*rng.uniform(6,14)*scale
                    elif kind=="stuck": x[j][ci]=x[start][ci]
                    elif kind=="bias": x[j][ci]+=rng.choice([-1,1])*rng.uniform(2.5,4)*scale
                    elif kind=="drift": x[j][ci]+=((j-start)/max(1,length-1))*rng.choice([-1,1])*rng.uniform(3,5)*scale
                    elif kind=="sentinel": x[j][ci]={"temperature":122.153,"humidity":-3.9,"light":54612.0,"voltage":0.0}[ch]
                    elif kind=="missing": x[j][ci]=None
        for i in range(steps):
            ts=(t+timedelta(minutes=i*C.SAMPLE_MINUTES)).isoformat(sep=" ")
            row={"timestamp":ts,"mote_id":m}
            for ci,ch in enumerate(C.CHANNELS):
                row[ch]=faulty[i][ci]; row["true_"+ch]=signals[i][ci]; row["fault_"+ch]=labels[ci][i]
            rows.append(row)
    return sorted(rows,key=lambda r:(r["timestamp"],r["mote_id"]))

def regularise(rows):
    by=defaultdict(dict)
    for r in rows:
        by[r["mote_id"]][r["timestamp"]]=r
    out=[]
    for mote,items in sorted(by.items()):
        times=sorted(items)
        if not times: continue
        # Existing timestamp grid is retained; missing packets become explicit only
        # when their timestamps can be inferred at the configured five-minute cadence.
        start=datetime.fromisoformat(times[0]); end=datetime.fromisoformat(times[-1])
        cur=start
        while cur<=end:
            key=cur.isoformat(sep=" ")
            row=items.get(key,{"timestamp":key,"mote_id":mote})
            for ch in C.CHANNELS: row.setdefault(ch,None)
            out.append(dict(row)); cur+=timedelta(minutes=C.SAMPLE_MINUTES)
    return sorted(out,key=lambda r:(r["timestamp"],r["mote_id"]))

def _rolling(vals, i, window):
    h=window//2; return [v for v in vals[max(0,i-h):min(len(vals),i+h+1)] if v is not None]

def hampel_flags(vals,window=C.HAMPEL_WINDOW,nsigma=C.HAMPEL_NSIGMA):
    meds=[]; sigmas=[]
    for i,x in enumerate(vals):
        w=_rolling(vals,i,window); m=med(w); mad=med([abs(v-m) for v in w]) if m is not None else None
        meds.append(m); sigmas.append(1.4826*mad if mad is not None else 0)
    pos=[s for s in sigmas if s>0]; floor=(med(pos) or 1e-6)*C.HAMPEL_SIGMA_FLOOR
    return [x is not None and meds[i] is not None and abs(x-meds[i])>nsigma*max(sigmas[i],floor,1e-6) for i,x in enumerate(vals)]

def stuck_flags(vals,ch,min_run=C.STUCK_MIN_RUN):
    out=[False]*len(vals); start=0
    while start<len(vals):
        end=start+1
        while end<len(vals) and vals[end] is not None and vals[start] is not None and vals[end]==vals[start]: end+=1
        if end-start>=min_run and not (C.STUCK_IGNORE_VALUE.get(ch)==vals[start]):
            for j in range(start,end):
                if vals[j] is not None: out[j]=True
        start=end
    return out

def _iforest_flags(features, contamination=C.IFOREST_CONTAMINATION, trees=C.IFOREST_TREES, seed=C.RANDOM_STATE):
    """Pure-Python Isolation Forest: random feature/split trees and path-length scores."""
    n=len(features)
    if n<8: return [False]*n
    rng=random.Random(seed); dim=len(features[0]); maxdepth=math.ceil(math.log2(n))
    def build(indices,depth):
        if depth>=maxdepth or len(indices)<=1: return (len(indices),)
        candidates=[k for k in range(dim) if max(features[i][k] for i in indices)>min(features[i][k] for i in indices)]
        if not candidates: return (len(indices),)
        k=rng.choice(candidates); lo=min(features[i][k] for i in indices); hi=max(features[i][k] for i in indices)
        split=rng.uniform(lo,hi)
        left=[i for i in indices if features[i][k]<split]; right=[i for i in indices if features[i][k]>=split]
        if not left or not right: return (len(indices),)
        return (k,split,build(left,depth+1),build(right,depth+1))
    forest=[build(list(range(n)),0) for _ in range(trees)]
    def c_factor(size):
        if size<=1:return 0
        h=math.log(size-1)+0.5772156649
        return 2*h-2*(size-1)/size
    def path(tree,row,depth=0):
        if len(tree)==1:return depth+c_factor(tree[0])
        return path(tree[2] if row[tree[0]]<tree[1] else tree[3],row,depth+1)
    scores=[2**(-sum(path(t,row) for t in forest)/trees/max(c_factor(n),1e-9)) for row in features]
    ranked=sorted(range(n),key=lambda i:scores[i],reverse=True)
    count=max(1,min(n,int(math.ceil(n*contamination))))
    chosen=set(ranked[:count]); return [i in chosen for i in range(n)]

def _spatial_residual(rows,ch,vals):
    groups=defaultdict(list)
    for i,r in enumerate(rows): groups[r["timestamp"]].append(i)
    cross={}
    for ts,idx in groups.items(): cross[ts]=med([vals[i] for i in idx])
    bym=defaultdict(list)
    for i,r in enumerate(rows): bym[r["mote_id"]].append(i)
    residual=[None]*len(rows)
    for m,idx in bym.items():
        diffs=[]
        for i in idx:
            x,c=vals[i],cross[rows[i]["timestamp"]]
            diffs.append((x/c if ch=="light" and c and c>100 else (x-c if x is not None and c is not None else None)))
        typical=med([v for v in diffs if v is not None])
        for j,i in enumerate(idx):
            if diffs[j] is not None:
                residual[i]=(diffs[j]-typical) if ch!="light" else ((vals[i]-med([vals[k] for k in groups[rows[i]["timestamp"]] if vals[k] is not None])*typical)/(cross[rows[i]["timestamp"]]+50) if cross[rows[i]["timestamp"]] is not None else None)
    return residual,cross

def _spatial_flags(rows,ch,vals):
    residual,_=_spatial_residual(rows,ch,vals); bym=defaultdict(list)
    for i,r in enumerate(rows): bym[r["mote_id"]].append(i)
    out=[False]*len(rows)
    for idx in bym.values():
        sm=[]
        for p,i in enumerate(idx): sm.append(med([v for v in residual[idx[q]] for q in []]) if False else med([residual[idx[q]] for q in range(max(0,p-C.SPATIAL_WINDOW//2),min(len(idx),p+C.SPATIAL_WINDOW//2+1))]))
        dev=[abs(v-med([x for x in sm if x is not None])) for v in sm if v is not None]
        nz=[v for v in dev if v>0]; sigma=max(1.4826*(med(nz) or 0),1e-9)
        for p,i in enumerate(idx): out[i]=sm[p] is not None and abs(sm[p])>C.SPATIAL_NSIGMA*sigma
    return out

def _features(rows,ch,vals):
    bym=defaultdict(list)
    for i,r in enumerate(rows): bym[r["mote_id"]].append(i)
    feats=[None]*len(rows)
    for idx in bym.values():
        seq=[vals[i] for i in idx]
        for p,i in enumerate(idx):
            short=med(_rolling(seq,p,C.HAMPEL_WINDOW)); long=med(_rolling(seq,p,C.LONG_WINDOW))
            prev=seq[p-1] if p else None
            window=_rolling(seq,p,C.HAMPEL_WINDOW)
            sd=statistics.pstdev(window) if len(window)>1 else 0
            x=vals[i]
            if x is not None and short is not None and long is not None and prev is not None:
                feats[i]=[x-short,x-long,x-prev,sd]
    spatial,_=_spatial_residual(rows,ch,vals)
    for i,f in enumerate(feats):
        if f is not None and spatial[i] is not None: f.append(spatial[i])
        else: feats[i]=None
    return feats

def impute(rows,ch,bad):
    vals=[None if bad[i] else r.get(ch) for i,r in enumerate(rows)]
    bym=defaultdict(list)
    for i,r in enumerate(rows): bym[r["mote_id"]].append(i)
    cross_by_time=defaultdict(list)
    for i,r in enumerate(rows):
        if vals[i] is not None: cross_by_time[r["timestamp"]].append(vals[i])
    cross={t:med(v) for t,v in cross_by_time.items()}
    out=vals[:]
    for idx in bym.values():
        for p,i in enumerate(idx):
            if out[i] is not None: continue
            left=next((idx[q] for q in range(p-1,-1,-1) if vals[idx[q]] is not None),None)
            right=next((idx[q] for q in range(p+1,len(idx)) if vals[idx[q]] is not None),None)
            gap=(idx.index(right)-idx.index(left)-1) if left is not None and right is not None else 999
            if left is not None and right is not None and gap<=C.SHORT_GAP:
                total=idx.index(right)-idx.index(left); frac=(p-idx.index(left))/total
                out[i]=vals[left]+(vals[right]-vals[left])*frac
            else:
                out[i]=cross.get(rows[i]["timestamp"])
    return out

class CleaningPipeline:
    METHODS=("range","hampel","stuck","spatial","iforest")
    def __init__(self,use=METHODS): self.use=tuple(use)
    def run(self,raw):
        rows=regularise(raw); cleaned=[dict(r) for r in rows]; flags={}; report={}
        for ch in C.CHANNELS:
            vals=[r.get(ch) for r in rows]; comp={}
            if "range" in self.use:
                lo,hi=C.PHYSICAL_RANGE[ch]; comp["range"]=[x is not None and (x<lo or x>hi) for x in vals]
            masked=[None if comp.get("range",[False]*len(rows))[i] else x for i,x in enumerate(vals)]
            bym=defaultdict(list)
            for i,r in enumerate(rows): bym[r["mote_id"]].append(i)
            if "hampel" in self.use:
                f=[False]*len(rows)
                for idx in bym.values():
                    z=hampel_flags([masked[i] for i in idx])
                    for p,i in enumerate(idx): f[i]=z[p]
                comp["hampel"]=f
            if "stuck" in self.use:
                f=[False]*len(rows)
                for idx in bym.values():
                    z=stuck_flags([masked[i] for i in idx],ch)
                    for p,i in enumerate(idx): f[i]=z[p]
                comp["stuck"]=f
            if "spatial" in self.use: comp["spatial"]=_spatial_flags(rows,ch,masked)
            if "iforest" in self.use:
                features=_features(rows,ch,masked); valid=[i for i,f in enumerate(features) if f is not None and masked[i] is not None and not comp.get("range",[False]*len(rows))[i]]
                pred=_iforest_flags([features[i] for i in valid])
                f=[False]*len(rows)
                for p,i in enumerate(valid): f[i]=pred[p]
                comp["iforest"]=f
            bad=[any(v[i] for v in comp.values()) for i in range(len(rows))]
            flags[ch]=bad; flags[ch+"__parts"]=comp
            filled=impute(rows,ch,[bad[i] or vals[i] is None for i in range(len(rows))])
            for i,x in enumerate(filled): cleaned[i][ch]=x
            report[ch]={"flagged":sum(bad),"missing":sum(x is None for x in vals),**{k:sum(v) for k,v in comp.items()}}
        return rows,cleaned,flags,report

def stream_clean(rows):
    """Causal online cleaner; deliberately excludes offline Isolation Forest."""
    state={}; output=[]
    for ts in sorted(set(r["timestamp"] for r in rows)):
        tick=[r for r in rows if r["timestamp"]==ts]
        for ch in C.CHANNELS:
            valid=[r[ch] for r in tick if r.get(ch) is not None and C.PHYSICAL_RANGE[ch][0]<=r[ch]<=C.PHYSICAL_RANGE[ch][1]]
            cross=med(valid)
            for r in tick:
                key=(r["mote_id"],ch); s=state.setdefault(key,{"hist":deque(maxlen=C.HAMPEL_WINDOW),"same":0,"last":None,"good":None})
                x=r.get(ch); reasons=[]
                if x is None: reasons=["missing"]
                elif not C.PHYSICAL_RANGE[ch][0]<=x<=C.PHYSICAL_RANGE[ch][1]: reasons=["range"]
                else:
                    h=list(s["hist"]); m=med(h); mad=med([abs(v-m) for v in h]) if h and m is not None else 0
                    if len(h)>=5 and m is not None and abs(x-m)>C.HAMPEL_NSIGMA*max(1.4826*(mad or 0),1e-6): reasons.append("hampel")
                    s["same"]=s["same"]+1 if s["last"]==x else 1; s["last"]=x
                    if s["same"]>=C.STUCK_MIN_RUN and C.STUCK_IGNORE_VALUE.get(ch)!=x: reasons.append("stuck")
                    if cross is not None and s["good"] is not None and abs(x-cross)>C.SPATIAL_NSIGMA*max(abs(s["good"]-cross),.01): reasons.append("spatial")
                    s["hist"].append(x)
                bad=bool(reasons); clean=(s["good"] if bad else x)
                if not bad: s["good"]=x
                output.append({"timestamp":ts,"mote_id":r["mote_id"],"channel":ch,"raw":x,"cleaned":clean if clean is not None else cross,"flagged":bad and reasons!=["missing"],"missing":x is None,"reasons":reasons})
    return output

def open_db(path=":memory:"):
    con=sqlite3.connect(path)
    con.executescript("""CREATE TABLE IF NOT EXISTS readings(timestamp TEXT,mote_id INTEGER,channel TEXT,raw REAL,cleaned REAL,flagged INTEGER,missing INTEGER,reasons TEXT,PRIMARY KEY(timestamp,mote_id,channel)); CREATE VIEW IF NOT EXISTS summary AS SELECT channel,COUNT(*) n,SUM(flagged) flagged,SUM(missing) missing,ROUND(100.0*SUM(flagged)/COUNT(*),2) pct_flagged FROM readings GROUP BY channel;""")
    return con

def save_results(con,rows):
    con.executemany("INSERT OR REPLACE INTO readings VALUES(?,?,?,?,?,?,?,?)",[(str(r["timestamp"]),int(r["mote_id"]),r["channel"],r.get("raw"),r.get("cleaned"),int(r["flagged"]),int(r["missing"]),",".join(r["reasons"])) for r in rows]); con.commit()

def summary(con): return con.execute("SELECT * FROM summary ORDER BY channel").fetchall()
def explain(con,mote,channel,limit=10):
    return con.execute("SELECT timestamp,raw,cleaned,reasons FROM readings WHERE mote_id=? AND channel=? AND flagged=1 ORDER BY timestamp DESC LIMIT ?",(mote,channel,limit)).fetchall()

def to_long(rows,cleaned,flags):
    out=[]
    for ch in C.CHANNELS:
        parts=flags[ch+"__parts"]
        for i,r in enumerate(rows):
            reasons=[k for k,v in parts.items() if v[i]]
            missing=r.get(ch) is None
            out.append({"timestamp":r["timestamp"],"mote_id":r["mote_id"],"channel":ch,"raw":r.get(ch),"cleaned":cleaned[i].get(ch),"flagged":flags[ch][i] and not missing,"missing":missing,"reasons":reasons or (["missing"] if missing else [])})
    return out

def load_intel_lab(path,motes=None,resample_min=5):
    rows=[]
    import gzip
    opener=gzip.open if str(path).endswith(".gz") else open
    with opener(path,"rt",encoding="utf-8",errors="replace") as f:
        for line in f:
            p=line.split()
            if len(p)<8: continue
            try:
                ts=datetime.fromisoformat(p[0]+" "+p[1]); mote=int(p[3])
                if motes and mote not in motes: continue
                rows.append({"timestamp":ts.isoformat(sep=" "),"mote_id":mote,**dict(zip(C.CHANNELS,[number(x) for x in p[4:8]]))})
            except (ValueError,IndexError): continue
    # Aggregate to configured time buckets, matching the original loader's median resampling.
    buckets=defaultdict(list)
    for r in rows:
        dt=datetime.fromisoformat(r["timestamp"]); minute=(dt.minute//resample_min)*resample_min
        key=dt.replace(minute=minute,second=0,microsecond=0).isoformat(sep=" ")
        buckets[(key,r["mote_id"])].append(r)
    out=[]
    for (ts,m),group in sorted(buckets.items()):
        out.append({"timestamp":ts,"mote_id":m,**{ch:med([g[ch] for g in group]) for ch in C.CHANNELS}})
    return out

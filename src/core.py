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
        q=dict(r); q["mote_id"]=int(float(r["mote_id"])); q["timestamp"]=datetime.fromisoformat(r["timestamp"].replace("Z","+00:00")).replace(tzinfo=None).isoformat(sep=" ")
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
            if bursts:
                brng=random.Random(seed+1000+ci+m)
                noise=statistics.pstdev([z[ci] for z in signals])+1e-9
                for _ in range(bursts):
                    length=brng.randint(20,min(59,steps))
                    start=brng.randrange(max(1,steps-length+1))
                    if any(labels[ci][j] for j in range(start,start+length)): continue
                    for j in range(start,start+length):
                        faulty[j][ci]+=brng.gauss(0,8*noise)
                        labels[ci][j]="burst"
        for i in range(steps):
            ts=(t+timedelta(minutes=i*C.SAMPLE_MINUTES)).isoformat(sep=" ")
            row={"timestamp":ts,"mote_id":m}
            for ci,ch in enumerate(C.CHANNELS):
                row[ch]=faulty[i][ci]; row["true_"+ch]=signals[i][ci]; row["fault_"+ch]=labels[ci][i]
            rows.append(row)
    return sorted(rows,key=lambda r:(r["timestamp"],r["mote_id"]))

def regularise(rows):
    """Aggregate readings into the configured time grid and expose absent bins.

    Intel Lab observations arrive at roughly 31-second intervals, so requiring
    exact five-minute timestamp matches would discard most real observations.
    """
    by=defaultdict(lambda: defaultdict(list))
    interval=C.SAMPLE_MINUTES
    for r in rows:
        dt=datetime.fromisoformat(r["timestamp"])
        bucket=dt.replace(minute=(dt.minute//interval)*interval,second=0,microsecond=0)
        key=bucket.isoformat(sep=" ")
        by[r["mote_id"]][key].append(r)
    out=[]
    for mote,items in sorted(by.items()):
        times=sorted(items)
        if not times: continue
        start=datetime.fromisoformat(times[0]); end=datetime.fromisoformat(times[-1])
        cur=start
        while cur<=end:
            key=cur.isoformat(sep=" ")
            samples=items.get(key,[])
            row=dict(samples[0]) if samples else {"timestamp":key,"mote_id":mote}
            row["timestamp"]=key
            row["mote_id"]=mote
            for ch in C.CHANNELS:
                row[ch]=med([number(sample.get(ch)) for sample in samples]) if samples else None
            # Preserve synthetic ground truth when a bucket contains one record.
            for ch in C.CHANNELS:
                true_key="true_"+ch
                if samples and true_key in samples[0]:
                    row[true_key]=med([number(sample.get(true_key)) for sample in samples])
                fault_key="fault_"+ch
                if samples and fault_key in samples[0]:
                    labels=[sample.get(fault_key,"") for sample in samples if sample.get(fault_key)]
                    row[fault_key]=labels[0] if labels else ""
            out.append(row)
            cur+=timedelta(minutes=interval)
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
    """Pure-Python Isolation Forest using the standard 256-row subsample."""
    n=len(features)
    if n<8: return [False]*n
    rng=random.Random(seed); dim=len(features[0]); sample_size=min(256,n)
    maxdepth=math.ceil(math.log2(sample_size))
    def build(indices,depth):
        if depth>=maxdepth or len(indices)<=1: return (len(indices),)
        candidates=[k for k in range(dim) if max(features[i][k] for i in indices)>min(features[i][k] for i in indices)]
        if not candidates: return (len(indices),)
        k=rng.choice(candidates); lo=min(features[i][k] for i in indices); hi=max(features[i][k] for i in indices)
        split=rng.uniform(lo,hi)
        left=[i for i in indices if features[i][k]<split]; right=[i for i in indices if features[i][k]>=split]
        if not left or not right: return (len(indices),)
        return (k,split,build(left,depth+1),build(right,depth+1))
    forest=[]
    population=list(range(n))
    for _ in range(trees):
        sample=rng.sample(population,sample_size)
        forest.append(build(sample,0))
    def c_factor(size):
        if size<=1:return 0.0
        h=math.log(size-1)+0.5772156649
        return 2*h-2*(size-1)/size
    norm=max(c_factor(sample_size),1e-9)
    def path(tree,row,depth=0):
        if len(tree)==1:return depth+c_factor(tree[0])
        return path(tree[2] if row[tree[0]]<tree[1] else tree[3],row,depth+1)
    scores=[2**(-sum(path(t,row) for t in forest)/trees/norm) for row in features]
    ranked=sorted(range(n),key=lambda i:scores[i],reverse=True)
    count=max(1,min(n,int(math.ceil(n*contamination))))
    chosen=set(ranked[:count])
    return [i in chosen for i in range(n)]



def _features(rows,ch,vals):
    """Build deterministic temporal/context features for one mote/channel."""
    out=[]
    for i,x in enumerate(vals):
        prev=vals[max(0,i-3):i]
        nxt=vals[i+1:min(len(vals),i+4)]
        local=med(prev+nxt)
        ts=rows[i].get("timestamp","")
        try:
            dt=datetime.fromisoformat(ts); hour=dt.hour+dt.minute/60
        except (TypeError,ValueError): hour=0.0
        out.append([float(x or 0.0),float((x-local) if x is not None and local is not None else 0.0),
                    float(local or 0.0),math.sin(2*math.pi*hour/24)])
    return out

def range_flags(vals,ch):
    lo,hi=C.PHYSICAL_RANGE[ch]
    return [x is not None and (x<lo or x>hi) for x in vals]

def _spatial_flags(rows,ch,vals,window=C.SPATIAL_WINDOW):
    groups=defaultdict(list)
    for i,r in enumerate(rows): groups[r["timestamp"]].append(i)
    ratios=[]; cross={}
    for ts,idx in groups.items():
        peers=[vals[j] for j in idx if vals[j] is not None]
        cross[ts]=med(peers)
        if ch=="light" and cross[ts] is not None and cross[ts]>100:
            ratios.extend(vals[j]/cross[ts] for j in idx if vals[j] is not None)
    typical=med(ratios) if ratios else None
    residual=[None]*len(vals)
    for ts,idx in groups.items():
        c=cross[ts]
        if c is None: continue
        for i in idx:
            x=vals[i]
            if x is None: continue
            if ch=="light":
                if c>100 and typical is not None:
                    residual[i]=(x-c*typical)/(c+50.0)
            else:
                peers=[vals[j] for j in idx if j!=i and vals[j] is not None]
                peer=med(peers)
                if peer is not None: residual[i]=x-peer
    valid=[x for x in residual if x is not None]
    center=med(valid); mad=med([abs(x-center) for x in valid]) if center is not None else None
    scale=max(1.4826*(mad or 0.0),0.02 if ch=="light" else 0.15)
    return [x is not None and center is not None and abs(x-center)>C.SPATIAL_NSIGMA*scale for x in residual]

def impute(vals, flags=None, spatial=None, short_gap=C.SHORT_GAP):
    """Interpolate short missing/flagged runs; use robust global fallback for long runs."""
    n=len(vals); bad=list(flags or [False]*n)
    if len(bad)!=n: raise ValueError("flags and values must have equal lengths")
    out=list(vals); invalid=[x is None or bad[i] for i,x in enumerate(vals)]
    good=[x for i,x in enumerate(vals) if not invalid[i]]
    fallback=med(good)
    i=0
    while i<n:
        if not invalid[i]: i+=1; continue
        start=i
        while i<n and invalid[i]: i+=1
        end=i; left=out[start-1] if start>0 and not invalid[start-1] else None
        right=out[end] if end<n and not invalid[end] else None
        length=end-start
        for j in range(start,end):
            if length<=short_gap and left is not None and right is not None:
                out[j]=left+(right-left)*(j-start+1)/(length+1)
            elif spatial is not None and j<len(spatial) and spatial[j] is not None:
                out[j]=spatial[j]
            else: out[j]=fallback
    return out

class CleaningPipeline:
    METHODS=("range","hampel","stuck","spatial","iforest")
    def __init__(self,methods=None):
        self.methods=tuple(methods or self.METHODS)
        unknown=set(self.methods)-set(self.METHODS)
        if unknown: raise ValueError("Unknown detection methods: "+", ".join(sorted(unknown)))
    def run(self,raw_rows):
        rows=regularise(raw_rows)
        cleaned=[dict(r) for r in rows]
        flags={ch:[False]*len(rows) for ch in C.CHANNELS}
        reasons={ch:[[] for _ in rows] for ch in C.CHANNELS}
        by_mote=defaultdict(list)
        for i,r in enumerate(rows): by_mote[r["mote_id"]].append(i)
        for ch in C.CHANNELS:
            all_values=[number(r.get(ch)) for r in rows]
            spatial_all=_spatial_flags(rows,ch,all_values) if "spatial" in self.methods else [False]*len(rows)
            for indices in by_mote.values():
                vals=[number(rows[i].get(ch)) for i in indices]
                local_rows=[rows[i] for i in indices]
                detected={name:[False]*len(indices) for name in self.METHODS}
                if "range" in self.methods: detected["range"]=range_flags(vals,ch)
                if "hampel" in self.methods: detected["hampel"]=hampel_flags(vals)
                if "stuck" in self.methods: detected["stuck"]=stuck_flags(vals,ch)
                if "spatial" in self.methods: detected["spatial"]=[spatial_all[i] for i in indices]
                if "iforest" in self.methods:
                    feat=_features(local_rows,ch,vals)
                    valid=[i for i,x in enumerate(vals) if x is not None]
                    if len(valid)>=8:
                        scored=_iforest_flags([feat[i] for i in valid],seed=C.RANDOM_STATE+int(rows[indices[0]]["mote_id"])+C.CHANNELS.index(ch))
                        for j,k in enumerate(valid): detected["iforest"][k]=scored[j]
                for j,global_i in enumerate(indices):
                    names=[name for name in self.methods if detected[name][j]]
                    if vals[j] is None: names.append("missing")
                    if names:
                        flags[ch][global_i]=True; reasons[ch][global_i]=names
                # Exclude physically impossible values and detector outliers before imputation.
                bad=[flags[ch][i] for i in indices]
                repaired=impute(vals,bad)
                for j,global_i in enumerate(indices):
                    cleaned[global_i][ch]=repaired[j]
        report={}
        for ch in C.CHANNELS:
            report[ch]={"readings":len(rows),"flagged":sum(flags[ch]),"missing":sum(r.get(ch) is None for r in rows),
                        "flagged_pct":round(100*sum(flags[ch])/max(1,len(rows)),2)}
        self.last_reasons=reasons
        return rows,cleaned,flags,report

def to_long(rows,cleaned,flags):
    out=[]
    for i,r in enumerate(rows):
        for ch in C.CHANNELS:
            raw=number(r.get(ch)); bad=bool(flags[ch][i])
            reasons=[]
            if raw is None: reasons.append("missing")
            if bad:
                # Reconstruct detector reason labels from the pipeline's last run.
                reasons.extend(getattr(_ACTIVE_PIPELINE,"last_reasons",{}).get(ch,[[] for _ in rows])[i])
            out.append({"timestamp":r["timestamp"],"mote_id":r["mote_id"],"channel":ch,
                        "raw":raw,"cleaned":number(cleaned[i].get(ch)),"flagged":int(bad),
                        "missing":int(raw is None),"reasons":reasons})
    return out

_ACTIVE_PIPELINE=None

def _pipeline_run(self,raw_rows):
    global _ACTIVE_PIPELINE
    result=_original_pipeline_run(self,raw_rows)
    _ACTIVE_PIPELINE=self
    return result
_original_pipeline_run=CleaningPipeline.run
CleaningPipeline.run=_pipeline_run

def stream_clean(rows):
    """Causal online path: range and recent-history Hampel/stuck checks only."""
    ordered=sorted(rows,key=lambda r:(r["timestamp"],r["mote_id"]))
    history=defaultdict(lambda:deque(maxlen=max(C.HAMPEL_WINDOW,C.STUCK_MIN_RUN)+1))
    out=[]
    for r in ordered:
        for ch in C.CHANNELS:
            x=number(r.get(ch)); key=(r["mote_id"],ch); h=list(history[key])
            reasons=[]
            if x is None: reasons.append("missing")
            elif x<C.PHYSICAL_RANGE[ch][0] or x>C.PHYSICAL_RANGE[ch][1]: reasons.append("range")
            elif len(h)>=5:
                center=med(h); mad=med([abs(v-center) for v in h])
                if mad is not None and abs(x-center)>max(4*1.4826*mad,0.5): reasons.append("online_hampel")
                if len(h)>=C.STUCK_MIN_RUN-1 and all(v==x for v in h[-(C.STUCK_MIN_RUN-1):]): reasons.append("stuck")
            clean=x
            if reasons and h: clean=med(h)
            elif x is None: clean=med(h)
            if x is not None and "range" not in reasons: history[key].append(x)
            out.append({"timestamp":r["timestamp"],"mote_id":r["mote_id"],"channel":ch,
                        "raw":x,"cleaned":clean,"flagged":int(bool(reasons)),"missing":int(x is None),"reasons":reasons})
    return out

def open_db(path="results/audit.db"):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS readings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp TEXT NOT NULL,mote_id INTEGER NOT NULL,
        channel TEXT NOT NULL,raw REAL,cleaned REAL,flagged INTEGER NOT NULL DEFAULT 0,
        missing INTEGER NOT NULL DEFAULT 0,reasons TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_readings_channel ON readings(channel)")
    con.commit()
    return con

def save_results(con,results):
    con.executemany("""INSERT INTO readings(timestamp,mote_id,channel,raw,cleaned,flagged,missing,reasons)
        VALUES(:timestamp,:mote_id,:channel,:raw,:cleaned,:flagged,:missing,:reasons)""",
        [{**r,"reasons":",".join(r.get("reasons",[])) if isinstance(r.get("reasons"),(list,tuple)) else str(r.get("reasons",""))} for r in results])
    con.commit()

def summary(con):
    return con.execute("""SELECT channel,COUNT(*),SUM(flagged),SUM(missing),
        ROUND(100.0*SUM(flagged)/COUNT(*),2) FROM readings GROUP BY channel ORDER BY channel""").fetchall()

def explain(con,mote_id,channel):
    return con.execute("""SELECT timestamp,raw,cleaned,flagged,missing,reasons FROM readings
        WHERE mote_id=? AND channel=? ORDER BY timestamp""",(mote_id,channel)).fetchall()

def load_intel_lab(path,motes=None):
    """Load Intel Berkeley Lab whitespace records: date time epoch mote temp humidity light voltage."""
    import gzip
    opener=gzip.open if str(path).lower().endswith(".gz") else open
    out=[]
    with opener(path,"rt",encoding="utf-8",errors="replace") as f:
        for line in f:
            parts=line.strip().split()
            if len(parts)<8: continue
            try:
                date,time=parts[0],parts[1]
                mote=int(parts[3])
                if motes is not None and mote not in motes: continue
                stamp=datetime.fromisoformat(date+"T"+time).isoformat(sep=" ")
                vals=[number(v) for v in parts[4:8]]
                out.append({"timestamp":stamp,"mote_id":mote,**dict(zip(C.CHANNELS,vals))})
            except (ValueError,IndexError): continue
    if not out: raise ValueError("No Intel Lab records found. Expected: date time epoch mote temperature humidity light voltage.")
    return sorted(out,key=lambda r:(r["timestamp"],r["mote_id"]))

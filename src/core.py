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


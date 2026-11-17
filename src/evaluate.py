"""Evaluation helpers for simulator output."""
import math
from . import config as C
from .simulator import FAULT_TYPES

def detection_scores(rows,flags,channels=C.CHANNELS):
    result=[]
    for ch in channels:
        tp=fp=fn=0
        for i,r in enumerate(rows):
            lab=r.get("fault_"+ch,"")
            truth=bool(lab and lab!="missing")
            pred=bool(flags[ch][i] and r.get(ch) is not None)
            tp+=truth and pred; fp+=(not truth) and pred; fn+=truth and (not pred)
        p=tp/(tp+fp) if tp+fp else 0; rec=tp/(tp+fn) if tp+fn else 0
        result.append({"channel":ch,"precision":p,"recall":rec,"f1":2*p*rec/(p+rec) if p+rec else 0,"tp":tp,"fp":fp,"fn":fn})
    return result

def recall_by_fault(rows,flags,channels=C.CHANNELS):
    out={}
    for ft in FAULT_TYPES:
        if ft=="missing": continue
        hit=tot=0
        for ch in channels:
            for i,r in enumerate(rows):
                if r.get("fault_"+ch)==ft: tot+=1; hit+=bool(flags[ch][i])
        out[ft]=hit/tot if tot else float("nan")
    return out

def value_rmse(rows,cleaned,channels=C.CHANNELS):
    out=[]
    for ch in channels:
        raw_err=[]; clean_err=[]
        for i,r in enumerate(rows):
            truth=r.get("true_"+ch)
            if truth is not None:
                if r.get(ch) is not None: raw_err.append((r[ch]-truth)**2)
                if cleaned[i].get(ch) is not None: clean_err.append((cleaned[i][ch]-truth)**2)
        a=math.sqrt(sum(raw_err)/len(raw_err)) if raw_err else float("nan")
        b=math.sqrt(sum(clean_err)/len(clean_err)) if clean_err else float("nan")
        out.append({"channel":ch,"raw_rmse":a,"cleaned_rmse":b,"improvement_%":100*(1-b/a) if a else 0})
    return out

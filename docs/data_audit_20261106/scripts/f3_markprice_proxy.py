# -*- coding: utf-8 -*-
"""模擬器計資金費用的價格 = 結算時刻那根 1H K 棒的開盤價(d2_sim.apply_funding: open_px);官方實際用 markPrice。比較兩者差距(只讀 raw_api 內已存的官方回應 + 本機 D3 K 線)。"""
import glob, json, os, pickle, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RAW_API, D3P, OUT, to_unified
H = 3600000; d3 = pickle.load(open(D3P, 'rb'))['candles']; res = {}; allr = []
for f in sorted(glob.glob(os.path.join(RAW_API, 'funding_*W[2-6]*.json'))):
    sid = os.path.basename(f).split('_')[1]; u = to_unified(sid); op = {r[0]: r[1] for r in d3[(u, '1h')]}; rel = []
    for x in json.load(open(f)):
        if not x.get('markPrice'): continue
        t = int(x['fundingTime']); o = op.get(t - t % H)
        if o: rel.append(abs(float(x['markPrice']) / o - 1))
    if rel: res.setdefault(sid, []).extend(rel); allr += rel
out = {k: {'n': len(v), 'mean_abs_rel_diff': sum(v) / len(v), 'max_abs_rel_diff': max(v)} for k, v in res.items()}; out['ALL'] = {'n': len(allr), 'mean_abs_rel_diff': sum(allr) / len(allr), 'max_abs_rel_diff': max(allr)}
print(json.dumps(out, indent=1)); json.dump(out, open(os.path.join(OUT, 'f3_markprice_proxy.json'), 'w'), indent=1)

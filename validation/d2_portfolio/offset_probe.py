"""D2:用機器人日誌每輪的「保證金≈」在空手時(= 錢包)檢驗對帳差額何時出現。"""
import json, re, datetime, bisect, statistics, collections, os, sys
sys.path.insert(0, 'validation/d1_live')
from d1_trips import local_to_ms
inc = json.load(open('validation/d1_live/raw/income.json')); T = json.load(open('validation/d1_live/raw/trips_enriched.json'))['trips']
ev = sorted((int(x['time']), float(x['income'])) for x in inc if x['incomeType'] in ('REALIZED_PNL', 'COMMISSION', 'FUNDING_FEE'))
cum = []; c = 0
for t, v in ev: c += v; cum.append(c)
ts = [t for t, _ in ev]
def wallet(t):
    i = bisect.bisect_right(ts, t) - 1
    return (152.49132399 if t >= 1781260860000 else 0) + (156.389344 if t >= 1787534820000 else 0) + (cum[i] if i >= 0 else 0)
pts = []; BOT = r'C:\Users\User\發大財\順勢交易機器人'
for fn in ('portfolio.log.old', 'portfolio.log'):
    for line in open(os.path.join(BOT, fn), encoding='utf-8', errors='replace'):
        m = re.match(r'\[(\d{4}-\d\d-\d\d [\d:]+)\] 保證金≈([\d.]+)', line)
        if m: pts.append((local_to_ms(m.group(1)), float(m.group(2))))
print('log margin points', len(pts))
def open_at(t): return sum(1 for x in T if x['entry_ts'] <= t <= (x['exit_ts'] if x['closed'] else 10**15))
flat = [(t, v) for t, v in pts if open_at(t) == 0]; print('flat samples', len(flat))
byday = collections.defaultdict(list)
for t, v in flat: byday[datetime.datetime.utcfromtimestamp(t / 1000).strftime('%m-%d')].append(v - wallet(t))
for d, v in sorted(byday.items()): print(d, len(v), round(statistics.mean(v), 4), round(min(v), 4), round(max(v), 4))
allr = [v - wallet(t) for t, v in pts]; print('all points mean(cap - wallet)', round(statistics.mean(allr), 3), 'sd', round(statistics.pstdev(allr), 3))

# -*- coding: utf-8 -*-
"""Record REAL job events from the running site into static/prototype/traces/traces.js (for replay in the Research Core prototype).
Each trace is produced by actually running the analysis on this machine; nothing is simulated or edited.
usage: python record_trace.py <base_url>"""
import json, sys, time, uuid, datetime, urllib.request, urllib.parse, os

BASE = sys.argv[1].rstrip('/')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'static', 'prototype', 'traces', 'traces.js')

RUNS = [
    ('analyze-2330', '單一標的分析 · 2330.TW(日線,DMI/ADX)', '/api/analyze', dict(symbol='2330.TW', strategy='diadx', period='2y', timeframe='1d')),
    ('best-sol-4h', '最佳策略排名 · SOL-USD 4H(加密,真實排名)', '/api/best_strategy', dict(symbol='SOL-USD', period='2y', timeframe='4h', use_oos='1')),
    ('error-bad-symbol', '資料取得失敗 · 無效代號(真實錯誤)', '/api/analyze', dict(symbol='ZZZZ9999', strategy='diadx', period='2y', timeframe='1d')),
]


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=600) as r: return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read().decode('utf-8'))


def summarize(path, d):
    if d.get('error'): return False, '失敗:' + d['error']
    if 'metrics' in d:
        m = d['metrics']; v = d.get('validation') or {}; o = v.get('oos') if v.get('available') else None
        t = {'insufficient': '樣本不足', 'preliminary': '初步觀察', 'evaluable': '可進一步評估'}
        return True, '扣成本報酬 %s%% · 淨 PF %s · 最大回撤 %s%% · %s 筆' % (m['totalReturn'], m['pf'] if m['tradeCount'] else '—', m['maxDD'], m['tradeCount']) + (' · 樣本外 %s 筆(%s)' % (o['trades'], t.get(o['tier'], o['tier'])) if o else '')
    top = (d.get('results') or [None])[0]
    return True, '共測試 %s 個策略,入選 %s 名' % (d['total_tested'], len(d['results'])) + (';第 1 名 %s(樣本外 %s 筆)' % (top['name'], top['oos']['trades'] if top.get('oos') else 0) if top else '')


traces = {}
for key, label, path, q in RUNS:
    job = 'rec-' + uuid.uuid4().hex[:16]
    t0 = time.time()
    code, d = get(BASE + path + '?' + urllib.parse.urlencode(dict(q, job=job)))
    _, ev = get(BASE + '/api/job_events?job=%s&after=0' % job)
    ok, summ = summarize(path, d)
    traces[key] = {'meta': {'label': label, 'recordedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'query': {k: v for k, v in q.items()}, 'wallSeconds': round(time.time() - t0, 1), 'events': len(ev['events'])},
                   'events': ev['events'], 'result': {'ok': ok, 'summary': summ}}
    print(key, 'http', code, 'events', len(ev['events']), 'wall', round(time.time() - t0, 1), 's', summ[:90])

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('/* Real events recorded from this machine by validation/stage3_ui/tools/record_trace.py (not simulated, not edited). */\n')
    f.write('window.RC_TRACES = ' + json.dumps(traces, ensure_ascii=False, separators=(',', ':')) + ';\n')
print('wrote', os.path.normpath(OUT), os.path.getsize(OUT), 'bytes')

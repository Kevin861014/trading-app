# -*- coding: utf-8 -*-
"""C3:用離線的真實 K 線快照(BTC、SOL、2330.TW、AAPL)產生各情境的真實 API 回應(正常、資料過期、樣本不足、沒有交易),
並用 /api/rule_summary 整理成摘要,存成 scenarios.json / scenarios.md;截圖時把『真實回應』餵給真實的前端渲染器。"""
import datetime, json, os, sys, warnings
from unittest import mock
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A

S = json.load(open(os.path.join(ROOT, 'validation', 'stage3_ui', 'C2', 'snapshot.json'))); ROWS = S['rows']
NOW = datetime.datetime.fromisoformat(S['__now__']).replace(microsecond=0) - datetime.timedelta(hours=8)
A.CCXT_AVAILABLE = True; A.fetch_data = lambda s, st, interval='1d': ROWS['%s|%s' % (s, interval)]
c = A.app.test_client()
CASES = [('normal_BTC', 'BTC/USDT', '4h', 'sixline', '1d,4h', 0, 'up,transition'), ('normal_SOL', 'SOL/USDT', '4h', 'sixline', '1d,4h', 0, ''),
         ('insufficient_2330', '2330.TW', '1d', 'diadx', '1d', 0, ''), ('insufficient_AAPL', 'AAPL', '1d', 'tsmom', '1d', 0, ''),
         ('stale_BTC', 'BTC/USDT', '4h', 'sixline', '1d,4h', 12, ''), ('notrades_BTC', 'BTC/USDT', '4h', 'adx_di_trend', '1d,4h', 0, '', '1y')]
out = {}; md = ['# C3 情境摘要（離線快照的真實 API 回應 → /api/rule_summary）', '']
for case in CASES:
    name, sym, tf, st, tfs, shift, allow = case[:7]; period = case[7] if len(case) > 7 else '2y'
    A._utcnow = lambda sh=shift: NOW + datetime.timedelta(days=sh)
    q = dict(symbol=sym, timeframe=tf, strategy=st, period=period); q.update(allow=allow, basis='own') if allow else None
    study = c.get('/api/regime_study', query_string=q).get_json(); mtf = c.get('/api/mtf', query_string=dict(symbol=sym, tfs=tfs)).get_json()
    s = c.post('/api/rule_summary', json={'study': study, 'mtf': mtf, 'trials': {'count': 1, 'revealed': 0} if allow else {}}).get_json()
    out[name] = {'study': study, 'mtf': mtf, 'summary': s}
    md += ['## %s（%s %s %s）— %s' % (name, sym, tf, st, s['headline']['levelLabel']), '', '**%s**' % s['headline']['text'], '']
    for sec in s['sections']:
        md.append('### ' + sec['title'])
        md += ['- ' + it['text'] + '  `' + ', '.join(e['path'] for e in it['evidence'][:3]) + ('…' if len(it['evidence']) > 3 else '') + '`' for it in sec['items']]
        md.append('')
    print(name, s['headline']['level'], study['overall']['all']['trades'], flush=True)
json.dump(out, open(os.path.join(HERE, 'scenarios.json'), 'w', encoding='utf-8'), ensure_ascii=False, default=str)
open(os.path.join(HERE, 'scenarios.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')

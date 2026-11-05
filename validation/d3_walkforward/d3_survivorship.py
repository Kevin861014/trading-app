# -*- coding: utf-8 -*-
"""D3:倖存者偏誤的量化(公開 exchangeInfo;只有目前仍列在清單上的合約,已完全移除的下架合約看不到)。"""
import datetime, json, os, warnings
warnings.filterwarnings('ignore')
import ccxt
HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.join(HERE, 'results')
ex = ccxt.binanceusdm({'enableRateLimit': True})
info = ex.fapiPublicGetExchangeInfo()['symbols']
perp = [s for s in info if s.get('contractType') == 'PERPETUAL' and s.get('quoteAsset') == 'USDT']
ms = lambda y, m, d: int(datetime.datetime(y, m, d, tzinfo=datetime.timezone.utc).timestamp() * 1000)
CUR = {c['symbol'].replace('/', '') for c in json.load(open(r'C:\Users\User\發大財\順勢交易機器人\config.portfolio.json', encoding='utf-8'))['combos']}
def cnt(cut):
    rows = [s for s in perp if int(s.get('onboardDate') or 0) and int(s['onboardDate']) < cut]
    st = {}
    for s in rows: st[s['status']] = st.get(s['status'], 0) + 1
    return {'listed_before': len(rows), 'by_status_now': st}
out = {'asof_perpetual_count': len(perp), 'status_now': {k: sum(1 for s in perp if s['status'] == k) for k in {s['status'] for s in perp}},
       'onboarded_before_2021-01-01': cnt(ms(2021, 1, 1)), 'onboarded_before_2023-07-01': cnt(ms(2023, 7, 1)), 'onboarded_before_2024-03-01': cnt(ms(2024, 3, 1)),
       'our_23_status_now': {s['symbol']: s['status'] for s in perp if s['symbol'] in CUR},
       'our_23_onboard_before_2023-07-01': sorted(s['symbol'] for s in perp if s['symbol'] in CUR and int(s['onboardDate']) < ms(2023, 7, 1)),
       'note': 'SETTLING = 正在下架/結算中的合約(仍在清單上)。已經從清單消失的合約公開 API 看不到,所以「當時存在、後來消失」的幣種無法納入;這會讓任何由今天清單挑出的組合在歷史上顯得比真實母體好。'}
json.dump(out, open(os.path.join(RES, 'survivorship.json'), 'w'), ensure_ascii=False, indent=1); print(json.dumps(out, ensure_ascii=False, indent=1))

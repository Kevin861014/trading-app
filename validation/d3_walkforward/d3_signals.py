# -*- coding: utf-8 -*-
"""D3:對完整歷史重算現行 23 組每根已收盤 K 棒的 (進場訊號, 出場訊號, ATR)(機器人用最近 400 根視窗;沿用 D2 的同一個函式,不重新開發)。輸出 raw/signals_long.pkl(不進版控)。"""
import concurrent.futures as cf, json, os, pickle, sys, time, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'validation', 'd2_portfolio')); sys.path.insert(0, ROOT); os.chdir(ROOT)
from d2_signals import work


def main():
    d = pickle.load(open(os.path.join(RAW, 'long.pkl'), 'rb')); cands = d['candles']
    CUR = json.load(open(r'C:\Users\User\發大財\順勢交易機器人\config.portfolio.json', encoding='utf-8'))['combos']
    args = [(c['symbol'], c['timeframe'], c['strategy'], cands[(c['symbol'], c['timeframe'])], 0) for c in CUR if cands.get((c['symbol'], c['timeframe']))]
    res = {}; t0 = time.time()
    with cf.ProcessPoolExecutor(max_workers=3) as ex:
        for key, out in ex.map(work, args):
            res[key] = out; print(key, len(out), '%.0fs' % (time.time() - t0), flush=True)
    pickle.dump(res, open(os.path.join(RAW, 'signals_long.pkl'), 'wb')); print('saved', len(res))


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""D2:預先計算每個組合『每一根已收盤 K 棒』的 (進場訊號, 出場訊號, ATR)。
機器人每輪用最近 400 根已收盤 K 棒呼叫策略的 build,只看最後一根(el[-1]/xl[-1]/ATR[-1]),所以這三個值只取決於『以該棒結尾的 400 根視窗』,與情境無關。
這裡用網站同一份策略程式(與機器人逐字相同),逐棒重算一次,存成 raw/signals.pkl,之後所有情境共用(不重複運算)。"""
import concurrent.futures as cf, json, os, pickle, sys, time, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); os.chdir(ROOT)
WIN = 400


def work(args):
    sym, tf, strat, rows, start_ms = args
    import app as A, sim
    s = A.STRATS[strat]; out = {}
    for i in range(WIN - 1, len(rows)):
        if rows[i][0] < start_ms: continue
        w = rows[i - WIN + 1:i + 1]
        O = [r[1] for r in w]; H = [r[2] for r in w]; L = [r[3] for r in w]; C = [r[4] for r in w]; V = [(r[5] if len(r) > 5 else 0.0) for r in w]
        try: res = s['build'](O, H, L, C, V, tf); el, xl = res[0], res[1]
        except Exception: continue
        at = sim.atr(H, L, C, 14)[-1]
        out[rows[i][0]] = (bool(el[-1]), bool(xl[-1]), at)
    return (sym, tf, strat), out


def main():
    d = pickle.load(open(os.path.join(RAW, 'data.pkl'), 'rb')); cands = d['candles']
    CUR = json.load(open(r'C:\Users\User\發大財\順勢交易機器人\config.portfolio.json', encoding='utf-8'))['combos']
    ms = lambda y, m, dd: int(__import__('datetime').datetime(y, m, dd, tzinfo=__import__('datetime').timezone.utc).timestamp() * 1000)
    jobs = []; seen = set()
    for c in CUR:                                            # 現行 23 組:整個擴充期間(2025-04-20 起)
        k = (c['symbol'], c['timeframe'], c['strategy']); seen.add(k); jobs.append((k, ms(2025, 4, 20)))
    extra = [('PAXG/USDT', '4h', 'trix_signal'), ('SOL/USDT', '4h', 'ema_8_21'), ('PYTH/USDT', '4h', 'week_hl'), ('AAVE/USDT', '4h', 'ppo_cross'), ('IMX/USDT', '4h', 'ema50_200_adx'),
             ('BNB/USDT', '4h', 'cmf'), ('XRP/USDT', '1h', 'cci'), ('SOL/USDT', '4h', 'force'), ('PAXG/USDT', '4h', 'supertrend'), ('ARB/USDT', '4h', 'ttm'), ('UNI/USDT', '4h', 'cci'), ('PAXG/USDT', '4h', 'lrs')]
    for k in extra:
        if k not in seen: jobs.append((k, ms(2026, 5, 20)))      # 舊設定/歸屬候選:只算實盤期間(2026-06 起,多留一點暖機)
    args = [(k[0], k[1], k[2], cands[(k[0], k[1])], st) for k, st in jobs if cands.get((k[0], k[1]))]
    res = {}; t0 = time.time()
    with cf.ProcessPoolExecutor(max_workers=3) as ex:
        for key, out in ex.map(work, args):
            res[key] = out; print(key, len(out), '%.0fs' % (time.time() - t0), flush=True)
    pickle.dump(res, open(os.path.join(RAW, 'signals.pkl'), 'wb')); print('saved', len(res))


if __name__ == '__main__':
    main()

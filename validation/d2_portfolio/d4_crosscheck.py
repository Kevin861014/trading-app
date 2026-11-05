# -*- coding: utf-8 -*-
"""D4 一次性交叉驗證(離線):用 D3 的真實歷史 K 棒/資金費率,當作『假行情來源』逐步餵給 D4 引擎(多次 tick),
再和『直接呼叫 D2 模擬器、用 D3 預先算好的訊號』的結果逐筆比對。證明 D4 的增量流程沒有改變 D2 的計算。
不連網、不寫 raw、結果只寫到暫存目錄;需要 validation/d3_walkforward/raw/long.pkl 與 signals_long.pkl(不在 git 內)。"""
import datetime, os, pickle, shutil, stat, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'paper_trading')); sys.path.insert(0, os.path.join(ROOT, 'validation', 'd2_portfolio')); sys.path.insert(0, ROOT)
import d4_engine as E
import d2_sim as S
from d4_store import read_jsonl
RAW = os.path.join(ROOT, 'validation', 'd3_walkforward', 'raw')
ms = lambda y, m, d, h=0: int(datetime.datetime(y, m, d, h, tzinfo=datetime.timezone.utc).timestamp() * 1000)


class ReplayFeed:
    def __init__(self, data, now): self.d = data; self.now = now
    def now_ms(self): return self.now
    def klines(self, sid, tf, start):
        s = self.sym[sid]; step = E.STEP[tf]; return [r[:6] for r in self.d['candles'][(s, tf)] if r[0] >= start and r[0] + step <= self.now - 5000]
    def funding(self, sid, start): return [(t, x) for t, x in self.d['funding'][self.sym[sid]] if t >= start and t <= self.now - 1]
    def markets(self, syms): return {s: self.d['markets'][s] for s in syms}


def main():
    d = pickle.load(open(os.path.join(RAW, 'long.pkl'), 'rb')); sigs = pickle.load(open(os.path.join(RAW, 'signals_long.pkl'), 'rb'))
    from d2_common import cfg_combos
    combos = cfg_combos('config.portfolio.json'); T0 = ms(2026, 9, 1); NOW = ms(2026, 10, 12, 5)
    feed = ReplayFeed(d, NOW); feed.sym = {v['id']: k for k, v in d['markets'].items()}
    tmp = tempfile.mkdtemp(prefix='d4x_'); exp = os.path.join(tmp, 'e')
    E.init_experiment(exp, 'xcheck', T0, combos, feed.markets(sorted({c['symbol'] for c in combos}) + ['BTC/USDT']), T0 - 86400000, {'note': 'crosscheck'})
    last = None
    for n in (ms(2026, 9, 3, 7), ms(2026, 9, 20, 12), NOW):
        feed.now = n; last = E.tick(exp, feed); print('tick', last['wall_utc'], 'T1', last['T1_utc'], 'new', last.get('new_records'), 'div', last.get('divergences'), 'errors', last['errors'], 'gaps', last['gaps'])
    snap = E.Exp(exp).load_snapshot(); T1 = last['T1']; M = S.Market(d); P = S.default_params({k: tuple(v) for k, v in snap['exit_params'].items()}, **snap['params'])
    ex = E.Exp(exp); ev = read_jsonl(ex.events)[0]; ok = True
    for sc in ('A', 'B'):
        cs = snap['scenarios'][sc]['combos']; ref = S.run(M, sigs, [(T0, cs)], T0, T1, P, snap['initial_equity'])
        exits = {e['id']: e for e in ev if e['scenario'] == sc and e['type'] == 'EXIT'}; mine = sorted((e['key'], e['entry_ts'], e['decision_ts'], round(e['net'], 6), round(e['sim_fill'], 8)) for e in exits.values())
        theirs = sorted((t['key'], t['entry_ts'], t['exit_ts'], round(t['net'], 6), round(t['exit_fill'], 8)) for t in ref['trades'])
        marks = read_jsonl(ex.marks(sc))[0]; me = [(m['h'], round(m['equity'], 6)) for m in marks]; re_ = [(h, round(e, 6)) for h, e, *_ in ref['marks']]
        same_t = mine == theirs; same_m = me == re_; ok &= same_t and same_m
        print(sc, 'closed trades D4 %d vs D2 %d identical=%s | hourly equity marks %d identical=%s | final equity D2 %.6f' % (len(mine), len(theirs), same_t, len(me), same_m, ref['equity_end']))
    shutil.rmtree(tmp, onerror=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
    print('CROSSCHECK', 'PASS' if ok else 'FAIL'); return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

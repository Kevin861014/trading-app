# -*- coding: utf-8 -*-
"""D4 單次 tick(跑一次就結束,不常駐):抓新收盤的 K 棒/資金費率 → 驗證實驗雜湊 → 確定性重播 A、B → 只附加新的紀錄。
用法:  python paper_trading/d4_tick.py --dir paper_trading/experiments/d4-v1
可以隨時重複執行或在中斷後再執行:同一事件 id 不會重複記帳;與既有紀錄不一致的只會寫進 ledger/divergences.jsonl,不覆蓋原始紀錄。
這個程式只打幣安公開行情端點,沒有金鑰、沒有任何交易/私有 API,也不讀寫機器人的資料夾。"""
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import d4_engine as E
from d4_store import LockBusy


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); ap.add_argument('--dir', required=True)
    a = ap.parse_args(argv)
    from d4_feed import BinanceFeed
    try: r = E.tick(a.dir, BinanceFeed())
    except E.ManifestMismatch as e: print('REFUSED:', e); return 3
    except LockBusy as e: print('SKIPPED:', e); return 4
    print('tick', r['tick_id'], '| processed through', r.get('T1_utc'), '| new bars', r['new_bars'], '| new records', r.get('new_records'), '| unchanged', r.get('unchanged_events'), '| divergences', r.get('divergences'))
    for k in ('A', 'B'):
        if k in r: print(' ', k, 'equity', r[k]['equity_end'], 'closed', r[k]['trades_closed'], 'open', r[k]['open'])
    if r['errors']: print('errors:', r['errors'])
    if r['gaps']: print('gaps:', r['gaps'])
    return 0


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""D4 建立『固定實驗版本』:A/B 設定快照 + 清單雜湊(MANIFEST)。只做一次;目錄已存在就拒絕(不覆蓋)。
用法:
  python paper_trading/d4_init.py --preview  --id d4-v1 --start "2026-11-09 00:00"      只印出/寫出預覽,不建立實驗
  python paper_trading/d4_init.py --id d4-v1 --start "2026-11-09 00:00"                建立正式實驗目錄(需要使用者確認後才執行)
--start 是 UTC 整點,必須在『現在之後』;之前的歷史只用來指標暖機。這個程式只打幣安公開的 exchangeInfo(取最小下單量/步長),不用任何金鑰。"""
import argparse, datetime, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import d4_engine as E
from d4_store import sha256_file


def parse_start(s):
    dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M').replace(tzinfo=datetime.timezone.utc); ms = int(dt.timestamp() * 1000)
    if ms % E.HOUR: raise ValueError('--start must be on a UTC hour boundary')
    return ms


def load_combos(path):
    j = json.load(open(path, encoding='utf-8'))
    return [{'symbol': c['symbol'], 'timeframe': c['timeframe'], 'strategy': c['strategy'], 'weight': c.get('weight', 1)} for c in j['combos']]       # 只取組合清單,不碰其他欄位


def make(exp_dir, exp_id, start_ms, combos_path, feed, preview=False, allow_dirty=False, now_ms=None):
    combos = load_combos(combos_path); syms = sorted({c['symbol'] for c in combos}) + [E.REF_SYMBOL]
    markets = feed.markets(syms); missing = [s for s in syms if s not in markets]
    if missing: raise RuntimeError('markets missing from exchangeInfo: %s' % missing)
    created = int(now_ms if now_ms is not None else feed.now_ms())
    src = {'file': os.path.basename(combos_path), 'sha256': sha256_file(combos_path), 'combos': len(combos), 'note': '只讀取「組合清單」(交易對/週期/策略/權重);不含也不讀任何金鑰'}
    if preview:
        return E.build_snapshot(exp_id, start_ms, combos, markets, created, src)
    gi = E.git_info()
    if gi.get('tracked_paths_dirty') and not allow_dirty: raise RuntimeError('策略/模擬器/D4 程式有未提交的修改;請先 commit,讓實驗版本對應到一個固定的程式版本(測試用 --allow-dirty)')
    return E.init_experiment(exp_dir, exp_id, start_ms, combos, markets, created, src)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--id', required=True); ap.add_argument('--start', required=True, help='UTC "YYYY-MM-DD HH:00"'); ap.add_argument('--dir'); ap.add_argument('--combos-file')
    ap.add_argument('--preview', action='store_true'); ap.add_argument('--allow-dirty', action='store_true'); ap.add_argument('--out', help='--preview 時把預覽寫到這個檔')
    a = ap.parse_args(argv)
    from d4_feed import BinanceFeed
    feed = BinanceFeed(); exp_dir = a.dir or os.path.join(HERE, 'experiments', a.id); cf = a.combos_file or E.default_combos_source()
    r = make(exp_dir, a.id, parse_start(a.start), cf, feed, preview=a.preview, allow_dirty=a.allow_dirty)
    if a.preview:
        txt = json.dumps(r, ensure_ascii=False, indent=1, sort_keys=True)
        if a.out: open(a.out, 'w', encoding='utf-8').write(txt + '\n'); print('preview written:', a.out)
        print('A combos:', len(r['scenarios']['A']['combos']), '| B combos:', len(r['scenarios']['B']['combos']), '| B excluded:', r['scenarios']['B']['excluded'], '| sumw A/B:', r['scenarios']['A']['sumw'], r['scenarios']['B']['sumw'])
        print('(preview only — no experiment was created, nothing started)')
    else:
        print('experiment created:', exp_dir); print('snapshot sha256:', r['snapshot_sha256']); print('(nothing is running; use d4_tick.py to take a tick when you decide to start observing)')


if __name__ == '__main__':
    main()

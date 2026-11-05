# -*- coding: utf-8 -*-
"""D1 步驟 1:把幣安唯讀取得的成交(userTrades)與收支(income)整理成『來回交易(trip)』,並盡可能歸屬到策略。
全部是離線處理 raw/ 內的檔案 + 機器人日誌/設定的唯讀副本(只讀,不改);輸出 raw/trips.json。

歸屬等級(誠實標示,不把推測當事實):
  log      機器人日誌有該筆進場的『SYMBOL|tf|策略』紀錄(2026-10-24 之後)——可靠。
  single   這個幣在所有可得的設定/狀態紀錄裡只出現過一個有交易的組合——可靠(但仍是由設定檔推得,不是帳務直接標記)。
  swap     這個幣的策略在 2026-10-29 設定更換前後不同;更換時間用日誌重啟紀錄,更換後的進場有日誌 → log;更換前且在日誌範圍內 → log。
  unknown  這個幣在日誌之前曾換過策略(例如 BNB cmf→ttm、XRP cci→vortex、SOL force→ema_8_21、PAXG supertrend→trix_signal…),無法可靠歸屬 → 不分配給任何策略。
"""
import collections, datetime, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw')
BOT = r'C:\Users\User\發大財\順勢交易機器人'
TZ = 8 * 3600 * 1000            # 日誌與檔案時間是台北時間(UTC+8)


def local_to_ms(s):
    return int(datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) - TZ


def ms_str(ms): return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')


def load_logs():
    ev = []; starts = []
    for fn in ('portfolio.log.old', 'portfolio.log'):
        for line in open(os.path.join(BOT, fn), encoding='utf-8', errors='replace'):
            m = re.match(r'\[(\d{4}-\d\d-\d\d [\d:]+)\] (.*)', line.rstrip('\n'))
            if not m: continue
            t = local_to_ms(m.group(1)); body = m.group(2)
            if body.startswith('=== 多策略籃子機器人'):
                n = re.search(r'策略 (\d+) 個', body); starts.append((t, int(n.group(1)) if n else None)); continue
            e = re.match(r'\s*➜ (\S+)\|(\w+)\|(\S+) 該策略進場 目標量=([\d.]+) @≈([\d.]+)', body)
            if e: ev.append({'t': t, 'kind': 'entry', 'sym': e.group(1), 'tf': e.group(2), 'strat': e.group(3), 'qty': float(e.group(4)), 'px': float(e.group(5))}); continue
            x = re.match(r'\s*➜ (\S+)\|(\w+)\|(\S+) 該策略出場\((.*?)\)', body)
            if x: ev.append({'t': t, 'kind': 'exit', 'sym': x.group(1), 'tf': x.group(2), 'strat': x.group(3), 'reason': x.group(4)}); continue
            g = re.match(r'\s*⚠ (\S+)\|(\w+)\|(\S+) 交易所端部位已不存在', body)
            if g: ev.append({'t': t, 'kind': 'exchange_exit', 'sym': g.group(1), 'tf': g.group(2), 'strat': g.group(3), 'reason': '保護停損觸發或外部平倉'}); continue
            s = re.match(r'\s*🛡 (\S+) 已掛交易所端保護停損 @ ([\d.]+)', body)
            if s: ev.append({'t': t, 'kind': 'stop_set', 'sym': s.group(1), 'stop': float(s.group(2))})
    ev.sort(key=lambda e: e['t']); return ev, starts


def cfg_combos(fn):
    c = json.load(open(os.path.join(BOT, fn), encoding='utf-8'))
    return {x['symbol']: (x['timeframe'], x['strategy'], x.get('weight')) for x in c['combos']}


def main():
    inc = json.load(open(os.path.join(RAW, 'income.json'))); fills = json.load(open(os.path.join(RAW, 'user_trades.json')))
    logev, starts = load_logs()
    cur = cfg_combos('config.portfolio.json'); era_b = cfg_combos('config.portfolio.json.bak_20251029_before_swap'); era_a = cfg_combos('config.portfolio.json.bak_20251010')
    state = json.load(open(os.path.join(BOT, 'portfolio_state.json'), encoding='utf-8'))['combos']
    # 同一個幣在狀態檔裡出現過幾個『有交易』的組合
    state_by_sym = collections.defaultdict(list)
    for k, v in state.items():
        if v.get('trades'): state_by_sym[k.split('|')[0]].append((k, len(v['trades'])))
    # 設定更換時間:第一次出現『策略 23 個』的重啟
    swap_t = min((t for t, n in starts if n == 23), default=None)
    fund = collections.defaultdict(list)
    for x in inc:
        if x['incomeType'] == 'FUNDING_FEE': fund[x['symbol']].append((int(x['time']), float(x['income'])))
    trips = []
    for sym, rows in fills.items():
        rows = sorted(rows, key=lambda f: (int(f['time']), int(f['id']))); pos = 0.0; t = None; base = sym.replace('USDT', '/USDT')
        for f in rows:
            q = float(f['qty']) * (1 if f['side'] == 'BUY' else -1); px = float(f['price'])
            if t is None:
                if q < 0: continue                      # 沒有對應進場的賣單(進場在資料範圍之前):略過並記錄
                t = {'symbol': base, 'fills': [], 'buy_qty': 0.0, 'buy_cost': 0.0, 'sell_qty': 0.0, 'sell_val': 0.0, 'realized': 0.0, 'commission': 0.0, 'entry_ts': int(f['time']), 'taker': 0, 'n': 0}
            t['fills'].append(int(f['id'])); t['n'] += 1; t['realized'] += float(f['realizedPnl']); t['commission'] += float(f['commission']); t['taker'] += (0 if f['maker'] else 1)
            if q > 0: t['buy_qty'] += q; t['buy_cost'] += q * px
            else: t['sell_qty'] += -q; t['sell_val'] += -q * px
            pos += q; t['exit_ts'] = int(f['time'])
            if abs(pos) < 1e-9 * max(1.0, t['buy_qty']):
                t['closed'] = True; trips.append(t); t = None; pos = 0.0
        if t is not None:
            t['closed'] = False; t['open_qty'] = pos; trips.append(t)
    out = []
    for t in trips:
        sym = t['symbol']; k = sym.replace('/', '')
        t['avg_entry'] = t['buy_cost'] / t['buy_qty']; t['entry_notional'] = t['buy_cost']
        t['avg_exit'] = (t['sell_val'] / t['sell_qty']) if t['sell_qty'] else None
        end = t['exit_ts'] if t['closed'] else int(__import__('time').time() * 1000)
        t['funding'] = sum(v for ts, v in fund.get(k, []) if t['entry_ts'] <= ts <= end)
        t['net'] = t['realized'] + t['funding'] - t['commission']
        t['net_pct'] = t['net'] / t['entry_notional'] * 100; t['gross_pct'] = t['realized'] / t['entry_notional'] * 100
        t['hold_h'] = (end - t['entry_ts']) / 3600000
        # 歸屬
        ent = [e for e in logev if e['kind'] == 'entry' and e['sym'] == sym and 0 <= t['entry_ts'] - e['t'] <= 10 * 60000]
        if ent:
            e = ent[-1]; t.update(attr='log', tf=e['tf'], strategy=e['strat'], signal_px=e['px'])
            ex = [x for x in logev if x['kind'] in ('exit', 'exchange_exit') and x['sym'] == sym and x['strat'] == e['strat'] and e['t'] <= x['t'] <= (t['exit_ts'] + 10 * 60000 if t['closed'] else 10**15)]
            t['exit_reason'] = ex[0]['reason'] if ex else ('持倉中' if not t['closed'] else '日誌沒有對應的出場紀錄')
            st = [x for x in logev if x['kind'] == 'stop_set' and x['sym'] == sym and 0 <= x['t'] - e['t'] <= 5 * 60000]
            t['stop_px'] = st[0]['stop'] if st else None
        else:
            hist = state_by_sym.get(sym, [])
            in_cur = sym in cur
            if swap_t and t['entry_ts'] >= swap_t and in_cur and not ent and logev and t['entry_ts'] >= logev[0]['t']:
                t.update(attr='unknown', tf=None, strategy=None, why='日誌範圍內卻找不到對應的進場紀錄(可能是手動單或日誌缺漏)')
            elif len(hist) <= 1 and in_cur and (era_a.get(sym, era_b.get(sym, cur.get(sym)))[1] == cur[sym][1]) and (era_b.get(sym, cur[sym])[1] == cur[sym][1]):
                t.update(attr='single', tf=cur[sym][0], strategy=cur[sym][1])
            elif not in_cur and sym in era_a and len(hist) <= 1 and (not logev or t['entry_ts'] < logev[0]['t']):
                t.update(attr='single', tf=era_a[sym][0], strategy=era_a[sym][1], retired=True)     # 已從設定移除的組合(ARB/UNI),狀態檔也只有一個策略
            else:
                t.update(attr='unknown', tf=None, strategy=None, why='這個幣在日誌之前換過策略(狀態檔有 %s),無法可靠歸屬' % ('、'.join('%s(%d筆)' % (a, n) for a, n in hist)))
        # 進場執行:成交均價 vs 訊號價、收盤後延遲(只對 1h/4h 的整點進場有意義)
        if t.get('signal_px'): t['entry_slip_pct'] = (t['avg_entry'] / t['signal_px'] - 1) * 100
        tfm = {'1h': 3600000, '4h': 14400000}.get(t.get('tf'))
        if tfm: t['delay_s'] = (t['entry_ts'] % tfm) / 1000.0
        out.append(t)
    json.dump({'trips': out, 'swap_t': swap_t, 'starts': starts, 'log_first': logev[0]['t'] if logev else None, 'log_last': logev[-1]['t'] if logev else None}, open(os.path.join(RAW, 'trips.json'), 'w'), ensure_ascii=False)
    c = collections.Counter((x['attr']) for x in out); print('trips', len(out), 'closed', sum(1 for x in out if x['closed']), dict(c), 'swap', ms_str(swap_t) if swap_t else None, 'log', ms_str(logev[0]['t']), ms_str(logev[-1]['t']))
    print('unattributable symbols:', sorted({x['symbol'] for x in out if x['attr'] == 'unknown'}))


if __name__ == '__main__':
    main()

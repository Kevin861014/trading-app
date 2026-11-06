# -*- coding: utf-8 -*-
"""D4 A/B 前向觀察報告(唯讀:只讀 ledger/ 與 bars/,不抓網路、不寫帳本、不影響任何設定)。報告只呈現觀察結果,不自動調整任何東西。
用法:  python paper_trading/d4_report.py --dir paper_trading/experiments/d4-v1 [--save]
--save 會在 reports/ 另存一份帶時間戳的新檔(不覆蓋舊報告)。"""
import argparse, collections, datetime, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
import d4_engine as E
import market_regime as MR
from d4_store import read_jsonl_ro

HOUR = E.HOUR


_ro = read_jsonl_ro                               # 唯讀:報告不修復、不寫任何檔


def _pf(nets):
    pos = sum(x for x in nets if x > 0); neg = -sum(x for x in nets if x < 0)
    return round(pos / neg, 2) if neg > 0 else None


def scen_stats(ex, scen, init, events, marks):
    ev = [e for e in events if e['scenario'] == scen]
    entries = [e for e in ev if e['type'] == 'ENTRY']
    exit_list = [e for e in ev if e['type'] == 'EXIT']; fund = [e for e in ev if e['type'] == 'FUNDING']; rej = [e for e in ev if e['type'] == 'REJECT']
    closed_ids = {'%s|ENTRY|%s|%d' % (scen, e['key'], e['entry_ts']) for e in exit_list}
    open_entries = [e for e in entries if e['id'] not in closed_ids]
    nets = [e['net'] for e in exit_list]
    eq = [init] + [m['equity'] for m in marks]; peak = init; mdd = 0.0
    for x in eq:
        peak = max(peak, x); mdd = min(mdd, x / peak - 1)
    day = collections.OrderedDict()
    for m in marks: day[datetime.datetime.fromtimestamp(m['h'] / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')] = m['equity']
    dv = [init] + list(day.values()); dchg = [b - a for a, b in zip(dv, dv[1:])]
    worst = min(dchg) if dchg else 0.0; worst_day = list(day.keys())[dchg.index(worst)] if dchg else None
    last_eq = marks[-1]['equity'] if marks else init
    fees = sum(e['fees'] for e in exit_list) + sum(e['fee'] for e in open_entries)
    stop_x = [e for e in exit_list if e['why'] == '交易所保護停損']; fills = [e for e in entries + exit_list if e.get('slip_vs_market_open_pct') is not None and e.get('why') != '交易所保護停損']      # 進場/市價出場 vs 當根開盤
    stop_slip = [abs(e['slip_vs_expected_pct']) for e in stop_x if e.get('slip_vs_expected_pct') is not None]                                         # 停損成交 vs 停損觸發價
    slip_cost = sum(e['qty'] * (e['sim_fill'] - e['expected_px']) for e in entries if e.get('expected_px')) + sum(e['qty'] * (e['expected_px'] - e['sim_fill']) for e in exit_list if e.get('expected_px'))
    ncon = [m['n_open'] for m in marks]; expo = [m['exposure'] / m['equity'] for m in marks if m['equity'] > 0]
    return {'trades_closed': len(exit_list), 'open_positions_now': len(open_entries), 'rejected_entries': len(rej), 'equity_end': round(last_eq, 4), 'net_return_pct': round((last_eq / init - 1) * 100, 3),
            'closed_net_usd': round(sum(nets), 4), 'net_pf': _pf(nets), 'win_pct': round(100 * sum(1 for x in nets if x > 0) / len(nets), 1) if nets else None, 'max_dd_pct': round(mdd * 100, 3),
            'worst_day_usd': round(worst, 4), 'worst_day': worst_day, 'days_with_marks': len(day), 'fees_usd': round(fees, 4), 'funding_usd': round(sum(e['amount'] for e in fund), 4), 'slippage_cost_usd_est': round(slip_cost, 4),
            'avg_concurrent': round(sum(ncon) / len(ncon), 2) if ncon else 0, 'max_concurrent': max(ncon) if ncon else 0, 'avg_exposure_x': round(sum(expo) / len(expo), 3) if expo else 0, 'max_exposure_x': round(max(expo), 3) if expo else 0,
            'fill_vs_market_open_bp_mean': round(sum(abs(e['slip_vs_market_open_pct']) for e in fills) / len(fills) * 100, 2) if fills else None, 'fill_vs_market_open_bp_max': round(max(abs(e['slip_vs_market_open_pct']) for e in fills) * 100, 2) if fills else None,
            'stop_fills': len(stop_x), 'stop_fill_vs_trigger_bp_mean': round(sum(stop_slip) / len(stop_slip) * 100, 2) if stop_slip else None, 'fills_outside_candle_range': sum(1 for e in fills if e.get('fill_within_candle_range') is False), 'entries_total': len(entries)}


def regime_table(ex, snap, marksA, marksB, events):
    bars = E.load_bars(ex, snap['reference_symbol'], '4h', True)
    if len(bars) < 30: return None
    codes = MR.classify_series(bars); closes = [b[0] + 4 * HOUR for b in bars]
    def per(marks):
        out = collections.defaultdict(lambda: [0, 0.0])
        for a, b in zip(marks, marks[1:]):
            c = MR.align_reference([a['h']], closes, codes, 4 * HOUR)[0]; out[c][0] += 1; out[c][1] += b['equity'] - a['equity']
        return out
    pa, pb = per(marksA), per(marksB); rows = []
    for c in (MR.UP, MR.DOWN, MR.RANGE, MR.TRANSITION, MR.NA):
        if c in pa or c in pb: rows.append({'regime': MR.LABEL[c], 'hours': pa[c][0], 'A_pnl': round(pa[c][1], 4), 'B_pnl': round(pb[c][1], 4), 'B_minus_A': round(pb[c][1] - pa[c][1], 4)})
    return rows


def build_report(exp_dir):
    ex = E.Exp(exp_dir); snap = ex.load_snapshot(); init = snap['initial_equity']; ev = _ro(ex.events); ticks = _ro(ex.ticks)
    mk = {s: _ro(ex.marks(s)) for s in ('A', 'B')}; T0 = snap['start_ts']
    rep = {'experiment_id': snap['experiment_id'], 'initial_equity': init, 'start_utc': snap['start_utc'], 'generated_from_ledger': True, 'manifest_mismatch': E.verify_manifest(ex)}
    last = ticks[-1] if ticks else None; hrs = len(mk['A'])
    bars1 = {s: sum(1 for b in E.load_bars(ex, s, '1h', True) if T0 <= b[0] < T0 + hrs * HOUR) for s in snap['symbols']} if hrs else {}
    rep['period'] = {'first_mark_utc': E.iso(mk['A'][0]['h']) if hrs else None, 'processed_through_utc': E.iso(mk['A'][-1]['h']) if hrs else None, 'hours_processed': hrs,
                     'completed_1h_bars_min_per_symbol': min(bars1.values()) if bars1 else 0, 'completed_4h_bars_ref': sum(1 for b in E.load_bars(ex, snap['reference_symbol'], '4h', True) if T0 <= b[0] and b[0] + 4 * HOUR <= T0 + hrs * HOUR) if hrs else 0,
                     'ticks': len(ticks), 'last_tick_utc': last['wall_utc'] if last else None}
    rep['A'] = scen_stats(ex, 'A', init, ev, mk['A']); rep['B'] = scen_stats(ex, 'B', init, ev, mk['B'])
    rep['regime'] = regime_table(ex, snap, mk['A'], mk['B'], ev) if hrs else None
    div = _ro(ex.diverge); flags = _ro(ex.flags); taint = E.current_taint(ex)
    cnt = collections.Counter(e.get('evidence', 'UNKNOWN') for e in ev); mcnt = collections.Counter(m.get('evidence', 'UNKNOWN') for s_ in mk.values() for m in s_)
    clean_ev = [e for e in ev if e.get('evidence') == 'LIVE_FORWARD']; clean_mk = {k: [m for m in v if m.get('evidence') == 'LIVE_FORWARD'] for k, v in mk.items()}
    mixed = bool(taint is not None)
    rep['evidence'] = {'mixed': mixed, 'taint_utc': E.iso(taint) if taint is not None else None, 'live_max_lag_hours': snap['rules']['live_max_lag_ms'] / HOUR, 'event_counts': dict(cnt), 'mark_counts': dict(mcnt),
                       'flags': [{'type': f['type'], 'taint_from_utc': E.iso(f['taint_from_ts']), 'recorded_utc': f['recorded_utc']} for f in flags],
                       'clean_through_utc': E.iso(clean_mk['A'][-1]['h']) if clean_mk['A'] else None, 'A_clean': scen_stats(ex, 'A', init, clean_ev, clean_mk['A']) if mixed else None, 'B_clean': scen_stats(ex, 'B', init, clean_ev, clean_mk['B']) if mixed else None,
                       'backfill_events': sum(1 for e in ev if e.get('is_backfill')), 'max_record_lag_s': max([e['record_lag_s'] for e in ev if e.get('record_lag_s') is not None] or [0])}
    fi = (ticks[-1].get('funding_issues') or []) if ticks else []
    rep['limits'] = {'funding_incomplete_ticks': sum(1 for t in ticks if t.get('funding_issues')), 'funding_open_issues': [{'sym': i['sym'], 'kind': i['kind'], 'from_utc': i['from_utc'], 'to_utc': i['to_utc'], 'reason': i['detail']} for i in fi], 'tick_runs': len(ticks), 'ticks_with_errors': sum(1 for t in ticks if t['errors']), 'ticks_with_gaps': sum(1 for t in ticks if t['gaps']), 'lock_takeovers': sum(1 for t in ticks if t.get('lock_takeover')),
                     'bar_mismatches': sum(len(t['bar_mismatches']) for t in ticks), 'divergences_logged': len(div), 'corrupt_lines_isolated': len(_ro(ex.corrupt)),
                     'wall_gap_hours_between_ticks_max': round(max([(_ts(b['wall_utc']) - _ts(a['wall_utc'])) / 3600 for a, b in zip(ticks, ticks[1:])] or [0]), 1)}
    return rep


def _ts(s): return datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()


def render(r):
    A, B, p = r['A'], r['B'], r['period']; L = []
    L.append('# D4 前向紙上交易 A/B 觀察報告(模擬,非實盤)'); L.append('實驗 `%s`|固定開始 %s UTC|只呈現觀察結果,不自動調整實盤。' % (r['experiment_id'], r['start_utc']))
    if r['manifest_mismatch']: L.append('**警告:實驗雜湊不符 → %s;此紀錄不可再續跑,需建立新實驗版本。**' % ', '.join(r['manifest_mismatch']))
    ev_ = r['evidence']
    L.append('\n## 1 觀察期間\n- **已處理到 %s UTC**(之後的行情尚未處理;處理範圍固定落後現在約 2 小時以上)\n- 已處理:%s → %s(%d 個小時;各幣已完成 1H 棒最少 %d 根;BTC 參考 4H 已完成 %d 根)\n- tick 次數 %d,最後一次 %s UTC' % (p['processed_through_utc'], p['first_mark_utc'], p['processed_through_utc'], p['hours_processed'], p['completed_1h_bars_min_per_symbol'], p['completed_4h_bars_ref'], p['ticks'], p['last_tick_utc']))
    if p['hours_processed'] < 24 * 14: L.append('- ⚠ 觀察期不足 14 天,統計意義很低,只當進度檢查。')
    rows = [('已平倉交易筆數', 'trades_closed'), ('目前持倉數', 'open_positions_now'), ('被拒絕的進場', 'rejected_entries'), ('淨報酬 %(含未平倉浮動)', 'net_return_pct'), ('已平倉淨損益 USD', 'closed_net_usd'), ('淨 PF(已平倉)', 'net_pf'), ('勝率 %', 'win_pct'),
            ('最大回撤 %(每小時權益)', 'max_dd_pct'), ('最差單日損益 USD', 'worst_day_usd'), ('手續費 USD', 'fees_usd'), ('資金費率 USD(+收/−付)', 'funding_usd'), ('滑價成本估計 USD', 'slippage_cost_usd_est'),
            ('平均/最大同時持倉', None), ('平均/最大暴露(倍權益)', None), ('進場/市價出場成交 vs 當根開盤:平均/最大 bp', None), ('停損成交 vs 觸發價:筆數 / 平均 bp', None)]
    L.append('\n## 2 證據分類(即時前向 vs 補跑)')
    if ev_['mixed']:
        L.append('- ⚠ **這個實驗已不是「未中斷的即時前向」**:汙染起點 %s UTC。下表「全部」包含補跑/中斷之後的紀錄(混合);**只有第 2b 表(截至汙染起點、僅 LIVE_FORWARD)才可當作未中斷的即時前向證據。**' % ev_['taint_utc'])
        L.append('- 旗標:' + '、'.join('%s(%s)' % (f['type'], f['taint_from_utc']) for f in ev_['flags']) if ev_['flags'] else '- 旗標:無(補跑來自記帳延遲超過 %g 小時)' % ev_['live_max_lag_hours'])
    else: L.append('- 目前全部紀錄皆為 LIVE_FORWARD(記帳延遲 ≤ %g 小時、無中斷/缺口/修訂/補跑)。' % ev_['live_max_lag_hours'])
    L.append('- 事件:%s|每小時權益點:%s|補跑事件 %d 筆|最大記帳延遲 %.1f 小時' % (dict(ev_['event_counts']), dict(ev_['mark_counts']), ev_['backfill_events'], ev_['max_record_lag_s'] / 3600))
    L.append('\n## 2a A / B 對照(起始權益 %.0f USD;%s)\n| 項目 | A 全部 23 組 | B 排除 TRX、XRP 1H |\n|---|---|---|' % (r['initial_equity'], '全部,含補跑/中斷之後 = 混合' if ev_['mixed'] else '全部為即時前向'))
    for lab, k in rows:
        if k: a, b = A[k], B[k]
        elif '持倉' in lab: a, b = '%s / %s' % (A['avg_concurrent'], A['max_concurrent']), '%s / %s' % (B['avg_concurrent'], B['max_concurrent'])
        elif '暴露' in lab: a, b = '%s / %s' % (A['avg_exposure_x'], A['max_exposure_x']), '%s / %s' % (B['avg_exposure_x'], B['max_exposure_x'])
        elif '停損成交' in lab: a, b = '%s / %s' % (A['stop_fills'], A['stop_fill_vs_trigger_bp_mean']), '%s / %s' % (B['stop_fills'], B['stop_fill_vs_trigger_bp_mean'])
        else: a, b = '%s / %s' % (A['fill_vs_market_open_bp_mean'], A['fill_vs_market_open_bp_max']), '%s / %s' % (B['fill_vs_market_open_bp_mean'], B['fill_vs_market_open_bp_max'])
        L.append('| %s | %s | %s |' % (lab, a, b))
    L.append('\n最差單日:A %s(%s)、B %s(%s)。' % (A['worst_day_usd'], A['worst_day'], B['worst_day_usd'], B['worst_day']))
    if ev_['mixed']:
        Ac, Bc_ = ev_['A_clean'], ev_['B_clean']
        L.append('\n## 2b 未中斷即時前向(僅 LIVE_FORWARD,截至 %s)\n| 項目 | A | B |\n|---|---|---|' % ((ev_['clean_through_utc'] + ' UTC') if ev_['clean_through_utc'] else '— 尚無任何未中斷的即時前向紀錄'))
        for lab, k in (('已平倉交易筆數', 'trades_closed'), ('淨報酬 %', 'net_return_pct'), ('淨 PF', 'net_pf'), ('最大回撤 %', 'max_dd_pct'), ('最差單日損益 USD', 'worst_day_usd'), ('手續費 USD', 'fees_usd'), ('資金費率 USD', 'funding_usd')): L.append('| %s | %s | %s |' % (lab, Ac[k], Bc_[k]))
    L.append('\n## 3 BTC 環境下的差異(C2 規則:ADX/DI,區間開始時已知的 4H 分類;每小時權益變化歸到當時環境)')
    if r['regime']:
        L.append('| 環境 | 小時數 | A 損益 | B 損益 | B−A |\n|---|---|---|---|---|')
        for x in r['regime']: L.append('| %s | %d | %s | %s | %s |' % (x['regime'], x['hours'], x['A_pnl'], x['B_pnl'], x['B_minus_A']))
    else: L.append('BTC 參考資料不足,尚無分類。')
    lm = r['limits']
    L.append('\n## 4 限制與資料狀況\n- tick %d 次;有錯誤 %d、有資料缺口 %d、鎖接管(前次異常中斷)%d、tick 最大間隔 %.1f 小時\n- K 棒與已存紀錄不一致 %d 次、事件重跑與原紀錄不一致 %d 筆(皆只記錄,不覆蓋原始紀錄)、殘缺行隔離 %d' % (lm['tick_runs'], lm['ticks_with_errors'], lm['ticks_with_gaps'], lm['lock_takeovers'], lm['wall_gap_hours_between_ticks_max'], lm['bar_mismatches'], lm['divergences_logged'], lm['corrupt_lines_isolated']))
    if lm['funding_incomplete_ticks']:
        L.append('- ⚠ **資金費率不完整,處理已停在缺口之前**(缺漏的資金費率不會被當成 0;曾發生 %d 次 tick)。目前仍未解決的:%s' % (lm['funding_incomplete_ticks'], ('；'.join('%s %s → %s UTC(%s):%s' % (i['sym'], i['from_utc'], i['to_utc'], i['kind'], i['reason']) for i in lm['funding_open_issues']) or '無(最近一次 tick 已完整)')))
    L.append('- **所有成交都是模擬(SIMULATED)**:進場 = 訊號棒後下一根開盤 ×(1+0.03%);市價出場 ×(1−0.01%);交易所保護停損 = min(觸發價, 開盤)×(1−0.042%)。真實成交可能因流動性、延遲、拒單而不同。')
    L.append('- 模擬器在程式中斷期間不會「漏跑」:下次 tick 會依已存的已收盤 K 棒補算,但若交易所端缺 K 棒,處理會停在缺口之前並記錄,不補造資料。')
    L.append('- 處理範圍落後現在至少 2 小時(等資金費率公布)。B 的 Σ權重沿用 A 的 16(其餘 21 組分配金額不因移除而增加)。')
    L.append('- 前向期間短、樣本少;A/B 的差異可能只是雜訊。這份報告不構成調整實盤的依據。')
    return '\n'.join(L) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); ap.add_argument('--dir', required=True); ap.add_argument('--save', action='store_true'); ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv); r = build_report(a.dir); txt = render(r)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else txt)
    if a.save:
        ex = E.Exp(a.dir); stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'); os.makedirs(ex.reports, exist_ok=True)
        p = os.path.join(ex.reports, 'report_%s.md' % stamp)
        if os.path.exists(p): raise FileExistsError(p)
        open(p, 'w', encoding='utf-8').write(txt); print('saved:', p)


if __name__ == '__main__':
    main()

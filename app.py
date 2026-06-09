from flask import Flask, jsonify, request
from flask_cors import CORS
import sys, os, datetime, time
sys.path.insert(0, os.path.dirname(__file__))
from sim import run_backtest, STRATS, market_cost
from sim import ema as calc_ema

app = Flask(__name__)
CORS(app)

PERIOD_DAYS = {
    '7d': 7, '1mo': 30, '1y': 365, '2y': 730, '3y': 1095, '5y': 1825
}

STRAT_LIST = [
    {"v": "sixline",    "l": "六條線 多頭排列（最推薦）"},
    {"v": "diadx",      "l": "DMI/ADX 方向動能（台股最強）"},
    {"v": "supertrend", "l": "Supertrend（黃金/PAXG 最佳）"},
    {"v": "keltner",    "l": "Keltner 通道突破"},
    {"v": "volbreak",   "l": "波動突破（貴金屬最強）"},
    {"v": "ttm",        "l": "TTM 擠壓突破（加密4H最強）"},
    {"v": "donchian",   "l": "Donchian 突破"},
    {"v": "ema_cross",  "l": "EMA 快慢線交叉"},
    {"v": "hma",        "l": "Hull MA 斜率翻轉"},
    {"v": "rsi50",      "l": "RSI-50 收復"},
    {"v": "tsmom",      "l": "時間序列動能（美股最強）"},
    {"v": "ichimoku",   "l": "Ichimoku 雲突破"},
    {"v": "cci",        "l": "CCI 動能突破"},
    {"v": "vortex",     "l": "Vortex 渦流順勢"},
    {"v": "bbreak",     "l": "布林帶突破"},
    {"v": "lrs",        "l": "線性回歸斜率"},
    {"v": "macd",       "l": "MACD 趨勢"},
    {"v": "crsi",       "l": "Connors RSI 逆勢（勝率67%）"},
    {"v": "rsi",        "l": "RSI 均值回歸（逆勢）"},
    {"v": "trend",      "l": "順勢 EMA20/100（通用）"},
]

_cache = {}
_cache_time = {}
CACHE_TTL = 3600

def fetch_data(symbol, start_date, interval='1d'):
    import yfinance as yf
    cache_key = f"{symbol}_{start_date}_{interval}"
    now = time.time()
    if cache_key in _cache and (now - _cache_time.get(cache_key, 0)) < CACHE_TTL:
        return _cache[cache_key]
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(2 * attempt)
            ticker = yf.Ticker(symbol)
            kw = dict(auto_adjust=True)
            # yfinance 日內資料有時間限制
            if interval == '1h':
                kw['period'] = '730d'
            else:
                kw['start'] = start_date
            df = ticker.history(interval=interval, **kw)
            if df is not None and not df.empty:
                out = []
                for ts, row in df.iterrows():
                    try:
                        o=float(row['Open']); h=float(row['High'])
                        l=float(row['Low']);  c=float(row['Close'])
                        v=float(row['Volume']) if 'Volume' in row else 0.0
                        if c > 0:
                            out.append([int(ts.timestamp()*1000), o, h, l, c, v])
                    except Exception:
                        continue
                if out:
                    _cache[cache_key] = out
                    _cache_time[cache_key] = now
                    return out
        except Exception as e:
            if attempt == 2: raise e
            time.sleep(2)
    return []

def get_real_trades(ohlcv, el_full, xl_full):
    N = len(ohlcv)
    pos = False
    buy_idx = [None] * N
    sell_idx = [None] * N
    for i in range(N - 1):
        if not pos and el_full[i]:
            pos = True
            buy_idx[i+1] = True
        elif pos and xl_full[i]:
            pos = False
            sell_idx[i+1] = True
    return buy_idx, sell_idx

@app.route('/api/strategies')
def get_strategies():
    return jsonify(STRAT_LIST)

@app.route('/api/analyze')
def analyze():
    symbol    = request.args.get('symbol', '2330.TW')
    strategy  = request.args.get('strategy', 'diadx')
    period    = request.args.get('period', '1y')
    timeframe = request.args.get('timeframe', '1d')

    # yfinance 不支援 4h，用 1h 替代（sim.py 也這樣處理）
    yf_tf = {'1d':'1d', '4h':'1h', '1h':'1h'}.get(timeframe, '1d')

    days = PERIOD_DAYS.get(period, 365)
    if yf_tf == '1h':
        fetch_days = min(days + 100, 680)  # yfinance 1h 上限約 730 天
    else:
        fetch_days = days + 700
    start_date = (datetime.datetime.now() - datetime.timedelta(days=fetch_days)).strftime('%Y-%m-%d')

    try:
        import sim as _sim
        spec = ('yf', symbol)
        _sim.COMMISSION, _sim.SLIPPAGE = market_cost(spec, strategy)

        ohlcv = fetch_data(symbol, start_date, interval=yf_tf)

        if not ohlcv or len(ohlcv) < 100:
            cnt = len(ohlcv) if ohlcv else 0
            return jsonify({'error': f'資料不足（取得 {cnt} 根）。台股如 2330.TW，美股如 AAPL，加密如 PAXG-USD'}), 400

        # 回測需要足夠暖機，不夠就提示
        if len(ohlcv) < 220:
            return jsonify({'error': f'資料不足以跑回測（{len(ohlcv)} 根），請選擇更長的時間範圍或改用日線'}), 400

        result = run_backtest(ohlcv, strategy=strategy, risk_pct=0.015, timeframe=yf_tf)
        if not result:
            return jsonify({'error': '回測失敗，請選擇更長的時間範圍'}), 400

        dates_dt, equity, stats = result

        O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
        L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
        V=[(r[5] if len(r)>5 else 0.0) for r in ohlcv]
        s = STRATS.get(strategy, STRATS['trend'])
        el_full, xl_full = s['build'](O, H, L, C, V, yf_tf)

        real_buy, real_sell = get_real_trades(ohlcv, el_full, xl_full)

        display_n = min(days * (6 if yf_tf=='1h' else 1) + 30, len(ohlcv))
        disp = ohlcv[-display_n:]
        offset = len(ohlcv) - display_n

        prices = [r[4] for r in disp]
        dates  = [datetime.datetime.utcfromtimestamp(r[0]/1000).strftime('%Y-%m-%d %H:%M' if yf_tf=='1h' else '%Y-%m-%d') for r in disp]

        ema20 = calc_ema(prices, 20)
        ema50 = calc_ema(prices, 50)

        buy_points  = [prices[i] if real_buy[offset+i]  else None for i in range(len(prices))]
        sell_points = [prices[i] if real_sell[offset+i] else None for i in range(len(prices))]

        diff = []
        for i in range(len(prices)):
            if ema20[i] is not None and ema50[i] is not None and ema50[i] > 0:
                diff.append(round((ema20[i] - ema50[i]) / ema50[i] * 100, 3))
            else:
                diff.append(0)

        trades_list = []
        buy_px = None; buy_date = None
        for i in range(len(prices)):
            if real_buy[offset+i]:
                buy_px = prices[i]; buy_date = dates[i]
            elif real_sell[offset+i] and buy_px:
                ret = round((prices[i] - buy_px) / buy_px * 100, 2)
                trades_list.append({'buyPrice':round(buy_px,2),'sellPrice':round(prices[i],2),
                                    'buyDate':buy_date,'sellDate':dates[i],'ret':ret})
                buy_px = None
        trades_list = trades_list[-10:][::-1]

        payoff = stats.get('payoff', 0)
        wr = stats['win'] / 100
        pf = round(payoff * wr / max(1 - wr, 0.001), 2) if payoff > 0 else 0

        volumes = [round(r[5], 0) if r[5] > 0 else None for r in disp]

        return jsonify({
            'dates': dates,
            'prices': [round(p,2) for p in prices],
            'ema20': [round(v,2) if v is not None else None for v in ema20],
            'ema50': [round(v,2) if v is not None else None for v in ema50],
            'buyPoints': buy_points,
            'sellPoints': sell_points,
            'diff': diff,
            'volumes': volumes,
            'metrics': {
                'totalReturn': round(stats['total'],2),
                'cagr': round(stats['cagr'],2),
                'pf': pf,
                'maxDD': round(stats['mdd'],2),
                'wr': round(stats['win'],1),
                'tradeCount': stats['trades'],
                'trades': trades_list,
            }
        })

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500

@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)

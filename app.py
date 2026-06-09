from flask import Flask, jsonify, request
from flask_cors import CORS
import sys, os, datetime
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

def fetch_data(symbol, start_date):
    """用 yfinance 抓資料，加上 headers 避免被擋"""
    import yfinance as yf
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, auto_adjust=True)
        if df is None or df.empty:
            return []
        out = []
        for ts, row in df.iterrows():
            try:
                o = float(row['Open']); h = float(row['High'])
                l = float(row['Low']);  c = float(row['Close'])
                v = float(row['Volume']) if 'Volume' in row else 0.0
                if c > 0:
                    out.append([int(ts.timestamp() * 1000), o, h, l, c, v])
            except Exception:
                continue
        return out
    except Exception as e:
        return []

@app.route('/api/strategies')
def get_strategies():
    return jsonify(STRAT_LIST)

@app.route('/api/analyze')
def analyze():
    symbol   = request.args.get('symbol', '2330.TW')
    strategy = request.args.get('strategy', 'diadx')
    period   = request.args.get('period', '1y')

    days = PERIOD_DAYS.get(period, 365)
    fetch_days = days + 700
    start_date = (datetime.datetime.now() - datetime.timedelta(days=fetch_days)).strftime('%Y-%m-%d')

    try:
        import sim as _sim
        spec = ('yf', symbol)
        _sim.COMMISSION, _sim.SLIPPAGE = market_cost(spec, strategy)

        ohlcv = fetch_data(symbol, start_date)

        if not ohlcv or len(ohlcv) < 220:
            cnt = len(ohlcv) if ohlcv else 0
            return jsonify({'error': f'資料不足（取得 {cnt} 根 K 棒）。台股代碼格式如 2330.TW，美股如 AAPL，加密如 PAXG-USD'}), 400

        result = run_backtest(ohlcv, strategy=strategy, risk_pct=0.015, timeframe='1d')
        if not result:
            return jsonify({'error': '回測失敗，請選擇更長的時間範圍（建議至少 2 年）'}), 400

        dates_dt, equity, stats = result

        display_n = min(days + 30, len(ohlcv))
        disp = ohlcv[-display_n:]

        prices = [r[4] for r in disp]
        dates  = [datetime.datetime.utcfromtimestamp(r[0]/1000).strftime('%Y-%m-%d') for r in disp]

        ema20 = calc_ema(prices, 20)
        ema50 = calc_ema(prices, 50)

        O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
        L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
        V=[(r[5] if len(r)>5 else 0.0) for r in ohlcv]
        s = STRATS.get(strategy, STRATS['trend'])
        el_full, xl_full = s['build'](O, H, L, C, V, '1d')

        offset = len(ohlcv) - display_n
        el = el_full[offset:]
        xl = xl_full[offset:]

        buy_points  = [prices[i] if el[i] else None for i in range(len(prices))]
        sell_points = [prices[i] if xl[i] else None for i in range(len(prices))]

        diff = []
        for i in range(len(prices)):
            if ema20[i] is not None and ema50[i] is not None and ema50[i] > 0:
                diff.append(round((ema20[i] - ema50[i]) / ema50[i] * 100, 3))
            else:
                diff.append(0)

        trades_list = []
        buy_px = None
        for i in range(len(prices)):
            if el[i]:
                buy_px = prices[i]
            elif xl[i] and buy_px:
                ret = round((prices[i] - buy_px) / buy_px * 100, 2)
                trades_list.append({
                    'buyPrice':  round(buy_px, 2),
                    'sellPrice': round(prices[i], 2),
                    'ret': ret
                })
                buy_px = None
        trades_list = trades_list[-10:][::-1]

        payoff = stats.get('payoff', 0)
        wr = stats['win'] / 100
        pf = round(payoff * wr / max(1 - wr, 0.001), 2) if payoff > 0 else 0

        return jsonify({
            'dates':      dates,
            'prices':     [round(p, 2) for p in prices],
            'ema20':      [round(v, 2) if v is not None else None for v in ema20],
            'ema50':      [round(v, 2) if v is not None else None for v in ema50],
            'buyPoints':  buy_points,
            'sellPoints': sell_points,
            'diff':       diff,
            'metrics': {
                'totalReturn': round(stats['total'], 2),
                'cagr':        round(stats['cagr'], 2),
                'pf':          pf,
                'maxDD':       round(stats['mdd'], 2),
                'wr':          round(stats['win'], 1),
                'tradeCount':  stats['trades'],
                'trades':      trades_list,
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

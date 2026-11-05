# -*- coding: utf-8 -*-
"""D2 共用:載入資料/訊號、機器人設定時間線、日誌輪詢時間、實盤交易(取自 D1 的重建)。全部唯讀。"""
import glob, json, os, pickle, re, sys, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, 'validation', 'd1_live')); os.chdir(ROOT)
import d2_sim as S
BOT = r'C:\Users\User\發大財\順勢交易機器人'; BACKUP_ROOT = r'C:\Users\User\發大財\研究備份_D2'
HOUR = 3600000


def local_to_ms(s):
    import datetime
    return int(datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) - 8 * 3600000


def backup_dir():
    return sorted(glob.glob(os.path.join(BACKUP_ROOT, '2*')))[-1]


def cfg_combos(name):
    """設定檔的『組合清單』(讀備份目錄裡已移除金鑰的副本,不碰原始設定檔)。"""
    fn = os.path.join(backup_dir(), name + '.REDACTED.json')
    return [{'symbol': c['symbol'], 'timeframe': c['timeframe'], 'strategy': c['strategy'], 'weight': c.get('weight', 1)} for c in json.load(open(fn, encoding='utf-8'))['combos']]


def load_market():
    d = pickle.load(open(os.path.join(RAW, 'data.pkl'), 'rb')); return S.Market(d), d


def load_signals(): return pickle.load(open(os.path.join(RAW, 'signals.pkl'), 'rb'))


def exit_params():
    import app as A
    out = {}
    for k, s in A.STRATS.items():
        out[k] = (s.get('atr_stop') or 0.0, s.get('atr_trail') or 0.0, s.get('atr_tp') or 0.0, s.get('pct_stop') or 0.0, s.get('pct_trail') or 0.0, s.get('pct_tp') or 0.0)
    return out


def log_loops():
    """日誌每輪『保證金≈』的時間(UTC 毫秒)與數值 = 機器人當時看到的資金(flat 時 = 錢包)。"""
    pts = []
    for fn in ('portfolio.log.old', 'portfolio.log'):
        p = os.path.join(BACKUP_ROOT, os.path.basename(backup_dir()), fn)
        for line in open(p, encoding='utf-8', errors='replace'):
            m = re.match(r'\[(\d{4}-\d\d-\d\d [\d:]+)\] 保證金≈([\d.]+)', line)
            if m: pts.append((local_to_ms(m.group(1)), float(m.group(2))))
    return sorted(pts)


def live_trips():
    return json.load(open(os.path.join(ROOT, 'validation', 'd1_live', 'raw', 'trips_enriched.json')))['trips']


def d1_meta():
    return json.load(open(os.path.join(ROOT, 'validation', 'd1_live', 'raw', 'trips.json')))

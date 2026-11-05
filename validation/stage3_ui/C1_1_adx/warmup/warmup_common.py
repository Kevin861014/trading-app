# -*- coding: utf-8 -*-
"""C1.1 第二部分共用:三種 DMI/ADX 版本(只在記憶體暫時替換 sim.dmi,不改任何檔案)與離線資料。

A  現行 sim.dmi
B  教科書 Wilder、因果(任一時間點只用當時與過去 K 棒)的修正版(tests/adx_reference.wilder_adx)
C(K) 現行 sim.dmi 搭配嚴格暖機:資料最前面 K 根的 +DI/-DI/ADX 一律視為 None(策略在 None 時不出訊號)
"""
import contextlib, datetime, json, os, sys, warnings
warnings.filterwarnings('ignore')
os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests')); os.chdir(ROOT)
import adx_reference as R
import app as A
import sim
A.CCXT_AVAILABLE = True        # RENDER=true 會略過啟動時的 ccxt 檢查;這台電腦有 ccxt

ORIG_DMI = sim.dmi
ADX_STRATS = ['diadx', 'ema50_200_adx', 'adx_di', 'dmi_cross', 'adx_di_trend', 'holy_grail']
SNAP = os.path.join(HERE, 'snapshots.json')
FIXED_NOW = datetime.datetime(2026, 11, 5, 10, 40)        # 與 C1 回歸快照相同的固定時間


def dmi_A(H, L, C, n=14):
    return ORIG_DMI(H, L, C, n)


def dmi_B(H, L, C, n=14):
    return R.wilder_adx(H, L, C, n)


def dmi_C(K):
    def f(H, L, C, n=14):
        p, m, a = ORIG_DMI(H, L, C, n); k = min(K, len(C))
        for x in (p, m, a):
            for i in range(k): x[i] = None
        return p, m, a
    return f


VARIANTS = {'A': dmi_A, 'B': dmi_B, 'C27': dmi_C(27), 'C50': dmi_C(50), 'C100': dmi_C(100), 'C150': dmi_C(150), 'C200': dmi_C(200)}


@contextlib.contextmanager
def use(variant):
    sim.dmi = VARIANTS[variant]
    try: yield
    finally: sim.dmi = ORIG_DMI


def load_snap():
    return json.load(open(SNAP, encoding='utf-8'))


def build(key, rows, tf):
    O, H, L, C, V = [[r[i] for r in rows] for i in (1, 2, 3, 4, 5)]
    m = A.STRATS[key]
    try: return m['build'](O, H, L, C, V, tf)
    except TypeError: return m['build'](O, H, L, C, V)

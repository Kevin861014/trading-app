# -*- coding: utf-8 -*-
"""C3 第一部分:大盤環境對齊必須看『收盤時間』(參考 K 棒要在策略決策時間之前或同時完成收盤),
涵蓋台股/美股 1H、夏令時間與交易時段邊界。"""
import datetime, json, os, random, sys, unittest, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import market_regime as MR
import regime_study as RS
from zoneinfo import ZoneInfo

UTC = datetime.timezone.utc
H = 3600000


def ms(y, mo, d, h=0, mi=0, tz=UTC):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=tz).astimezone(UTC).timestamp() * 1000)


NY, TP = ZoneInfo("America/New_York"), ZoneInfo("Asia/Taipei")


class TestBarClose(unittest.TestCase):
    def test_us_hourly_bars_close_on_the_session_clock_in_winter_and_summer(self):
        # 冬令(EST,UTC-5):2026-03-06 週五;夏令(EDT,UTC-4):2026-03-09 週一(夏令時間在 03-08 開始)
        for day, off in ((6, 5), (9, 4)):
            first = ms(2026, 3, day, 9, 30, NY); last = ms(2026, 3, day, 15, 30, NY)
            self.assertEqual(RS.bar_close_ms(first, "1h", "us"), ms(2026, 3, day, 10, 30, NY))
            self.assertEqual(RS.bar_close_ms(last, "1h", "us"), ms(2026, 3, day, 16, 0, NY))            # 最後一根只有 30 分鐘,16:00 收,不是 16:30
            self.assertEqual(RS.bar_close_ms(last, "1h", "us"), ms(2026, 3, day, 16 + off, 0))          # 換算成 UTC:冬令 21:00、夏令 20:00
        # 冬令回歸(2026-11-01)
        self.assertEqual(RS.bar_close_ms(ms(2026, 11, 2, 15, 30, NY), "1h", "us"), ms(2026, 11, 2, 21, 0))

    def test_tw_hourly_and_daily_close(self):
        self.assertEqual(RS.bar_close_ms(ms(2026, 11, 5, 9, 0, TP), "1h", "tw"), ms(2026, 11, 5, 10, 0, TP))
        self.assertEqual(RS.bar_close_ms(ms(2026, 11, 5, 13, 0, TP), "1h", "tw"), ms(2026, 11, 5, 13, 30, TP))      # 13:00 那根 13:30 收
        self.assertEqual(RS.bar_close_ms(ms(2026, 11, 5), "1d", "tw"), ms(2026, 11, 5, 13, 30, TP))                  # 日線標籤是當地日期 00:00 UTC
        self.assertEqual(RS.bar_close_ms(ms(2026, 11, 5), "1d", "tw"), ms(2026, 11, 5, 5, 30))

    def test_us_daily_close_follows_daylight_saving(self):
        self.assertEqual(RS.bar_close_ms(ms(2026, 3, 6), "1d", "us"), ms(2026, 3, 6, 21, 0))      # EST
        self.assertEqual(RS.bar_close_ms(ms(2026, 3, 9), "1d", "us"), ms(2026, 3, 9, 20, 0))      # EDT
        self.assertEqual(RS.bar_close_ms(ms(2026, 11, 2), "1d", "us"), ms(2026, 11, 2, 21, 0))     # 回到 EST

    def test_crypto_is_open_plus_period(self):
        self.assertEqual(RS.bar_close_ms(ms(2026, 11, 5, 4), "4h", "crypto"), ms(2026, 11, 5, 8)); self.assertEqual(RS.bar_close_ms(ms(2026, 11, 5), "1d", "crypto"), ms(2026, 11, 6))


class TestAlignmentByCloseTime(unittest.TestCase):
    def test_boundary_equal_close_is_usable_one_ms_later_is_not(self):
        self.assertEqual(MR.align_reference([1000 * H], [1000 * H], ["up"], H), ["up"])
        self.assertEqual(MR.align_reference([1000 * H], [1000 * H + 1], ["up"], H), [MR.NA])

    def test_open_time_alone_is_not_enough_daily_reference_for_an_hourly_decision(self):
        # 假設主標的是美股 1H、參考是日線:同一天日線的『開盤時間標籤』比 10:30 收盤的 1H 早,但它要到 16:00 才收盤 → 不能用(舊的只看開盤時間的規則會洩漏)
        day = ms(2026, 3, 9)                                                      # 日線標籤(當地日期 00:00 UTC)
        main_close = [RS.bar_close_ms(ms(2026, 3, 9, 9, 30, NY), "1h", "us")]    # 10:30 ET 收
        ref_close = [RS.bar_close_ms(ms(2026, 3, 6), "1d", "us"), RS.bar_close_ms(day, "1d", "us")]
        self.assertEqual(MR.align_reference(main_close, ref_close, ["down", "up"], H, max_gap_bars=10**6), ["down"])   # 只能用上週五的日線
        # 同一天最後一根(15:30–16:00)的決策時間 = 16:00 ET = 日線收盤時間 → 可以用當天日線
        main_close = [RS.bar_close_ms(ms(2026, 3, 9, 15, 30, NY), "1h", "us")]
        self.assertEqual(MR.align_reference(main_close, ref_close, ["down", "up"], H, max_gap_bars=10**6), ["up"])

    def test_same_market_hourly_bars_align_one_to_one_across_dst_and_weekends(self):
        for market, tz, hours in (("us", NY, [(9, 30), (10, 30), (11, 30), (12, 30), (13, 30), (14, 30), (15, 30)]), ("tw", TP, [(9, 0), (10, 0), (11, 0), (12, 0), (13, 0)])):
            rnd = random.Random(1); ts = []; d = datetime.date(2026, 2, 23)
            while d < datetime.date(2026, 4, 20):                                   # 涵蓋 2026-03-08 美國夏令開始
                if d.weekday() < 5: ts += [ms(d.year, d.month, d.day, h, m, tz) for h, m in hours]
                d += datetime.timedelta(days=1)
            px = 100.0; rows = []
            for t in ts:
                o = px; c = o * (1 + rnd.uniform(-0.01, 0.01)); rows.append([t, o, max(o, c) * 1.002, min(o, c) * 0.998, c, 1]); px = c
            codes = MR.classify_series(rows); out = RS.align_market_regime(ts, rows, "1h", market)
            self.assertEqual(out, codes, market)                                    # 同市場同週期:每一根對到自己同一根(收盤時間相同),沒有偏移一根、也沒有跨日錯位

    def test_missing_reference_bar_falls_back_to_the_previous_closed_one_never_the_next(self):
        rows = [[ms(2026, 3, 9, h, 30, NY), 100 + i, 101 + i, 99 + i, 100.5 + i, 1] for i, h in enumerate(range(9, 16))]
        ts = [r[0] for r in rows]; ref = [r for i, r in enumerate(rows) if i != 3]                 # 少了 12:30 那根
        codes = ["up", "down", "range", "transition", "up", "down", "range"]
        got = MR.align_reference([RS.bar_close_ms(t, "1h", "us") for t in ts], [RS.bar_close_ms(r[0], "1h", "us") for r in ref], [c for i, c in enumerate(codes) if i != 3], H)
        self.assertEqual(got[3], "range")                                           # 退回上一根已收盤的,不是下一根

    def test_real_daily_data_unchanged_by_the_stricter_rule(self):
        snap = json.load(open(os.path.join(ROOT, "validation", "stage3_ui", "C2", "snapshot.json"), encoding="utf-8"))["rows"]
        for sym, ref, market in (("2330.TW", "^TWII", "tw"), ("AAPL", "^GSPC", "us"), ("SOL/USDT", "BTC/USDT", "crypto")):
            tf = "1d"; rows, rrows = snap["%s|%s" % (sym, tf)], snap["%s|%s" % (ref, tf)]
            new = RS.align_market_regime([r[0] for r in rows], rrows, tf, market)
            rc = MR.classify_series(rrows); rts = [r[0] for r in rrows]; import bisect
            old = [rc[bisect.bisect_right(rts, r[0]) - 1] if (bisect.bisect_right(rts, r[0]) - 1 >= 0 and r[0] - rts[bisect.bisect_right(rts, r[0]) - 1] <= 5 * 86400000) else MR.NA for r in rows]
            self.assertEqual(new, old, sym)                                          # 同市場日線:舊規則本來就沒洩漏,結果與 C2 完全相同


if __name__ == "__main__":
    unittest.main()

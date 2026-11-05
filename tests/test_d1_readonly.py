# -*- coding: utf-8 -*-
"""D1 安全性:研究用的幣安工具只能 GET 白名單路徑;研究腳本裡沒有任何下單/撤單/改槓桿/轉帳/提領的呼叫。不連網。"""
import glob, os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D1 = os.path.join(ROOT, "validation", "d1_live")
sys.path.insert(0, D1)
import binance_ro as B


class TestGuard(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.g = B.guard(lambda url, method='GET', headers=None, body=None: self.sent.append((url, method)) or {"ok": 1})

    def test_write_methods_and_paths_are_blocked_before_any_request(self):
        for m, p in (("POST", "/fapi/v1/order"), ("DELETE", "/fapi/v1/order"), ("DELETE", "/fapi/v1/allOpenOrders"), ("POST", "/fapi/v1/leverage"), ("POST", "/fapi/v1/marginType"),
                     ("POST", "/fapi/v1/positionSide/dual"), ("GET", "/sapi/v1/capital/withdraw/apply"), ("POST", "/sapi/v1/asset/transfer"), ("PUT", "/fapi/v1/listenKey"), ("GET", "/fapi/v1/order"), ("GET", "/fapi/v1/leverageBracket")):
            with self.assertRaises(B.ReadOnlyViolation, msg=(m, p)): self.g("https://fapi.binance.com" + p + "?x=1", m)
        self.assertEqual(self.sent, [])

    def test_read_paths_pass_and_nothing_else(self):
        for p in sorted(B.ALLOWED): self.g("https://fapi.binance.com" + p, "GET")
        self.assertEqual(len(self.sent), len(B.ALLOWED))
        for p in B.ALLOWED: self.assertNotRegex(p, r"order|leverage|marginType|withdraw/apply|positionSide|listenKey|batch|margin$")

    def test_allowlist_has_no_write_endpoints_and_scripts_never_call_them(self):
        src = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(D1, "*.py")))
        for bad in ("create_order", "cancel_order", "cancelOrder", "set_leverage", "setLeverage", "set_margin_mode", "fapiPrivatePost", "fapiPrivateDelete", "fapiPrivatePut", "sapiPost", "sapiDelete", "withdraw(", "transfer("):
            self.assertNotIn(bad, src.replace("'/sapi/v1/asset/transfer'", ""), bad)

    def test_secrets_are_never_printed_or_written(self):
        src = open(os.path.join(D1, "binance_ro.py"), encoding="utf-8").read()
        prints = re.findall(r"print\(.*", src); self.assertEqual(len(prints), 1); self.assertIn("_scrub(", prints[0])        # 唯一的 print 會先過濾金鑰與簽章
        for f in glob.glob(os.path.join(D1, "*.py")):
            if os.path.basename(f) == "binance_ro.py": continue
            t = open(f, encoding="utf-8").read(); self.assertNotIn("api_key", t, f); self.assertNotIn("api_secret", t, f)        # 其他腳本不碰金鑰
        self.assertEqual(B._scrub("x signature=abcdef0123 K1 S2", ("K1", "S2")), "x signature=*** *** ***")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""診斷:把瀏覽器 CPU 依行程類型拆開(browser / renderer / gpu / network ...),並比較『量測程式自己的 CDP 輪詢』造成的額外負載。"""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rc_resources as R
from rc_resources import open_page, set_lab_target, kill_tree


def per_proc(tmp):
    key = os.path.basename(tmp)
    ps = ("$k='%s'; Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -like \"*$k*\" } | ForEach-Object { "
          "$t='browser'; if ($_.CommandLine -match '--type=(\w[\w-]*)') { $t=$Matches[1] }; if ($_.CommandLine -match 'utility-sub-type=([\w.]+)') { $t += ':' + $Matches[1] }; "
          "'{0}|{1}|{2}' -f $_.ProcessId, $t, ($_.KernelModeTime + $_.UserModeTime) }") % key
    out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=60).stdout.split()
    d = {}
    for line in out:
        pid, t, cpu = line.split('|'); d[pid] = (t, int(cpu) / 1e7)
    return d


async def window(c, tmp, label, mode):
    a = per_proc(tmp); t0 = time.time()
    if mode == 'poll':
        while True:
            if not await c.js("labState.model.state==='running'") and time.time() - t0 > 3: break
            await asyncio.sleep(0.25)
    else:                                   # 不做任何 CDP 輪詢:只睡到分析大約結束
        await asyncio.sleep(22)
    wall = time.time() - t0; b = per_proc(tmp)
    agg = {}
    for pid, (t, cpu) in b.items():
        agg[t] = agg.get(t, 0) + (cpu - a.get(pid, (t, 0))[1])
    print(label, 'wall %.1fs' % wall, {k: round(v / wall * 100, 1) for k, v in sorted(agg.items())}, flush=True)


async def main():
    base = sys.argv[1]
    variants = [('transition:none only', "var st=document.createElement('style');st.textContent='*{transition:none!important}';document.head.appendChild(st);"),
                ('animation:none only', "var st=document.createElement('style');st.textContent='*{animation:none!important}';document.head.appendChild(st);"),
                ('.progress-bar transition none only', "var st=document.createElement('style');st.textContent='.progress-bar,.rcp *{transition:none!important}';document.head.appendChild(st);")]
    for label, js in variants:
        proc, tmp, sess, c = await open_page(base + '/#/lab', 'desktop', port=9380)
        try:
            await asyncio.sleep(12)                      # 讓自選清單卡片的載入先結束,避免干擾
            await c.js("labState.core.setMotion(false);" + js + " 1")
            await set_lab_target(c, 'SOL-USD', '1h'); await c.js("runLabView(); 1")
            await window(c, tmp, label, 'sleep')
        finally:
            await sess.close(); kill_tree(proc)

asyncio.run(main())

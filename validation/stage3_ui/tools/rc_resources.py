# -*- coding: utf-8 -*-
"""Research Core 資源量測(Edge + 真實 GPU)。

量測:
  cpu%  = 這個瀏覽器所有行程(主程序/算圖/GPU/網路)合計的 CPU 時間 ÷ 牆鐘時間,單位是『佔用單一核心的百分比』
  gpu%  = 這些行程在 Windows『GPU Engine』計數器上的 3D 引擎使用率合計(每秒取樣)
  main% = 頁面主執行緒忙碌率(Performance.getMetrics 的 TaskDuration)
每個情境重複數次,報告每次與中位數(避免單次雜訊;同一台電腦上同時有交易機器人與其他程式在執行)。
不量測後端:分析運算本身沒有改動,輪詢端點不做運算。

usage: python rc_resources.py <base_url> <outdir>
"""
import asyncio, json, os, statistics, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aiohttp
import rc_int, shot
from rc_int import open_page, until, set_lab_target
from shot import kill_tree, BROWSER

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


async def launch_gpu(port):
    """與 shot.launch 相同,但『不』加 --disable-gpu(使用這台電腦真實的 GPU 加速)。"""
    tmp = tempfile.mkdtemp(prefix='shot_profile_')
    proc = subprocess.Popen([BROWSER, '--headless=new', '--remote-debugging-port=%d' % port, '--user-data-dir=' + tmp, '--no-first-run', '--disable-extensions',
                             '--disk-cache-size=1', '--aggressive-cache-discard', '--hide-scrollbars', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    async with aiohttp.ClientSession() as s:
        for _ in range(60):
            try:
                async with s.get('http://127.0.0.1:%d/json/version' % port) as r:
                    if r.status == 200: break
            except Exception: pass
            await asyncio.sleep(0.5)
        async with s.get('http://127.0.0.1:%d/json' % port) as r:
            targets = await r.json()
    page = next(t for t in targets if t.get('type') == 'page'); proc._port = port
    return proc, tmp, page['webSocketDebuggerUrl']

rc_int.launch = launch_gpu


def cpu_seconds(tmp):
    key = os.path.basename(tmp)
    ps = ("$k='%s'; $p = Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -like \"*$k*\" }; "
          "$s = ($p | ForEach-Object { $_.KernelModeTime + $_.UserModeTime } | Measure-Object -Sum).Sum; "
          "Write-Output (\"{0} {1} {2}\" -f $s, $p.Count, (($p | ForEach-Object { $_.ProcessId }) -join ','))") % key
    out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=60).stdout.split()
    return float(out[0]) / 1e7, int(out[1]), (out[2] if len(out) > 2 else '')


GPU_PS = r"""
param($pids, $stop, $log)
$set = @{}; foreach ($p in ($pids -split ',')) { if ($p) { $set[$p] = 1 } }
while (-not (Test-Path $stop)) {
  try {
    $c = Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction Stop
    $sum = 0.0
    foreach ($s in $c.CounterSamples) { if ($s.InstanceName -match '^pid_(\d+)_.*engtype_3d$' -and $set.ContainsKey($Matches[1])) { $sum += $s.CookedValue } }
    Add-Content -Path $log -Value $sum
  } catch {}
}
"""


def gpu_start(pids):
    d = tempfile.mkdtemp(prefix='gpuS_'); stop, log, ps1 = os.path.join(d, 'stop'), os.path.join(d, 'log.txt'), os.path.join(d, 's.ps1')
    open(ps1, 'w').write(GPU_PS); open(log, 'w').write('')
    p = subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1, '-pids', pids, '-stop', stop, '-log', log], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p, stop, log


def gpu_stop(h):
    p, stop, log = h; open(stop, 'w').write('1')
    try: p.wait(15)
    except Exception: p.kill()
    vals = [float(x) for x in open(log).read().split() if x.strip()]
    return round(sum(vals) / len(vals), 2) if vals else None


async def task_ms(c):
    m = await c.call('Performance.getMetrics'); d = {x['name']: x['value'] for x in m['metrics']}
    return d.get('TaskDuration', 0) * 1000


async def measure(c, tmp, seconds, label, rep, until_expr=None, max_s=120):
    await c.call('Performance.enable')
    c0, n, pids = cpu_seconds(tmp); g = gpu_start(pids); await asyncio.sleep(0.5)
    c0, n, pids = cpu_seconds(tmp); t0 = time.time(); k0 = await task_ms(c)
    if until_expr: await until(c, until_expr, max_s, 0.25)
    else: await asyncio.sleep(seconds)
    k1 = await task_ms(c); c1, _, _ = cpu_seconds(tmp); wall = time.time() - t0
    gpu = gpu_stop(g)
    r = {'wall_s': round(wall, 1), 'cpu_pct_1core': round((c1 - c0) / wall * 100, 2), 'gpu_3d_pct': gpu, 'main_thread_pct': round((k1 - k0) / (wall * 1000) * 100, 2)}
    rep.setdefault(label, []).append(r); print(label, r, flush=True)


def med(rep):
    out = {}
    for k, runs in rep.items():
        if not isinstance(runs, list): continue
        g = [r['gpu_3d_pct'] for r in runs if r['gpu_3d_pct'] is not None]
        out[k] = {'runs': len(runs), 'cpu_pct_1core_median': round(statistics.median(r['cpu_pct_1core'] for r in runs), 2), 'cpu_all': [r['cpu_pct_1core'] for r in runs],
                  'gpu_3d_pct_median': round(statistics.median(g), 2) if g else None, 'main_thread_pct_median': round(statistics.median(r['main_thread_pct'] for r in runs), 2), 'wall_s': runs[0]['wall_s']}
    return out


DONE = "labState.model.state!=='running' && labState.model.eventCount>0"


async def lab_run(c, tf='1h'):
    await set_lab_target(c, 'SOL-USD', tf); await c.js("runLabView(); 1")


async def main():
    base, out = sys.argv[1], os.path.abspath(sys.argv[2]); os.makedirs(out, exist_ok=True); rep = {}
    # ───── A:正式網站實驗室(桌面,真實 GPU) ─────
    proc, tmp, sess, c = await open_page(base + '/#/lab', 'desktop', port=9360)
    try:
        await asyncio.sleep(3)
        for _ in range(3): await measure(c, tmp, 10, 'A1 待機(預設:靜態、裝飾關)', rep)
        await c.js("labState.core.setAmbient(true); 1"); await asyncio.sleep(1)
        for _ in range(3): await measure(c, tmp, 10, 'A2 待機 + 使用者開啟裝飾旋轉', rep)
        await c.js("labState.core.setAmbient(false); 1"); await asyncio.sleep(1)
        for _ in range(3):
            await lab_run(c); await measure(c, tmp, 0, 'A3 分析中(真實 SOL-USD 1H 深度分析,事件流動動畫開)', rep, until_expr=DONE)
            await asyncio.sleep(1)
        rep['A3_events'] = await c.js("labState.model.eventCount")
        for _ in range(2): await measure(c, tmp, 8, 'A4 分析完成後待機', rep)
        await c.js("labState.core.setMotion(false); 1")
        for _ in range(3):
            await lab_run(c); await measure(c, tmp, 0, 'A5 分析中,事件流動動畫關閉(文字/進度列仍即時更新)', rep, until_expr=DONE)
            await asyncio.sleep(1)
        await c.js("labState.core.setMotion(true); 1")
        for _ in range(2):
            await lab_run(c); await asyncio.sleep(3); await c.js("labState.core._forceVisibility(true); 1")
            await measure(c, tmp, 0, 'A6 分析中,分頁在背景(隱藏)', rep, until_expr="labState.model.state!=='running'")
            rep['A6_loopOn_after'] = await c.js("labState.core.stats().loopOn"); await c.js("labState.core._forceVisibility(false); 1"); await asyncio.sleep(1)
        await c.call('Emulation.setEmulatedMedia', dict(features=[dict(name='prefers-reduced-motion', value='reduce')])); await asyncio.sleep(0.5)
        for _ in range(2):
            await lab_run(c); await asyncio.sleep(1); rep['A7_static'] = await c.js("labState.core.stats().static")
            await measure(c, tmp, 0, 'A7 分析中,prefers-reduced-motion', rep, until_expr=DONE); await asyncio.sleep(1)
    finally:
        await sess.close(); kill_tree(proc)

    # ───── B:手機尺寸(簡化) ─────
    proc, tmp, sess, c = await open_page(base + '/#/lab', 'mobile', port=9361)
    try:
        await asyncio.sleep(3)
        for _ in range(2): await measure(c, tmp, 8, 'B1 手機 待機', rep)
        for _ in range(2):
            await lab_run(c); await measure(c, tmp, 0, 'B2 手機 分析中(簡化:靜態球體 + 節點按鈕格)', rep, until_expr=DONE); await asyncio.sleep(1)
        rep['B_loopOn'] = await c.js("labState.core.stats().loopOn")
    finally:
        await sess.close(); kill_tree(proc)

    # ───── C:原型 新舊對照(同一份真實紀錄重播:best-sol-4h 約 6.5 秒) ─────
    old_dir = os.path.join(out, '_old_proto'); os.makedirs(os.path.join(old_dir, 'traces'), exist_ok=True)
    for f in ('research-core-v2.html', 'research-core-v2.css', 'research-core-v2.js', 'traces/traces.js'):
        data = subprocess.run(['git', 'show', '99fd0e0:trading-app/static/prototype/' + f], cwd=REPO, capture_output=True).stdout or subprocess.run(['git', 'show', '99fd0e0:static/prototype/' + f], cwd=REPO, capture_output=True).stdout
        open(os.path.join(old_dir, f), 'wb').write(data)
    old_url = 'file:///' + old_dir.replace('\\', '/') + '/research-core-v2.html'
    new_url = 'file:///' + os.path.join(REPO, 'static', 'prototype', 'research-core-v2.html').replace('\\', '/')
    for tag, url, port in (('C1 舊版原型 99fd0e0', old_url, 9362), ('C2 新版原型(共用新引擎)', new_url, 9363)):
        proc, tmp, sess, c = await open_page(url, 'desktop', port=port)
        try:
            await asyncio.sleep(3)
            assert await c.js("!!document.getElementById('rc-trace')"), 'prototype did not load: ' + url
            for _ in range(2): await measure(c, tmp, 10, tag + ' 待機', rep)
            for _ in range(2):
                await c.js("document.getElementById('rc-trace').value='best-sol-4h'; document.getElementById('rc-replay').click(); 1")
                await measure(c, tmp, 8.5, tag + ' 重播真實紀錄(約 6.5 秒)', rep); await asyncio.sleep(1)
        finally:
            await sess.close(); kill_tree(proc)
    summary = med(rep)
    json.dump({'raw': rep, 'median': summary}, open(os.path.join(out, 'resources_report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    asyncio.run(main())

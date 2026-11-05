# -*- coding: utf-8 -*-
"""Research Core 事件機制:記錄『網站後端真的在做的工作』,讓畫面只依真實事件亮燈。

原則(重要):
  * 只在真的有工作時才產生事件:事件由 app.py 裡既有的工作流程在『開始/完成』處發出(行情下載、指標計算、策略回測、訊號判斷、
    樣本外驗證、風險與成本摘要)。這個模組自己不開執行緒、不排程、不做任何背景運算,也沒有任何計時器或假進度。
  * 呼叫端沒帶 job 代號(例如卡片、舊流程)→ 一律是 NullJob:所有方法都是空操作,沒有記憶體、沒有時間成本。
  * 事件只含:階段、狀態(start/progress/done/skip/error)、真實耗時(毫秒)、真實計數(K 棒數、策略數、交易筆數…)。
    不含任何 API 金鑰、持倉、帳號、機器人狀態。
  * 記憶體有上限:最多保留 40 個工作、每個最多 600 筆事件;執行中的工作閒置 10 分鐘清除,已結束(完成/失敗/取消)的工作只保留 2 分鐘
    (足夠前端取走最後一批事件),清除只發生在有人建立/讀取工作的當下,沒有計時器。
  * 取消是『合作式』的:cancel() 只設一個旗標,分析流程在每個策略開始前呼叫 check(),看到旗標就停止後續運算(不做半套結果)。
"""
import re, threading, time

JOB_ID_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}$')
STAGES = ('data', 'indicators', 'backtest', 'signal', 'validation', 'summary')
STATUSES = ('start', 'progress', 'done', 'skip', 'error')
MAX_JOBS, MAX_EVENTS, TTL_SECONDS, FINISHED_TTL_SECONDS = 40, 600, 600, 120


class JobCancelled(BaseException):
    """使用者取消。刻意繼承 BaseException:分析流程裡既有的『except Exception: continue』不會把它吞掉。"""


class _NullJob:
    active = False
    def start(self, *a, **k): pass
    def progress(self, *a, **k): pass
    def done(self, *a, **k): pass
    def skip(self, *a, **k): pass
    def error(self, *a, **k): pass
    def finish(self, *a, **k): pass
    def check(self): pass


NULL_JOB = _NullJob()


class _Job:
    active = True

    def __init__(self, store, job_id, kind, meta):
        self.store, self.id, self.kind, self.meta = store, job_id, kind, meta
        self.t0 = time.perf_counter()
        self.wall0 = time.time()
        self.events = []
        self.seq = 0
        self.status = 'running'          # running | ok | error | cancelled
        self.cancelled = False
        self.finished_at = None
        self.last_touch = time.time()
        self._starts = {}                # stage -> perf_counter at start (for real elapsed ms)

    def _emit(self, stage, status, **detail):
        if stage not in STAGES or status not in STATUSES: return
        now = time.perf_counter()
        if status == 'start': self._starts[stage] = now
        if status in ('done', 'error') and stage in self._starts and 'ms' not in detail:
            detail['ms'] = round((now - self._starts[stage]) * 1000.0, 1)
        with self.store._lock:
            self.seq += 1
            if len(self.events) < MAX_EVENTS:
                self.events.append({'seq': self.seq, 't': round((now - self.t0) * 1000.0, 1), 'stage': stage, 'status': status, **detail})
            self.last_touch = time.time()

    def start(self, stage, **d): self._emit(stage, 'start', **d)
    def progress(self, stage, **d): self._emit(stage, 'progress', **d)
    def done(self, stage, **d): self._emit(stage, 'done', **d)
    def skip(self, stage, **d): self._emit(stage, 'skip', **d)
    def error(self, stage, message, **d): self._emit(stage, 'error', message=str(message)[:200], **d)

    def check(self):
        """合作式取消點:被取消就中止後續工作。沒被取消時只是讀一個布林值。"""
        if self.cancelled: raise JobCancelled()

    def finish(self, ok=True, cancelled=False):
        with self.store._lock:
            self.status = 'cancelled' if cancelled else ('ok' if ok else 'error')
            self.last_touch = self.finished_at = time.time()
            self.total_ms = round((time.perf_counter() - self.t0) * 1000.0, 1)


class JobEvents:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}

    def begin(self, job_id, kind, **meta):
        """沒有(或不合法的)job 代號 → NULL_JOB(空操作)。"""
        if not job_id or not JOB_ID_RE.match(str(job_id)): return NULL_JOB
        with self._lock:
            self._purge_locked()
            j = _Job(self, job_id, kind, meta)
            self._jobs[job_id] = j
        return j

    def _purge_locked(self):
        now = time.time()
        for k in [k for k, j in self._jobs.items()
                  if (j.finished_at is not None and now - j.finished_at > FINISHED_TTL_SECONDS) or now - j.last_touch > TTL_SECONDS]:
            del self._jobs[k]
        while len(self._jobs) >= MAX_JOBS:
            oldest = min(self._jobs, key=lambda k: self._jobs[k].last_touch)
            del self._jobs[oldest]

    def cancel(self, job_id):
        """要求取消。只有『執行中』的工作會被標記;回傳是否找到執行中的工作。"""
        with self._lock:
            j = self._jobs.get(job_id)
            if not j or j.status != 'running': return False
            j.cancelled = True; j.last_touch = time.time()
            return True

    def get(self, job_id, after=0):
        with self._lock:
            self._purge_locked()
            j = self._jobs.get(job_id)
            if not j: return None
            evs = [e for e in j.events if e['seq'] > after]
            return {'job': job_id, 'kind': j.kind, 'meta': j.meta, 'status': j.status, 'events': evs,
                    'lastSeq': j.seq, 'startedAt': j.wall0, 'totalMs': getattr(j, 'total_ms', None)}

    def count(self):
        with self._lock: return len(self._jobs)

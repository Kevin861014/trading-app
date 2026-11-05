# -*- coding: utf-8 -*-
"""D4 儲存層:append-only JSONL、安全讀取(中斷造成的殘缺行)、檔案鎖、SHA-256。不依賴網站或機器人的任何程式。"""
import hashlib, json, os, time


def sha256_bytes(b): return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def dumps(o): return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def append_jsonl(path, recs):
    """附加多筆記錄(每筆一行)。先寫完、flush、fsync 才算完成;不會覆寫既有內容。"""
    if not recs: return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        for r in recs: f.write(dumps(r) + '\n')
        f.flush(); os.fsync(f.fileno())
    return len(recs)


def read_jsonl(path, corrupt_path=None):
    """讀取 JSONL。若最後一行因程式中斷而殘缺(沒有換行或無法解析):把殘缺片段另存到 corrupt_path,並從原檔移除它(避免下次附加時接在殘缺行後面)。
    中間的壞行只跳過並記錄,不改動原檔。回傳 (records, problems)。"""
    if not os.path.exists(path): return [], []
    raw = open(path, 'rb').read(); recs = []; problems = []; pos = 0; good_end = 0
    for line in raw.split(b'\n'):
        end = pos + len(line) + 1
        if line.strip():
            try: recs.append(json.loads(line.decode('utf-8'))); good_end = min(end, len(raw))
            except Exception: problems.append((pos, line))
        else: good_end = min(end, len(raw))
        pos = end
    trunc = None
    if problems and (not raw.endswith(b'\n') or problems[-1][0] + len(problems[-1][1]) + 1 >= len(raw)):
        trunc = problems[-1]
    if corrupt_path and problems:
        append_jsonl(corrupt_path, [{'file': os.path.basename(path), 'offset': o, 'raw': l.decode('utf-8', 'replace'), 'at': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} for o, l in problems])
    if trunc is not None:
        with open(path, 'rb+') as f: f.truncate(trunc[0])                      # 只移除殘缺的結尾片段(已另存)
    return recs, [(o, l.decode('utf-8', 'replace')[:120]) for o, l in problems]


def read_jsonl_ro(path):
    """完全唯讀版:不修復、不寫任何檔;無法解析的行直接忽略(報告用)。"""
    if not os.path.exists(path): return []
    out = []
    for line in open(path, 'rb').read().split(b'\n'):
        if line.strip():
            try: out.append(json.loads(line.decode('utf-8')))
            except Exception: pass
    return out


class LockBusy(RuntimeError):
    pass


class FileLock:
    """簡單的單一執行鎖(O_EXCL 建立)。超過 stale_s 秒的舊鎖視為前一次異常中斷留下的,會被接管並記錄。"""
    def __init__(self, path, stale_s=1800): self.path = path; self.stale_s = stale_s; self.took_over = False

    def __enter__(self):
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, 'w') as f: f.write(json.dumps({'pid': os.getpid(), 'at': time.time()}))
                return self
            except FileExistsError:
                try: age = time.time() - os.path.getmtime(self.path)
                except OSError: continue
                if age > self.stale_s: os.remove(self.path); self.took_over = True; continue
                raise LockBusy('another tick is running (lock %s, age %.0fs)' % (self.path, age))
        raise LockBusy('could not acquire lock')

    def __exit__(self, *a):
        try: os.remove(self.path)
        except OSError: pass

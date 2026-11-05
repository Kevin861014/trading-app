# -*- coding: utf-8 -*-
r"""D2 階段一:資料保全。只『讀』機器人資料夾(不修改、不搬移、不改名、不鎖檔),把日誌/狀態/設定備份複製到獨立的研究備份目錄,並記錄大小、修改時間與 SHA-256。
- 設定檔含 API Key/Secret → 只存『已移除金鑰欄位』的副本,另外記錄原檔的 SHA-256(雜湊不會洩漏金鑰)。secret_keys.json 完全不碰。
- 備份目錄在 Git 版控之外(C:\Users\User\發大財\研究備份_D2\),manifest 只放檔名/大小/時間/雜湊。
- 用一次性讀取到記憶體的位元組寫出備份,雜湊與備份內容一致(日誌正被機器人追加,所以每個檔案的雜湊是『讀取當下』的快照)。"""
import datetime, hashlib, json, os, re, sys
BOT = r'C:\Users\User\發大財\順勢交易機器人'
DEST = r'C:\Users\User\發大財\研究備份_D2'
FILES = ['portfolio.log', 'portfolio.log.old', 'portfolio_state.json', 'portfolio_state.json.bak', 'portfolio.protection_alerts.log', 'watchdog.log', 'basket_saved.json']
CONFIGS = ['config.portfolio.json', 'config.portfolio.json.bak_20251010', 'config.portfolio.json.bak_20251029_before_swap']
SECRET = re.compile(r'key|secret|token|pass', re.I)


def sha(b): return hashlib.sha256(b).hexdigest()


def iso(t): return datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S')


def redact(o):
    if isinstance(o, dict): return {k: ('<removed>' if SECRET.search(k) else redact(v)) for k, v in o.items()}
    if isinstance(o, list): return [redact(x) for x in o]
    return o


def main():
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S'); d = os.path.join(DEST, stamp); os.makedirs(d, exist_ok=True)
    man = {'created': iso(datetime.datetime.now().timestamp()), 'source': BOT, 'files': []}
    cfg = json.load(open(os.path.join(BOT, 'config.portfolio.json'), encoding='utf-8')); secrets = [v for k, v in cfg.items() if SECRET.search(k) and isinstance(v, str) and v]
    for fn in FILES + CONFIGS:
        p = os.path.join(BOT, fn)
        if not os.path.exists(p): man['files'].append({'name': fn, 'status': 'missing'}); continue
        st = os.stat(p)
        with open(p, 'rb') as f: raw = f.read()                                  # 唯讀開啟,一次讀完
        e = {'name': fn, 'source_size': st.st_size, 'source_mtime': iso(st.st_mtime), 'bytes_read': len(raw), 'source_sha256_at_read': sha(raw)}
        if fn in CONFIGS:
            js = json.loads(raw.decode('utf-8')); out = json.dumps(redact(js), ensure_ascii=False, indent=1).encode('utf-8')
            name = fn + '.REDACTED.json'; e.update(backup=name, kind='redacted copy (api keys removed)', backup_sha256=sha(out), backup_size=len(out))
        else:
            out = raw; name = fn; e.update(backup=name, kind='byte-identical copy', backup_sha256=sha(out), backup_size=len(out))
            if any(s.encode() in raw for s in secrets): e['WARNING'] = 'contains secret'; out = b''
        with open(os.path.join(d, name), 'wb') as f: f.write(out)
        try: os.utime(os.path.join(d, name), (st.st_atime, st.st_mtime))             # 保留原始修改時間(只改備份檔,不動原檔)
        except Exception: pass
        man['files'].append(e)
    # 驗證:備份內容不含金鑰、位元組備份的雜湊與讀取時一致
    bad = []
    for e in man['files']:
        if 'backup' not in e: continue
        b = open(os.path.join(d, e['backup']), 'rb').read()
        if any(s.encode() in b for s in secrets): bad.append(e['name'])
        if sha(b) != e['backup_sha256']: bad.append(e['name'] + ':hash')
        if e['kind'].startswith('byte') and e['backup_sha256'] != e['source_sha256_at_read']: bad.append(e['name'] + ':differs')
    man['verification'] = {'secrets_found_in_backup': [x for x in bad if ':' not in x], 'hash_problems': [x for x in bad if ':' in x]}
    json.dump(man, open(os.path.join(d, 'MANIFEST.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(d); [print(' ', e['name'], e.get('source_size'), e.get('source_mtime'), (e.get('backup_sha256') or '')[:12], e.get('kind', e.get('status')), e.get('WARNING', '')) for e in man['files']]; print('verification', man['verification'])
    # 把 manifest(不含任何內容)複製一份到倉庫,供報告引用
    repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results'); os.makedirs(repo, exist_ok=True)
    json.dump(man, open(os.path.join(repo, 'backup_manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()

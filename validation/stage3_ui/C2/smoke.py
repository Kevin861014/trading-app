import json, os, sys, time, datetime, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER','true')
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0,ROOT); os.chdir(ROOT)
import app as A
S=json.load(open(os.path.join(HERE,'snapshot.json')))
NOW=datetime.datetime.fromisoformat(S['__now__']).replace(microsecond=0)
A._utcnow=lambda: datetime.datetime.utcnow().replace(microsecond=0) - (datetime.datetime.now()-NOW) if False else NOW - (datetime.datetime.now()-datetime.datetime.utcnow())
A.fetch_data=lambda sym,start,interval='1d': S['rows']['%s|%s'%(sym,interval)]
c=A.app.test_client()
for q in (dict(symbol='BTC/USDT',timeframe='4h',strategy='sixline'),dict(symbol='SOL/USDT',timeframe='1d',strategy='diadx'),dict(symbol='2330.TW',timeframe='1d',strategy='diadx'),dict(symbol='AAPL',timeframe='1d',strategy='tsmom')):
    t=time.time(); r=c.get('/api/regime_study',query_string=dict(q,period='2y',allow='up,range',basis='market')); j=r.get_json(); print(q, r.status_code, '%.1fs'%(time.time()-t))
    if r.status_code!=200: print(j); continue
    print(' ref',j['reference'].get('symbol'),j['reference'].get('supported'),'split',j['split'])
    print(' overall', {k:(v['trades'],v['pf']) for k,v in j['overall'].items()})
    for b in ('own','market'):
        if j['breakdown'][b]: print(' ',b,{s:{c_:(x['n'],x['pf']) for c_,x in rows.items()} for s,rows in j['breakdown'][b].items() if s!='all'})
    print(' share', {b:{c_:v['pct'] for c_,v in (j['share'][b] or {}).items()} for b in ('own','market')})
    f=j['filter']; print(' filter', f['status'], f.get('isNote'), {k:(f[k]['is']['trades'],f[k]['is']['pf']) for k in ('A','B')})

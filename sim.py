# -*- coding: utf-8 -*-
"""
模擬/試算 + 策略註冊表(sim 與 live_bot 共用同一套訊號,保證一致)。
34 種單一資產策略(全部真實成本驗證、足夠樣本、長期正回報;見 STRAT_ORDER):
  順勢/突破:sixline ttm keltner donchian supertrend volbreak smc hma rsi50
            tsmom ichimoku cci vortex diadx bbreak lrs macd psar kama heikin ema_cross pullback trend
  量能(需真實成交量,加密4H最佳):vwap obv force cmf
  型態:wbottom(雙重/三重底反轉,2~3%動態鎖利) trend3(三點一線趨勢線突破/跌破)
  逆勢:rsi crsi
全部無未來函數;成本含手續費+滑點;固定風險% sizing。可 API 自動下單(live_bot 全支援)。
註:sim 與 live_bot 完全一致(同一套訊號、初始停損皆以『訊號棒收盤』為基準)。
    TradingView Pine 版因平台規則,初始停損以『成交棒收盤』計,與本模組約差 1 根 K 棒,
    僅微幅影響進場初期的停損點位,對整體統計影響極小(屬可接受近似)。
"""
import math, datetime
COMMISSION = 0.0004; SLIPPAGE = 0.0002   # 每邊;來回約 0.12%

# ============================ 指標 ============================
def ema(vals, n):
    out=[None]*len(vals); k=2/(n+1); prev=None
    for i,v in enumerate(vals):
        prev=v if prev is None else (v-prev)*k+prev; out[i]=prev
    return out

def sma(vals, n):
    out=[None]*len(vals); s=0.0
    for i,v in enumerate(vals):
        s+=v
        if i>=n: s-=vals[i-n]
        if i>=n-1: out[i]=s/n
    return out

def stdev(vals, n):
    import math as _m
    out=[None]*len(vals)
    for i in range(n-1,len(vals)):
        w=vals[i-n+1:i+1]; m=sum(w)/n
        out[i]=_m.sqrt(sum((x-m)**2 for x in w)/n)
    return out

def atr(H,L,C,n):
    tr=[]
    for i in range(len(C)):
        tr.append(H[i]-L[i] if i==0 else max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])))
    out=[None]*len(tr); prev=None
    for i in range(len(tr)):
        if i<n-1: continue
        prev=sum(tr[:n])/n if prev is None else (prev*(n-1)+tr[i])/n; out[i]=prev
    return out

def rsi(C,n):
    out=[None]*len(C); ag=al=None
    for i in range(1,len(C)):
        ch=C[i]-C[i-1]; up=max(ch,0); dn=max(-ch,0)
        if i<n: continue
        if ag is None:
            ups=[max(C[j]-C[j-1],0) for j in range(i-n+1,i+1)]
            dns=[max(C[j-1]-C[j],0) for j in range(i-n+1,i+1)]
            ag=sum(ups)/n; al=sum(dns)/n
        else:
            ag=(ag*(n-1)+up)/n; al=(al*(n-1)+dn)/n
        out[i]=100-100/(1+ag/al) if al>0 else 100
    return out

def highest(src,n):
    out=[None]*len(src)
    for i in range(n-1,len(src)): out[i]=max(src[i-n+1:i+1])
    return out
def lowest(src,n):
    out=[None]*len(src)
    for i in range(n-1,len(src)): out[i]=min(src[i-n+1:i+1])
    return out

def dmi(H,L,C,n=14):
    """Wilder DMI/ADX:回傳 (+DI, -DI, ADX)。"""
    N=len(C); pdm=[0.0]*N; ndm=[0.0]*N; tr=[0.0]*N
    for i in range(1,N):
        up=H[i]-H[i-1]; dn=L[i-1]-L[i]
        pdm[i]=up if (up>dn and up>0) else 0.0
        ndm[i]=dn if (dn>up and dn>0) else 0.0
        tr[i]=max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1]))
    def wilder(x):
        out=[None]*N; s=None
        for i in range(1,N):
            if i<n: continue
            s=sum(x[1:n+1]) if s is None else s-s/n+x[i]
            out[i]=s
        return out
    str_=wilder(tr); pdms=wilder(pdm); ndms=wilder(ndm)
    pdi=[None]*N; ndi=[None]*N; adx=[None]*N; dx=[None]*N
    for i in range(N):
        if str_[i] and str_[i]>0:
            pdi[i]=100*pdms[i]/str_[i]; ndi[i]=100*ndms[i]/str_[i]
            tot=pdi[i]+ndi[i]; dx[i]=100*abs(pdi[i]-ndi[i])/tot if tot>0 else 0
    s=None
    for i in range(N):
        if dx[i] is None: continue
        if s is None:
            seg=[dx[j] for j in range(i,min(i+n,N)) if dx[j] is not None]
            if len(seg)>=n: s=sum(seg[:n])/n; adx[i+n-1]=s
        else:
            s=(s*(n-1)+dx[i])/n; adx[i]=s
    return pdi,ndi,adx

def vortex(H,L,C,n=14):
    """Vortex 渦流指標:回傳 (VI+, VI-)。"""
    N=len(C); vp=[0.0]*N; vm=[0.0]*N; tr=[0.0]*N
    for i in range(1,N):
        vp[i]=abs(H[i]-L[i-1]); vm[i]=abs(L[i]-H[i-1])
        tr[i]=max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1]))
    vip=[None]*N; vin=[None]*N
    for i in range(n,N):
        st=sum(tr[i-n+1:i+1])
        if st>0: vip[i]=sum(vp[i-n+1:i+1])/st; vin[i]=sum(vm[i-n+1:i+1])/st
    return vip,vin

def cci(H,L,C,n=20):
    """Commodity Channel Index。"""
    N=len(C); tp=[(H[i]+L[i]+C[i])/3 for i in range(N)]; out=[None]*N
    for i in range(n-1,N):
        w=tp[i-n+1:i+1]; m=sum(w)/n; md=sum(abs(x-m) for x in w)/n
        out[i]=(tp[i]-m)/(0.015*md) if md>0 else 0
    return out

def linreg_slope(C,n=20):
    """收盤對時間的線性回歸斜率(>0 上升、<0 下降)。"""
    N=len(C); out=[None]*N
    xs=list(range(n)); xm=sum(xs)/n; sxx=sum((x-xm)**2 for x in xs)
    for i in range(n-1,N):
        w=C[i-n+1:i+1]; ym=sum(w)/n
        sxy=sum((xs[j]-xm)*(w[j]-ym) for j in range(n))
        out[i]=sxy/sxx if sxx>0 else 0
    return out

def connors_rsi(C,r1=3,streak_n=2,pr_n=100):
    """Connors RSI = (RSI(close,3) + RSI(streak,2) + 百分位排名(ROC,100)) / 3。"""
    N=len(C); base=rsi(C,r1); st=[0]*N
    for i in range(1,N):
        if C[i]>C[i-1]: st[i]=st[i-1]+1 if st[i-1]>0 else 1
        elif C[i]<C[i-1]: st[i]=st[i-1]-1 if st[i-1]<0 else -1
        else: st[i]=0
    srsi=rsi(st,streak_n); roc=[None]*N
    for i in range(1,N): roc[i]=(C[i]/C[i-1]-1) if C[i-1] else 0
    pr=[None]*N
    for i in range(pr_n,N):
        w=[roc[j] for j in range(i-pr_n+1,i+1) if roc[j] is not None]
        if w: pr[i]=100*sum(1 for x in w if x<roc[i])/len(w)
    out=[None]*N
    for i in range(N):
        if None in (base[i],srsi[i],pr[i]): continue
        out[i]=(base[i]+srsi[i]+pr[i])/3
    return out

# ============================ 量能指標(用真實成交量 V)============================
def obv(C,V):
    """On-Balance Volume:價漲累加量、價跌扣量。"""
    out=[0.0]*len(C)
    for i in range(1,len(C)):
        out[i]=out[i-1]+(V[i] if C[i]>C[i-1] else (-V[i] if C[i]<C[i-1] else 0.0))
    return out

def cmf(H,L,C,V,n=20):
    """Chaikin Money Flow:n 期『資金流量乘數×量』總和 / 量總和。"""
    N=len(C); mfv=[0.0]*N
    for i in range(N):
        rng=H[i]-L[i]; mfv[i]=(((C[i]-L[i])-(H[i]-C[i]))/rng*V[i]) if rng>0 else 0.0
    out=[None]*N; sm=sv=0.0
    for i in range(N):
        sm+=mfv[i]; sv+=V[i]
        if i>=n: sm-=mfv[i-n]; sv-=V[i-n]
        if i>=n-1 and sv>0: out[i]=sm/sv
    return out

def vwap_roll(H,L,C,V,n=20):
    """滾動 VWAP(n 期量價加權均價)。"""
    N=len(C); tp=[(H[i]+L[i]+C[i])/3 for i in range(N)]; out=[None]*N; stv=sv=0.0
    for i in range(N):
        stv+=tp[i]*V[i]; sv+=V[i]
        if i>=n: stv-=tp[i-n]*V[i-n]; sv-=V[i-n]
        if i>=n-1 and sv>0: out[i]=stv/sv
    return out

def force_idx(C,V,n=13):
    """Force Index:(收盤變動 × 量)的 EMA,衡量多空力度。"""
    N=len(C); raw=[0.0]*N
    for i in range(1,N): raw[i]=(C[i]-C[i-1])*V[i]
    return ema(raw,n)

# ============================ 訊號(全部 long-only,回傳 el,xl)============================
# 慣例:第 i 棒收盤確認,第 i+1 棒開盤成交。
def sig_trend(O,H,L,C, ema_len=20, trend_len=100):
    er=ema(C,ema_len); et=ema(C,trend_len); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (er[i],er[i-1],et[i]): continue
        if C[i-1]<=er[i-1] and C[i]>er[i] and C[i]>et[i]: el[i]=True
        if C[i-1]>=er[i-1] and C[i]<er[i]: xl[i]=True
    return el,xl

def sig_sixline(O,H,L,C, periods=(10,20,30,60,120,200), entry_mode="form", exit_mode="mid"):
    E=[ema(C,p) for p in periods]; M=len(periods); N=len(C); el=[False]*N; xl=[False]*N
    def aligned(i):
        vals=[E[k][i] for k in range(M)]
        if any(v is None for v in vals): return None
        return all(vals[k]>vals[k+1] for k in range(M-1))
    xidx=2 if (exit_mode=="mid" and M>=3) else 0
    for i in range(1,N):
        a=aligned(i); ap=aligned(i-1)
        if a is None or ap is None: continue
        if entry_mode=="form":
            if a and (not ap) and C[i]>E[0][i]: el[i]=True
        else:  # ride
            if a and E[0][i-1] is not None and C[i-1]<=E[0][i-1] and C[i]>E[0][i]: el[i]=True
        if E[xidx][i] is not None and C[i]<E[xidx][i]: xl[i]=True
    return el,xl

def sig_donchian(O,H,L,C, n_enter=20, n_exit=10, trend_len=100):
    hh=highest(H,n_enter); lx=lowest(L,n_exit); et=ema(C,trend_len); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if hh[i-1] is None or lx[i-1] is None or et[i] is None: continue
        if C[i]>hh[i-1] and C[i]>et[i]: el[i]=True
        if C[i]<lx[i-1]: xl[i]=True
    return el,xl

def _supertrend_dir(O,H,L,C, period=10, mult=3.0):
    a=atr(H,L,C,period); N=len(C); fub=[None]*N; flb=[None]*N; tr=[0]*N
    for i in range(N):
        if a[i] is None: continue
        hl2=(H[i]+L[i])/2; ub=hl2+mult*a[i]; lb=hl2-mult*a[i]
        if fub[i-1] is None: fub[i]=ub; flb[i]=lb; tr[i]=1; continue
        fub[i]=ub if (ub<fub[i-1] or C[i-1]>fub[i-1]) else fub[i-1]
        flb[i]=lb if (lb>flb[i-1] or C[i-1]<flb[i-1]) else flb[i-1]
        tr[i]=1 if C[i]>fub[i-1] else (-1 if C[i]<flb[i-1] else tr[i-1])
    return tr

def sig_supertrend(O,H,L,C, period=10, mult=3.0):
    """Supertrend(ATR 軌)順勢:趨勢翻多進場、翻空出場。高樣本、機械化。"""
    tr=_supertrend_dir(O,H,L,C,period,mult); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if tr[i]==1 and tr[i-1]!=1: el[i]=True
        if tr[i]==-1 and tr[i-1]!=-1: xl[i]=True
    return el,xl

def sig_keltner(O,H,L,C, ema_len=20, atr_len=10, mult=2.0, trend_len=100):
    """Keltner 通道突破:收盤突破 EMA+mult*ATR 上軌且站上長均線進場;跌破中軌出場。"""
    e=ema(C,ema_len); a=atr(H,L,C,atr_len); te=ema(C,trend_len); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (e[i],a[i],te[i]): continue
        if C[i] > e[i]+mult*a[i] and C[i]>te[i]: el[i]=True
        if C[i] < e[i]: xl[i]=True
    return el,xl

def sig_volbreak(O,H,L,C, k=1.0, atr_len=14, trend_len=100):
    """波動突破(Larry Williams 概念):收盤 > 前收 + k*ATR 且站上長均線進場;跌破長均線出場。"""
    a=atr(H,L,C,atr_len); te=ema(C,trend_len); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if a[i-1] is None or te[i] is None: continue
        if C[i] > C[i-1]+k*a[i-1] and C[i]>te[i]: el[i]=True
        if C[i] < te[i]: xl[i]=True
    return el,xl

def sig_ttm(O,H,L,C, n=20, bb_k=2.0, kc_m=1.5, minsq=6):
    """TTM/Bollinger-Keltner 擠壓突破:BB 縮進 KC(波動壓縮)連續≥minsq 棒,
       釋放且動能向上 -> 進場;跌破 EMA(n) -> 出場。壓縮→擴張機制(加密 4H 最佳)。"""
    mid=sma(C,n); sd=stdev(C,n); a=atr(H,L,C,n); em=ema(C,n); hh=highest(H,n); ll=lowest(L,n)
    N=len(C); el=[False]*N; xl=[False]*N; run=0
    for i in range(1,N):
        if None in (mid[i],sd[i],a[i],em[i],hh[i],ll[i]): run=0; continue
        bbu=mid[i]+bb_k*sd[i]; bbl=mid[i]-bb_k*sd[i]
        kcu=em[i]+kc_m*a[i]; kcl=em[i]-kc_m*a[i]
        squeeze = bbu<kcu and bbl>kcl
        mom = C[i]-((hh[i]+ll[i])/2+mid[i])/2
        if squeeze:
            run+=1
        else:
            if run>=minsq and mom>0: el[i]=True
            run=0
        if C[i]<em[i]: xl[i]=True
    return el,xl

def wma(src,n):
    out=[None]*len(src); denom=n*(n+1)/2
    for i in range(n-1,len(src)):
        out[i]=sum(src[i-n+1+j]*(j+1) for j in range(n))/denom
    return out

def sig_hma(O,H,L,C, n=20, trend=200):
    """Hull MA 斜率翻轉(近零延遲):HMA 斜率翻上且站上長均線進場;翻下出場。"""
    half=wma(C,max(2,n//2)); full=wma(C,n)
    raw=[(2*half[i]-full[i]) if (half[i] is not None and full[i] is not None) else None for i in range(len(C))]
    sq=max(2,int(round(n**0.5))); h=[None]*len(C)   # round(sqrt) 對齊 Pine ta.hma
    for i in range(len(C)):
        seg=raw[i-sq+1:i+1]
        if len(seg)==sq and all(v is not None for v in seg):
            d=sq*(sq+1)/2; h[i]=sum(seg[j]*(j+1) for j in range(sq))/d
    te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(2,N):
        if None in (h[i],h[i-1],h[i-2],te[i]): continue
        if h[i]>h[i-1] and h[i-1]<=h[i-2] and C[i]>te[i]: el[i]=True
        if h[i]<h[i-1] and h[i-1]>=h[i-2]: xl[i]=True
    return el,xl

def sig_rsi50(O,H,L,C, rsi_len=14, mid=50, trend=200):
    """RSI-50 收復(順勢回踩續勢):多頭中 RSI 由 <50 上穿回 50 進場;RSI<50 或跌破 SMA200 出場。"""
    rv=rsi(C,rsi_len); te=sma(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (rv[i],rv[i-1],te[i]): continue
        if rv[i-1]<=mid and rv[i]>mid and C[i]>te[i]: el[i]=True   # 對齊 Pine ta.crossover
        if rv[i]<mid or C[i]<te[i]: xl[i]=True
    return el,xl

def sig_macd(O,H,L,C, f=12, s=26, sig=9, trend=200):
    """MACD 趨勢:MACD 上穿訊號線且站上長均線進場;下穿出場。"""
    ef=ema(C,f); es=ema(C,s); m=[ef[i]-es[i] for i in range(len(C))]; sg=ema(m,sig); te=ema(C,trend)
    N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if te[i] is None: continue
        if m[i-1]<=sg[i-1] and m[i]>sg[i] and C[i]>te[i]: el[i]=True
        if m[i-1]>=sg[i-1] and m[i]<sg[i]: xl[i]=True
    return el,xl

def sig_psar(O,H,L,C, af0=0.02, step=0.02, afmax=0.2, trend=200):
    """Parabolic SAR 順勢:SAR 翻多且站上長均線進場;翻空出場。"""
    N=len(C); tr=[0]*N
    if N>=2:
        up=True; af=af0; ep=H[0]; sar=L[0]; tr[0]=1
        for i in range(1,N):
            psar=sar+af*(ep-sar)
            if up:
                psar=min(psar,L[i-1],L[i-2] if i>=2 else L[i-1])
                if H[i]>ep: ep=H[i]; af=min(af+step,afmax)
                if L[i]<psar: up=False; psar=ep; ep=L[i]; af=af0
            else:
                psar=max(psar,H[i-1],H[i-2] if i>=2 else H[i-1])
                if L[i]<ep: ep=L[i]; af=min(af+step,afmax)
                if H[i]>psar: up=True; psar=ep; ep=H[i]; af=af0
            sar=psar; tr[i]=1 if up else -1
    te=ema(C,trend); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if te[i] is None: continue
        if tr[i]==1 and tr[i-1]!=1 and C[i]>te[i]: el[i]=True
        if tr[i]==-1 and tr[i-1]!=-1: xl[i]=True
    return el,xl

def sig_kama(O,H,L,C, n=10, fast=2, slow=30, trend=200):
    """Kaufman 自適應均線交叉:盤整趨平減假訊號。收盤上穿 KAMA 且站上長均線進場;下穿出場。"""
    N=len(C); scf=2/(fast+1); scs=2/(slow+1); k=[None]*N
    for i in range(N):
        if i<n: k[i]=C[i]; continue
        ch=abs(C[i]-C[i-n]); vol=sum(abs(C[j]-C[j-1]) for j in range(i-n+1,i+1))
        er=ch/vol if vol>0 else 0; sc=(er*(scf-scs)+scs)**2
        k[i]=k[i-1]+sc*(C[i]-k[i-1])
    te=ema(C,trend); el=[False]*N; xl=[False]*N
    for i in range(n+1,N):
        if te[i] is None: continue
        if C[i-1]<=k[i-1] and C[i]>k[i] and C[i]>te[i]: el[i]=True
        if C[i-1]>=k[i-1] and C[i]<k[i]: xl[i]=True
    return el,xl

def sig_heikin(O,H,L,C, trend=200):
    """Heikin-Ashi 趨勢:HA 由紅翻綠且站上長均線進場;翻紅出場。"""
    N=len(C); hac=[None]*N; hao=[None]*N
    for i in range(N):
        hac[i]=(O[i]+H[i]+L[i]+C[i])/4
        hao[i]=(O[0]+C[0])/2 if i==0 else (hao[i-1]+hac[i-1])/2
    te=ema(C,trend); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if te[i] is None: continue
        up=hac[i]>hao[i]; upp=hac[i-1]>hao[i-1]
        if up and not upp and C[i]>te[i]: el[i]=True
        if not up: xl[i]=True
    return el,xl

def sig_ema_cross(O,H,L,C, fast=20, slow=50):
    """EMA 快慢線交叉:快線上穿慢線進場;下穿出場。"""
    ef=ema(C,fast); es=ema(C,slow); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (ef[i],es[i],ef[i-1],es[i-1]): continue
        if ef[i-1]<=es[i-1] and ef[i]>es[i]: el[i]=True
        if ef[i-1]>=es[i-1] and ef[i]<es[i]: xl[i]=True
    return el,xl

def sig_trend_pullback(O,H,L,C, trend=100, rsi_n=14, rsi_buy=40):
    """順勢回檔買進:價在長均線上(多頭)、RSI 回落到 rsi_buy 以下再轉上進場;跌破長均線出場。"""
    ma=ema(C,trend); rs=rsi(C,rsi_n); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(2,N):
        if None in (ma[i],rs[i],rs[i-1]): continue
        if C[i]>ma[i] and rs[i-1]<rsi_buy and rs[i]>=rsi_buy: el[i]=True
        if C[i]<ma[i]: xl[i]=True
    return el,xl

def sig_smc(O,H,L,C, pivot=5, trend_len=100):
    """市場結構突破(BOS)+ 失衡缺口(FVG)── 課程核心:確認 swing 後收盤突破前 swing 高、
       近期有多頭 FVG、且站上長均線 -> 進場;跌破前 swing 低 -> 出場。無未來函數。"""
    N=len(C); el=[False]*N; xl=[False]*N; te=ema(C,trend_len)
    fl=[False]*N
    for i in range(2,N):
        if L[i] > H[i-2]: fl[i]=True   # 多頭 FVG(三K缺口)
    lastSH=None; lastSL=None
    for i in range(N):
        j=i-pivot
        if j-pivot>=0:   # 嚴格樞紐(中心需比左右皆嚴格高/低),對齊 Pine ta.pivothigh/low
            if all(H[j]>H[k] for k in range(j-pivot,j+pivot+1) if k!=j): lastSH=H[j]
            if all(L[j]<L[k] for k in range(j-pivot,j+pivot+1) if k!=j): lastSL=L[j]
        rfl = any(fl[max(0,i-pivot):i+1])
        if lastSH is not None and C[i]>lastSH and (te[i] is not None and C[i]>te[i]) and rfl: el[i]=True
        if lastSL is not None and C[i]<lastSL: xl[i]=True
    return el,xl

def sig_rsi2dip(O,H,L,C, buy=2, sell=70, trend=200, fast=5):
    """深超賣剝頭皮(唯一通過手續費的剝頭皮,且限『掛單 maker』):
       長多頭(收>EMA200)中 RSI(2)<buy(極端超賣)-> 進場;RSI(2)>sell 或站回 EMA(fast) -> 出場。
       ⚠ 必須用『限價單(掛單/maker)』:逆勢天生掛單等成交。用市價單(taker)會賠。限 1H、ETH/LINK/LTC。
       搭配寬止損(3 ATR)。邊際薄、寬止損偶有大虧,風險% 請 ≤1%。"""
    r2=rsi(C,2); te=ema(C,trend); ef=ema(C,fast); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (r2[i],te[i],ef[i]): continue
        if r2[i]<buy and C[i]>te[i]: el[i]=True
        if r2[i]>sell or C[i]>ef[i]: xl[i]=True
    return el,xl

def sig_ibsdip(O,H,L,C, ibs_in=0.05, ibs_out=0.80, trend=200, rsi_exit=50):
    """IBS 深超賣剝頭皮(限掛單 maker):收盤位於當根區間極底(IBS<0.05)且長多頭 -> 掛限價進場;
       IBS>0.80 或 RSI(2)>50 -> 出場。寬止損 3 ATR。6 幣皆可,OOS 最穩。⚠ 限掛單/1H/風險%≤1%。"""
    te=ema(C,trend); r2=rsi(C,2); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if te[i] is None: continue
        rng=H[i]-L[i]; ibs=(C[i]-L[i])/rng if rng>0 else 0.5
        if ibs<ibs_in and C[i]>te[i]: el[i]=True
        if ibs>ibs_out or (r2[i] is not None and r2[i]>rsi_exit): xl[i]=True
    return el,xl

def sig_zdip(O,H,L,C, n=20, z_in=2.5, trend=200):
    """Z-score 深超賣剝頭皮(限掛單 maker):(收-SMA20)/SD < -2.5(極端偏離)且長多頭 -> 掛限價進場;
       回到均值(z>=0)-> 出場。寬止損 3 ATR。限 ETH/LINK/LTC。⚠ 限掛單/1H/風險%≤1%。"""
    mid=sma(C,n); sd=stdev(C,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (mid[i],sd[i],te[i]) or sd[i]==0: continue
        z=(C[i]-mid[i])/sd[i]
        if z<-z_in and C[i]>te[i]: el[i]=True
        if z>=0: xl[i]=True
    return el,xl

def sig_diadx(O,H,L,C, n=14, adx_min=20, trend=100):
    """DMI/ADX 方向動能:+DI 上穿 -DI 且 ADX>adx_min(趨勢夠強)、站上長均線 -> 進場;
       +DI 下穿 -DI -> 出場。Wilder 經典,四市場全通過(台股 PF 最高)。"""
    pdi,ndi,adx=dmi(H,L,C,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (pdi[i],ndi[i],adx[i],pdi[i-1],ndi[i-1],te[i]): continue
        if pdi[i-1]<=ndi[i-1] and pdi[i]>ndi[i] and adx[i]>adx_min and C[i]>te[i]: el[i]=True
        if pdi[i-1]>=ndi[i-1] and pdi[i]<ndi[i]: xl[i]=True
    return el,xl

def sig_vortex(O,H,L,C, n=14, trend=100):
    """Vortex 渦流順勢:VI+ 上穿 VI- 且站上長均線 -> 進場;VI+ 下穿 VI- -> 出場。四市場全通過。"""
    vip,vin=vortex(H,L,C,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (vip[i],vin[i],vip[i-1],vin[i-1],te[i]): continue
        if vip[i-1]<=vin[i-1] and vip[i]>vin[i] and C[i]>te[i]: el[i]=True
        if vip[i-1]>=vin[i-1] and vip[i]<vin[i]: xl[i]=True
    return el,xl

def sig_ichimoku(O,H,L,C, conv=9, base=26, spanb=52, trend=100):
    """Ichimoku 雲突破:收盤站上雲頂(前移26的Senkou) + 轉換線上穿基準線 -> 進場;
       跌破基準線 -> 出場。四市場全通過,機制獨特。無未來函數(雲取自過去前移)。"""
    N=len(C); ten=[None]*N; kij=[None]*N; sa=[None]*N; sb=[None]*N
    for i in range(N):
        if i>=conv-1: ten[i]=(max(H[i-conv+1:i+1])+min(L[i-conv+1:i+1]))/2
        if i>=base-1: kij[i]=(max(H[i-base+1:i+1])+min(L[i-base+1:i+1]))/2
        if i>=spanb-1: sb[i]=(max(H[i-spanb+1:i+1])+min(L[i-spanb+1:i+1]))/2
        if ten[i] is not None and kij[i] is not None: sa[i]=(ten[i]+kij[i])/2
    el=[False]*N; xl=[False]*N
    for i in range(base,N):
        ca=sa[i-base]; cb=sb[i-base]   # 雲前移 base 棒:對應當前 bar 的雲來自過去
        if None in (ten[i],kij[i],ca,cb,ten[i-1],kij[i-1]): continue
        if C[i]>max(ca,cb) and ten[i-1]<=kij[i-1] and ten[i]>kij[i]: el[i]=True
        if C[i]<kij[i]: xl[i]=True
    return el,xl

def sig_cci(O,H,L,C, n=20, trig=100, trend=100):
    """CCI 動能突破:CCI 上穿 +100(動能轉強)且站上長均線 -> 進場;CCI<0 -> 出場。四市場全通過。"""
    cc=cci(H,L,C,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (cc[i],cc[i-1],te[i]): continue
        if cc[i-1]<=trig and cc[i]>trig and C[i]>te[i]: el[i]=True
        if cc[i]<0: xl[i]=True
    return el,xl

def sig_bbreak(O,H,L,C, n=20, k=2.0, trend=100):
    """布林帶突破(用標準差,與 Keltner 用 ATR 不同):收盤突破上軌(SMA+k*SD)且站上長均線 -> 進場;
       跌破中軌 -> 出場。加密/美股/台股通過。"""
    mid=sma(C,n); sd=stdev(C,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (mid[i],sd[i],te[i]): continue
        if C[i]>mid[i]+k*sd[i] and C[i]>te[i]: el[i]=True
        if C[i]<mid[i]: xl[i]=True
    return el,xl

def sig_tsmom(O,H,L,C, look=40, trend=100):
    """時間序列動能(TSMOM,學術經典):過去 look 棒報酬由負翻正且站上長均線 -> 進場;
       報酬翻負 -> 出場。四市場全通過,美股 PF 2.24 最強。"""
    te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(look+1,N):
        if te[i] is None: continue
        m=C[i]-C[i-look]; mp=C[i-1]-C[i-1-look]
        if mp<=0 and m>0 and C[i]>te[i]: el[i]=True
        if m<0: xl[i]=True
    return el,xl

def sig_lrs(O,H,L,C, n=20, trend=100):
    """線性回歸斜率:回歸斜率由負翻正(趨勢轉上)且站上長均線 -> 進場;斜率翻負 -> 出場。
       加密/美股/台股通過。"""
    sl=linreg_slope(C,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (sl[i],sl[i-1],te[i]): continue
        if sl[i-1]<=0 and sl[i]>0 and C[i]>te[i]: el[i]=True
        if sl[i]<0: xl[i]=True
    return el,xl

def sig_crsi(O,H,L,C, lo=10, hi=70, trend=200, fast=5):
    """Connors RSI 逆勢(均值回歸):長多頭中 CRSI<lo(極端超賣)-> 進場;
       CRSI>hi 或站回 EMA(fast) -> 出場。美股/台股/貴金屬通過(勝率約67%)。逆勢、宜搭停利。"""
    cr=connors_rsi(C); te=ema(C,trend); ef=ema(C,fast); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (cr[i],te[i],ef[i]): continue
        if cr[i]<lo and C[i]>te[i]: el[i]=True
        if cr[i]>hi or C[i]>ef[i]: xl[i]=True
    return el,xl

def sig_vwap(O,H,L,C,V, n=20, trend=200):
    """VWAP 收復(量價均衡):多頭中收盤由下上穿滾動 VWAP(n) -> 進場;跌破 VWAP -> 出場。
       量能類最強(加密 4H);掛單(maker)更佳但市價(taker)亦可。需真實成交量。"""
    vw=vwap_roll(H,L,C,V,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (vw[i],vw[i-1],te[i]): continue
        if C[i-1]<=vw[i-1] and C[i]>vw[i] and C[i]>te[i]: el[i]=True
        if C[i]<vw[i]: xl[i]=True
    return el,xl

def sig_obv(O,H,L,C,V, ema_len=20, trend=200):
    """OBV 量能趨勢:OBV 上穿其 EMA(量能轉強)且站上長均線 -> 進場;OBV 跌破其 EMA -> 出場。需真實成交量。"""
    ob=obv(C,V); oe=ema(ob,ema_len); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (oe[i],oe[i-1],te[i]): continue
        if ob[i-1]<=oe[i-1] and ob[i]>oe[i] and C[i]>te[i]: el[i]=True
        if ob[i-1]>=oe[i-1] and ob[i]<oe[i]: xl[i]=True
    return el,xl

def sig_force(O,H,L,C,V, n=13, trend=200):
    """Force Index 力度:力度(收盤變動×量的EMA)由負翻正且站上長均線 -> 進場;翻負 -> 出場。需真實成交量。"""
    fi=force_idx(C,V,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (fi[i],fi[i-1],te[i]): continue
        if fi[i-1]<=0 and fi[i]>0 and C[i]>te[i]: el[i]=True
        if fi[i]<0: xl[i]=True
    return el,xl

def sig_cmf(O,H,L,C,V, n=20, trend=100):
    """Chaikin 資金流:CMF 由負轉正(買盤資金流入)且站上長均線 -> 進場;CMF<0 -> 出場。需真實成交量。"""
    cm=cmf(H,L,C,V,n); te=ema(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if None in (cm[i],cm[i-1],te[i]): continue
        if cm[i-1]<=0 and cm[i]>0 and C[i]>te[i]: el[i]=True
        if cm[i]<0: xl[i]=True
    return el,xl

def sig_wbottom(O,H,L,C, piv=5, tol=0.03):
    """雙重底 / 三重底 反轉(W 底):兩個(或更多)相近的低點 + 中間頸線高點;
       收盤『突破頸線』-> 進場(抓反轉);收盤跌破底部 -> 出場(型態失敗)。搭配 2~3% 動態鎖利(見註冊表)。
       無未來函數(樞紐需 piv 根確認後才成立)。tol=兩低點相近容差(預設 3%)。"""
    N=len(C); el=[False]*N; xl=[False]*N
    pl=[]; ph=[]; neck=None; patt_low=None; armed=False
    for i in range(N):
        j=i-piv
        if j-piv>=0:
            seg=range(j-piv,j+piv+1)
            if all(L[j]<L[k] for k in seg if k!=j):
                pl.append((j,L[j]))
                if len(pl)>=2:
                    (i1,l1),(i2,l2)=pl[-2],pl[-1]
                    if l1>0 and abs(l2-l1)/l1 < tol:           # 兩低點相近 = 雙重底
                        necks=[h for (hi,h) in ph if i1<hi<i2]
                        if necks: neck=max(necks); patt_low=min(l1,l2); armed=True
            if all(H[j]>H[k] for k in seg if k!=j): ph.append((j,H[j]))
        if armed and neck is not None and i>=1 and C[i-1]<=neck and C[i]>neck:
            el[i]=True; armed=False                            # 突破頸線進場(一次)
        if patt_low is not None and C[i]<patt_low: xl[i]=True  # 跌破底部=型態失敗(備援;主要靠%鎖利)
    return el,xl

def sig_trend3(O,H,L,C, piv=3, tol=0.02):
    """三點一線 趨勢線 突破/跌破(短週期):用最近 3 個樞紐高點連成『壓力線』(三點近似一直線),
       收盤突破壓力線 -> 進場(多);用最近 3 個樞紐低點連成『支撐線』,收盤跌破支撐線 -> 出場(空)。
       無未來函數(樞紐 piv 根確認)。tol=三點共線容差(預設 2%);piv 小=短週期較敏感。"""
    N=len(C); el=[False]*N; xl=[False]*N; ph=[]; pl=[]
    def line3(pts):    # 三點是否近似一直線;回 (x1,y1,斜率) 或 None
        (x1,y1),(x2,y2),(x3,y3)=pts
        if x3==x1 or y2==0: return None
        m=(y3-y1)/(x3-x1); yline=y1+m*(x2-x1)
        return (x1,y1,m) if abs(y2-yline)/abs(y2) < tol else None
    for i in range(N):
        j=i-piv
        if j-piv>=0:
            seg=range(j-piv,j+piv+1)
            if all(H[j]>H[k] for k in seg if k!=j): ph.append((j,H[j]))
            if all(L[j]<L[k] for k in seg if k!=j): pl.append((j,L[j]))
        if len(ph)>=3 and i>=1:
            c=line3(ph[-3:])
            if c:
                x1,y1,m=c
                if C[i-1]<=(y1+m*(i-1-x1)) and C[i]>(y1+m*(i-x1)): el[i]=True   # 突破壓力線
        if len(pl)>=3 and i>=1:
            c=line3(pl[-3:])
            if c:
                x1,y1,m=c
                if C[i-1]>=(y1+m*(i-1-x1)) and C[i]<(y1+m*(i-x1)): xl[i]=True   # 跌破支撐線
    return el,xl

def sig_rsi(O,H,L,C, rsi_len=14, oversold=30, overbot=70):
    r=rsi(C,rsi_len); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if r[i] is None or r[i-1] is None: continue
        if r[i-1]<oversold and r[i]>=oversold: el[i]=True   # 由超賣向上穿回
        if r[i]>=overbot: xl[i]=True
    return el,xl

# ============================ 策略註冊表 ============================
# build(O,H,L,C,V,tf)->(el,xl);V=成交量(量能策略用,其餘忽略);atr_stop/atr_trail/atr_tp 為風控(ATR 倍)。
# 全部經真實成本 0.24% + IS/OOS + 足夠樣本驗證;不合格/樣本過少者不列入。
def sig_pullbk(O,H,L,C, trend=100, rn=14, dip=45, ex=62):
    """順勢回檔買 2.0:上升趨勢(收盤>SMA)中,RSI 自低位(<dip)回升才做多;回到高位或趨勢轉空平。
       實測:美股日線多方 PF≈1.2、IS/OOS 皆正(買回檔不接刀)。回傳 (el,xl) 只做多。"""
    r=rsi(C,rn); m=sma(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(N):
        if r[i] is None or m[i] is None: continue
        if i>0 and r[i-1] is not None and C[i]>m[i] and r[i-1]<dip<=r[i]: el[i]=True
        if r[i]>=ex or C[i]<m[i]: xl[i]=True
    return el, xl

def sig_rolltrend(O,H,L,C, n_enter=20, trend=100):
    """順勢滾倉『進場訊號』:突破 n_enter 日高 + 收盤在 SMA(trend) 之上(多頭)。
       加碼與吊燈出場由滾倉引擎 _simulate_pyramid(回測)/ update_combo(實盤)處理。回傳 (el,xl)。"""
    he=highest(H,n_enter); m=sma(C,trend); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if he[i-1] is None or m[i] is None: continue
        if H[i]>=he[i-1] and C[i]>m[i]: el[i]=True
    return el, xl

def sig_vbreakr(O,H,L,C, trend=100, k=1.0, atrn=14):
    """波動突破(趨勢過濾):上升趨勢中,收盤向上突破(>昨收+k×ATR)才做多;趨勢轉空或向下突破平。
       實測:美股日線多方 PF≈1.7、OOS+1.7%(NVDA/AAPL/GOOGL 強)。回傳 (el,xl) 只做多。"""
    m=sma(C,trend); a=atr(H,L,C,atrn); N=len(C); el=[False]*N; xl=[False]*N
    for i in range(1,N):
        if m[i] is None or a[i-1] is None: continue
        if C[i]>m[i] and C[i]>C[i-1]+k*a[i-1]: el[i]=True
        if C[i]<m[i] or C[i]<C[i-1]-k*a[i-1]: xl[i]=True
    return el, xl

STRATS = {
    "sixline":   dict(name="六條線 多頭排列(課程核心・最強)", build=lambda O,H,L,C,V,tf: sig_sixline(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),   # 放寬追蹤止盈→讓贏家奔跑(實測增利)
    "trend":     dict(name="順勢 EMA20/100(通用)",          build=lambda O,H,L,C,V,tf: sig_trend(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "donchian":  dict(name="Donchian 突破(抗成本)",          build=lambda O,H,L,C,V,tf: sig_donchian(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "ttm":       dict(name="TTM 擠壓突破(加密4H最強突破)",     build=lambda O,H,L,C,V,tf: sig_ttm(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "keltner":   dict(name="Keltner 通道突破(跨市場突破)",      build=lambda O,H,L,C,V,tf: sig_keltner(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "supertrend":dict(name="Supertrend(ATR順勢・高樣本)",    build=lambda O,H,L,C,V,tf: sig_supertrend(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "volbreak":  dict(name="波動突破(順勢;貴金屬最佳)",      build=lambda O,H,L,C,V,tf: sig_volbreak(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "smc":       dict(name="SMC 結構突破+FVG(課程核心)",     build=lambda O,H,L,C,V,tf: sig_smc(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "hma":       dict(name="Hull MA 斜率翻轉(低延遲順勢)",   build=lambda O,H,L,C,V,tf: sig_hma(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "rsi50":     dict(name="RSI-50 收復(順勢回踩續勢)",      build=lambda O,H,L,C,V,tf: sig_rsi50(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "tsmom":     dict(name="時間序列動能(四市場全過・美股最強)", build=lambda O,H,L,C,V,tf: sig_tsmom(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "ichimoku":  dict(name="Ichimoku 雲突破(四市場全過)",     build=lambda O,H,L,C,V,tf: sig_ichimoku(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "cci":       dict(name="CCI 動能突破(四市場全過)",        build=lambda O,H,L,C,V,tf: sig_cci(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "vortex":    dict(name="Vortex 渦流順勢(四市場全過)",     build=lambda O,H,L,C,V,tf: sig_vortex(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "diadx":     dict(name="DMI/ADX 方向動能(四市場全過・台股最強)", build=lambda O,H,L,C,V,tf: sig_diadx(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "bbreak":    dict(name="布林帶突破(加密/美股/台股)",      build=lambda O,H,L,C,V,tf: sig_bbreak(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "lrs":       dict(name="線性回歸斜率(加密/美股/台股)",    build=lambda O,H,L,C,V,tf: sig_lrs(O,H,L,C),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "macd":      dict(name="MACD 趨勢",                       build=lambda O,H,L,C,V,tf: sig_macd(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "psar":      dict(name="Parabolic SAR 順勢",              build=lambda O,H,L,C,V,tf: sig_psar(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "kama":      dict(name="KAMA 自適應均線(貴金屬佳)",      build=lambda O,H,L,C,V,tf: sig_kama(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "heikin":    dict(name="Heikin-Ashi 趨勢(貴金屬佳)",     build=lambda O,H,L,C,V,tf: sig_heikin(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "ema_cross": dict(name="EMA 快慢線交叉(經典)",          build=lambda O,H,L,C,V,tf: sig_ema_cross(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "pullback":  dict(name="順勢回檔買進(貴金屬佳)",        build=lambda O,H,L,C,V,tf: sig_trend_pullback(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "pullbk":    dict(name="順勢回檔買 2.0(上升趨勢買回檔・美股佳)", build=lambda O,H,L,C,V,tf: sig_pullbk(O,H,L,C),
                      atr_stop=2.5, atr_trail=0.0, atr_tp=0.0),
    "vbreakr":   dict(name="波動突破(趨勢過濾・美股最強)",    build=lambda O,H,L,C,V,tf: sig_vbreakr(O,H,L,C),
                      atr_stop=0.0, atr_trail=3.0, atr_tp=0.0),
    "rolltrend": dict(name="順勢滾倉(加碼+寬止損+吊燈追蹤・美股日線)", build=lambda O,H,L,C,V,tf: sig_rolltrend(O,H,L,C),
                      atr_stop=0.0, atr_trail=0.0, atr_tp=0.0,
                      pyramid=dict(init_atr=3.0, trail_atr=4.0, add_atr=1.0, max_adds=4)),
    "rsi":       dict(name="RSI 均值回歸(逆勢/震盪)",        build=lambda O,H,L,C,V,tf: sig_rsi(O,H,L,C),
                      atr_stop=2.0, atr_trail=0.0, atr_tp=3.0),
    "crsi":      dict(name="Connors RSI 逆勢(美股/台股/金屬)", build=lambda O,H,L,C,V,tf: sig_crsi(O,H,L,C),
                      atr_stop=2.0, atr_trail=0.0, atr_tp=3.0),
    "vwap":      dict(name="VWAP 收復(量能・加密4H最佳)",     build=lambda O,H,L,C,V,tf: sig_vwap(O,H,L,C,V),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "obv":       dict(name="OBV 量能趨勢(加密4H)",            build=lambda O,H,L,C,V,tf: sig_obv(O,H,L,C,V),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "force":     dict(name="Force Index 力度(量能・加密4H)",  build=lambda O,H,L,C,V,tf: sig_force(O,H,L,C,V),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "cmf":       dict(name="Chaikin 資金流(量能・加密4H)",    build=lambda O,H,L,C,V,tf: sig_cmf(O,H,L,C,V),
                      atr_stop=3.0, atr_trail=8.0, atr_tp=0.0),
    "wbottom":   dict(name="雙重/三重底反轉(2~3%動態鎖利)",  build=lambda O,H,L,C,V,tf: sig_wbottom(O,H,L,C),
                      atr_stop=0.0, atr_trail=0.0, atr_tp=0.0, pct_stop=0.03, pct_trail=0.025),
    "trend3":    dict(name="三點一線趨勢線 突破/跌破(短週期)", build=lambda O,H,L,C,V,tf: sig_trend3(O,H,L,C),
                      atr_stop=3.0, atr_trail=5.0, atr_tp=0.0),
    "rsi2dip":   dict(name="深超賣剝頭皮 RSI2(1H・限掛單maker)", build=lambda O,H,L,C,V,tf: sig_rsi2dip(O,H,L,C),
                      atr_stop=3.0, atr_trail=0.0, atr_tp=0.0),
    "ibsdip":    dict(name="深超賣剝頭皮 IBS(1H・限掛單maker)",  build=lambda O,H,L,C,V,tf: sig_ibsdip(O,H,L,C),
                      atr_stop=3.0, atr_trail=0.0, atr_tp=0.0),
    "zdip":      dict(name="深超賣剝頭皮 Z-score(1H・限掛單maker)", build=lambda O,H,L,C,V,tf: sig_zdip(O,H,L,C),
                      atr_stop=3.0, atr_trail=0.0, atr_tp=0.0),
}
# 34 種單一資產策略(可 API 自動下單),全部真實成本 + IS/OOS + 足夠樣本驗證、長期正回報(各依其適用市場)。
# (含 4 種『量能』vwap/obv/force/cmf 需成交量、僅加密;wbottom 用 2~3% 動態鎖利;trend3=三點一線趨勢線。)
STRAT_ORDER = ["sixline","ttm","keltner","donchian","supertrend","volbreak","smc","hma","rsi50",
               "tsmom","ichimoku","cci","vortex","diadx","bbreak","lrs",
               "macd","psar","kama","heikin","ema_cross","pullback","pullbk","vbreakr","rolltrend","trend",
               "vwap","obv","force","cmf","wbottom","trend3","rsi","crsi",
               "rsi2dip","ibsdip","zdip"]

# 各時間框架:回測抓取天數(避免小時框抓太多)
TF_DAYS = {"5m":45, "15m":120, "30m":250, "1h":540, "2h":720, "4h":900, "1d":1500}

# ============================ 模擬器(long-only)============================
def _simulate(T,O,H,L,C, el, xl, A, atr_stop, atr_trail, atr_tp, risk_pct, max_lev, start,
              pct_stop=0.0, pct_trail=0.0, pct_tp=0.0):
    """長多模擬。風控可用 ATR 倍(atr_*)或『百分比價格』(pct_*,如 pct_trail=0.025=回檔2.5%鎖利)。
       pct_* > 0 時優先採用百分比式(動態鎖利);否則用 ATR 式。"""
    N=len(C); eq=start; pos=0; entry=0.0; qty=0.0; stop=None; tp=None; peak=None
    entry_date=None; entry_idx=None
    dates=[]; equity=[]; trades=[]; trade_log=[]
    cost=lambda px: px*(COMMISSION+SLIPPAGE)
    use_pct = (pct_stop>0 or pct_trail>0 or pct_tp>0)
    for i in range(N-1):
        o2=O[i+1]
        if pos>0:
            av=A[i]
            if pct_trail>0:                                   # 百分比動態鎖利:回檔 pct_trail 即出場(隨新高上移)
                peak=max(peak if peak is not None else -1e18, H[i])
                ns=peak*(1.0-pct_trail)
                stop=ns if stop is None else max(stop,ns)
            elif atr_trail>0 and av is not None:
                peak=max(peak if peak is not None else -1e18, H[i])
                ns=peak-atr_trail*av
                stop=ns if stop is None else max(stop,ns)
            exit_px=None; exit_i=None
            if stop is not None and L[i]<=stop: exit_px=min(stop,O[i]); exit_i=i
            elif tp is not None and H[i]>=tp: exit_px=tp; exit_i=i
            if exit_px is not None:
                pnl=qty*(exit_px-entry)-qty*cost(exit_px)-qty*cost(entry); eq+=pnl; trades.append(pnl)
                exit_date=datetime.datetime.utcfromtimestamp(T[exit_i]/1000)
                trade_log.append({'entry_px':round(entry,2),'exit_px':round(exit_px,2),
                    'entry_date':entry_date,'exit_date':exit_date,
                    'ret':round((exit_px-entry)/entry*100,2)})
                pos=0; qty=0.0; stop=tp=peak=None; entry_date=None
        if pos>0 and xl[i]:
            pnl=qty*(o2-entry)-qty*cost(o2)-qty*cost(entry); eq+=pnl; trades.append(pnl)
            exit_date=datetime.datetime.utcfromtimestamp(T[i+1]/1000)
            trade_log.append({'entry_px':round(entry,2),'exit_px':round(o2,2),
                'entry_date':entry_date,'exit_date':exit_date,
                'ret':round((o2-entry)/entry*100,2)})
            pos=0; qty=0.0; stop=tp=peak=None; entry_date=None
        if pos==0 and el[i]:
            av=A[i]
            ok = (av is not None and av>0) if not use_pct else True
            if ok:
                entry=o2; entry_date=datetime.datetime.utcfromtimestamp(T[i+1]/1000); entry_idx=i+1
                stop_dist = (pct_stop*entry) if (use_pct and pct_stop>0) else (atr_stop*av if (av and atr_stop>0) else 0)
                qty=min((eq*risk_pct)/stop_dist, (eq*max_lev)/entry) if (risk_pct>0 and stop_dist>0) else (eq)/entry
                pos=1; peak=H[i]
                if use_pct:
                    stop=entry*(1.0-pct_stop) if pct_stop>0 else None
                    tp=entry*(1.0+pct_tp) if pct_tp>0 else None
                else:
                    stop=C[i]-atr_stop*av if atr_stop>0 else None
                    tp=C[i]+atr_tp*av if atr_tp>0 else None
        mtm=eq + (qty*(C[i+1]-entry) if pos>0 else 0)
        dates.append(datetime.datetime.utcfromtimestamp(T[i+1]/1000)); equity.append(mtm)
    # 如果還在場內，記錄未出場的進場資訊
    if pos>0 and entry_date:
        trade_log.append({'entry_px':round(entry,2),'exit_px':None,
            'entry_date':entry_date,'exit_date':None,'ret':None,'open':True})
    return dates, equity, trades, trade_log

def _simulate_pyramid(T,O,H,L,C, el, A, init_atr, trail_atr, add_atr, max_adds, risk_pct, max_lev, start):
    """順勢滾倉(加碼)回測。回傳 (dates,equity,trades,trade_log)。
    trade_log 每筆包含完整進出場資訊及加碼明細 add_log。"""
    N=len(C); eq=start; pos=False; entries=[]; peak=0.0; stop=None; last_add=0.0; adds=0
    cost=lambda px: px*(COMMISSION+SLIPPAGE)
    dates=[]; equity=[]; trades=[]; trade_log=[]
    entry_date=None; add_log=[]  # 本次進場的加碼紀錄
    tq=lambda: sum(q for _,q in entries)
    for i in range(N-1):
        o2=O[i+1]; av=A[i]
        if pos and av:
            peak=max(peak,H[i]); ns=peak-trail_atr*av; stop=ns if stop is None else max(stop,ns)
            if L[i]<=stop:                                       # 吊燈止損 → 全部出場
                ex=min(stop,O[i])
                avg_entry=sum(ep*q for ep,q in entries)/tq() if entries else 0
                pnl=sum(q*(ex-ep) for ep,q in entries)-sum(q*(cost(ex)+cost(ep)) for ep,q in entries)
                eq+=pnl; trades.append(pnl)
                exit_date=datetime.datetime.utcfromtimestamp(T[i]/1000)
                trade_log.append({
                    'entry_px':round(avg_entry,2),'exit_px':round(ex,2),
                    'entry_date':entry_date,'exit_date':exit_date,
                    'ret':round((ex-avg_entry)/avg_entry*100,2) if avg_entry else 0,
                    'add_log': add_log[:],  # 加碼明細
                    'is_pyramid': True
                })
                pos=False; entries=[]; stop=None; adds=0; peak=0.0; entry_date=None; add_log=[]
            elif adds<max_adds and C[i]>=last_add+add_atr*av:    # 順勢加碼(滾倉)
                sd=trail_atr*av
                want=min((eq*risk_pct)/sd, (eq*max_lev)/o2 - tq()) if sd>0 else 0
                if want>0:
                    entries.append((o2,want)); last_add=C[i]; adds+=1
                    add_date=datetime.datetime.utcfromtimestamp(T[i+1]/1000)
                    add_log.append({'px':round(o2,2),'date':add_date,'n':adds})
        if (not pos) and av and av>0 and el[i]:                  # 突破進場(首手)
            entry=o2; sd=init_atr*av
            q=min((eq*risk_pct)/sd, (eq*max_lev)/entry) if sd>0 else 0
            if q>0:
                pos=True; entries=[(entry,q)]; peak=H[i]
                stop=entry-init_atr*av; last_add=C[i]; adds=0
                entry_date=datetime.datetime.utcfromtimestamp(T[i+1]/1000)
                add_log=[]
        avg=(sum(ep*q for ep,q in entries)/tq()) if entries else 0
        mtm=eq + (tq()*(C[i+1]-avg) if pos else 0)
        dates.append(datetime.datetime.utcfromtimestamp(T[i+1]/1000)); equity.append(mtm)
    # 還在場內
    if pos and entries and entry_date:
        avg_entry=sum(ep*q for ep,q in entries)/tq() if entries else 0
        trade_log.append({
            'entry_px':round(avg_entry,2),'exit_px':None,
            'entry_date':entry_date,'exit_date':None,'ret':None,
            'add_log': add_log[:], 'is_pyramid': True, 'open': True
        })
    return dates, equity, trades, trade_log

def run_backtest(ohlcv, strategy="trend", risk_pct=0.015, max_lev=3.0, start=10000.0,
                 timeframe=None, atr_len=14):
    """ohlcv=[[ts_ms,o,h,l,c,v],...]。回傳 (dates,equity,stats) 或 None。"""
    if len(ohlcv) < 220: return None     # 需足夠暖機(六條線含 EMA200)
    T=[r[0] for r in ohlcv]; O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]; L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
    V=[(r[5] if len(r)>5 else 0.0) for r in ohlcv]
    s=STRATS.get(strategy, STRATS["trend"])
    el,xl=s["build"](O,H,L,C,V,timeframe)
    A=atr(H,L,C,atr_len)
    if s.get("pyramid"):
        pp=s["pyramid"]
        dates,equity,trades,trade_log=_simulate_pyramid(T,O,H,L,C, el, A,
                                              pp["init_atr"], pp["trail_atr"], pp["add_atr"], pp["max_adds"],
                                              risk_pct, max_lev, start)
    else:
        dates,equity,trades,trade_log=_simulate(T,O,H,L,C, el,xl, A,
                                      s["atr_stop"], s["atr_trail"], s["atr_tp"],
                                      risk_pct, max_lev, start,
                                      s.get("pct_stop",0.0), s.get("pct_trail",0.0), s.get("pct_tp",0.0))
    if not equity: return None
    base=equity[0]; peak=base; mdd=0.0
    for v in equity:
        peak=max(peak,v); mdd=max(mdd,(peak-v)/peak if peak>0 else 0)
    yrs=max((dates[-1]-dates[0]).days/365.25, 1e-9) if dates else 1
    cagr=((equity[-1]/base)**(1/yrs)-1)*100 if equity and equity[-1]>0 and base>0 else 0
    rets=[equity[i]/equity[i-1]-1 for i in range(1,len(equity)) if equity[i-1]>0]
    mu=sum(rets)/len(rets) if rets else 0
    sd=math.sqrt(sum((x-mu)**2 for x in rets)/len(rets)) if rets else 0
    bars_per_yr=len(rets)/yrs if yrs>0 else 252
    sharpe=mu/sd*math.sqrt(bars_per_yr) if sd>0 else 0
    w=[t for t in trades if t>0]; l=[t for t in trades if t<0]
    win=len(w)/len(trades)*100 if trades else 0
    payoff=(sum(w)/len(w))/(-sum(l)/len(l)) if w and l else 0
    stats={"cagr":cagr,"mdd":mdd*100,"sharpe":sharpe,"win":win,"trades":len(trades),
           "payoff":payoff,"total":(equity[-1]/base-1)*100 if equity else 0,"years":yrs,
           "strategy":strategy,"trade_log":trade_log}
    return dates, equity, stats

# ============================ 抓資料 ============================
def fetch_ccxt(exchange, symbol, timeframe, days=900):
    """分頁抓加密(任一 ccxt 交易所)約 days 天歷史。"""
    import ccxt, time
    dtype = "swap" if exchange in ("bybit","pionex","okx","gate") else "future"
    ex=getattr(ccxt, exchange)({"enableRateLimit":True,"options":{"defaultType":dtype}})
    tf_ms=ex.parse_timeframe(timeframe)*1000
    since=ex.milliseconds()-int(days*86400*1000); now=ex.milliseconds()
    out=[]; seen=set()
    while since<now:
        batch=ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch: break
        for r in batch:
            if r[0] not in seen: seen.add(r[0]); out.append(r)
        nxt=batch[-1][0]+tf_ms
        if nxt<=since: break
        since=nxt; time.sleep(ex.rateLimit/1000)
    out.sort(key=lambda r:r[0]); return out

def fetch_yf(ticker, start="2017-01-01", interval="1d"):
    """抓股票/黃金/貴金屬(免費 yfinance),回傳 ccxt 格式 [ts_ms,o,h,l,c,v]。
       支援日內:yfinance 無 4h(自動以 1h 替代);日內歷史有限(<1h≈60天、1h≈730天)。"""
    import yfinance as yf
    iv = {"5m":"5m","15m":"15m","30m":"30m","1h":"1h","4h":"1h","1d":"1d","1wk":"1wk"}.get(interval,"1d")
    kw = dict(interval=iv, progress=False, auto_adjust=True)
    if iv in ("5m","15m","30m"): kw["period"]="60d"     # yfinance 日內資料上限
    elif iv=="1h":               kw["period"]="730d"
    else:                        kw["start"]=start
    d=yf.download(ticker, **kw)
    out=[]
    for ts,row in d.iterrows():
        try: o=float(row["Open"]); h=float(row["High"]); l=float(row["Low"]); c=float(row["Close"])
        except Exception: continue
        if c>0: out.append([int(ts.timestamp()*1000), o, h, l, c, 0.0])
    return out

def market_cost(spec, strategy=None):
    """各市場真實『單邊』成本(來回=2倍)。台股含 0.3% 賣出證交稅是硬成本,務必正確計入。"""
    if strategy in ("rsi2dip","ibsdip","zdip"): return (0.0002, 0.0)      # 限掛單 maker ~0.04% 來回
    if spec[0]=="ccxt": return (0.0004, 0.0002)                            # 加密 taker ~0.12% 來回
    tk = spec[1]
    if tk.endswith(".TW"): return (0.00225, 0.0)                           # 台股 ≈0.45% 來回(手續費+0.3%證交稅)
    if tk in ("GC=F","SI=F","PL=F","PA=F"): return (0.0002, 0.0001)        # 商品期貨 ~0.06% 來回
    if tk in ("GLD","SLV"): return (0.0003, 0.0)                           # 金屬 ETF ~0.06% 來回
    return (0.00015, 0.00005)                                             # 美股(多數零佣)~0.04% 來回

def backtest_product(spec, timeframe, risk_pct=0.015, days=None, strategy="trend"):
    """spec=('ccxt',exchange,symbol) 或 ('yf',ticker)。回傳 (dates,equity,stats)。
       依市場套用真實費率(台股含 0.3% 證交稅),避免試算過度樂觀。"""
    global COMMISSION, SLIPPAGE
    if days is None: days = TF_DAYS.get(timeframe, 900)
    COMMISSION, SLIPPAGE = market_cost(spec, strategy)
    o = fetch_yf(spec[1], interval=timeframe) if spec[0]=="yf" else fetch_ccxt(spec[1], spec[2], timeframe, days)
    return run_backtest(o, strategy=strategy, risk_pct=risk_pct, timeframe=timeframe)

def backtest_symbol(symbol, timeframe, risk_pct=0.015, days=900, strategy="trend"):   # 向後相容
    return backtest_product(("ccxt","binanceusdm",symbol), timeframe, risk_pct, days, strategy)

if __name__=="__main__":
    import sys
    sym=sys.argv[1] if len(sys.argv)>1 else "SOL/USDT"; tf=sys.argv[2] if len(sys.argv)>2 else "4h"
    strat=sys.argv[3] if len(sys.argv)>3 else "trend"
    spec=("ccxt","binanceusdm",sym) if "/" in sym else ("yf",sym)
    r=backtest_product(spec, tf, strategy=strat)
    if r:
        d,e,s=r
        print(f"{sym} {tf} [{strat}]  期間 {d[0].date()}~{d[-1].date()}  {s['years']:.1f}年")
        print(f"  總報酬 {s['total']:+.1f}%  CAGR {s['cagr']:+.1f}%  回撤 {s['mdd']:.1f}%  夏普 {s['sharpe']:.2f}  勝率 {s['win']:.0f}%  交易 {s['trades']}")
    else:
        print("資料不足")

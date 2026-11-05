// ── Lightweight Charts 繪圖 ──────────────────────────────
// 日內時間字串(例 "2026-01-05 08:00")是 UTC 時間;一律以 UTC 解析,不受瀏覽器所在時區影響。
function toTime(dateStr){
  if(dateStr.length>10){
    const iso=dateStr.replace(' ','T')+(dateStr.length<=16?':00':'')+'Z';
    return Math.floor(Date.parse(iso)/1000);
  }
  return dateStr;
}

// 權益曲線(策略 vs 買進持有)+ 回撤。時間為 epoch 秒(UTC),來源是 /api/analyze 的 backtest 區塊。
function drawBacktestCurves(eqEl, ddEl, bt, intraday){
  const uniq = arr => { const m=new Map(); arr.forEach(([t,v])=>m.set(t,v)); return [...m.entries()].sort((a,b)=>a[0]-b[0]).map(([time,value])=>({time,value})); };
  const opts = {...CHART_OPTS, timeScale:{borderColor:'rgba(255,255,255,0.1)', timeVisible:!!intraday}};
  const pf = {type:'custom', formatter:v=>v.toFixed(1)+'%'};
  const eqChart = LightweightCharts.createChart(eqEl, {...opts, height:eqEl.clientHeight||260});
  const sEq = eqChart.addLineSeries({color:'#26a69a', lineWidth:2, priceLineVisible:false, lastValueVisible:true, title:'策略', priceFormat:pf});
  const eqData = uniq(bt.equity); sEq.setData(eqData);
  let sBh=null;
  if(bt.buyHold && bt.buyHold.length){
    sBh = eqChart.addLineSeries({color:'#8b90a0', lineWidth:1.5, lineStyle:2, priceLineVisible:false, lastValueVisible:true, title:'買進持有', priceFormat:pf});
    sBh.setData(uniq(bt.buyHold));
  }
  sEq.createPriceLine({price:0, color:'rgba(255,255,255,0.25)', lineWidth:1, lineStyle:1, axisLabelVisible:false});
  const ddChart = LightweightCharts.createChart(ddEl, {...opts, height:ddEl.clientHeight||120});
  const sDd = ddChart.addHistogramSeries({color:'rgba(239,83,80,0.55)', priceLineVisible:false, lastValueVisible:false, priceFormat:pf});
  const ddData = uniq(bt.drawdown); sDd.setData(ddData);
  eqChart.timeScale().fitContent(); ddChart.timeScale().fitContent();
  // 兩張圖的時間軸同步(用時間範圍,因為兩條曲線的資料點數可能不同)
  let busy=false;
  const link=(a,b)=>a.timeScale().subscribeVisibleTimeRangeChange(r=>{ if(!r||busy) return; busy=true; try{ b.timeScale().setVisibleRange(r); }catch(e){} busy=false; });
  link(eqChart,ddChart); link(ddChart,eqChart);
  // 十字線讀數(同一時間的策略 / 買進持有 / 回撤)
  const tip=document.createElement('div');
  tip.style.cssText='position:absolute;left:8px;top:6px;z-index:5;font-size:11px;color:#e8eaf0;background:rgba(20,24,36,0.85);padding:3px 8px;border-radius:6px;pointer-events:none;display:none;';
  eqEl.style.position='relative'; eqEl.appendChild(tip);
  const fmtT = t => { const d=new Date(t*1000); const p=n=>String(n).padStart(2,'0'); return d.getUTCFullYear()+'-'+p(d.getUTCMonth()+1)+'-'+p(d.getUTCDate())+(intraday?' '+p(d.getUTCHours())+':'+p(d.getUTCMinutes()):''); };
  const ddMap=new Map(ddData.map(d=>[d.time,d.value]));
  eqChart.subscribeCrosshairMove(p=>{
    if(!p||!p.time||!p.seriesData){ tip.style.display='none'; return; }
    const a=p.seriesData.get(sEq), b=sBh?p.seriesData.get(sBh):null;
    if(!a){ tip.style.display='none'; return; }
    const dd=ddMap.get(p.time);
    tip.innerHTML=`${fmtT(p.time)} · <span style="color:#26a69a">策略 ${fmtPct(a.value,1)}</span>`+(b?` · <span style="color:#8b90a0">買進持有 ${fmtPct(b.value,1)}</span>`:'')+(dd!=null?` · 回撤 ${dd.toFixed(1)}%`:'');
    tip.style.display='block';
  });
  return [eqChart, ddChart];
}

function buildChartsInContainer(container,data,indicators,height){
  const charts=[];
  const prices=data.prices;
  const dates=data.dates;
  const diff=calcEMADiff(data.ema20,data.ema50);
  const {K,D}=calcKD(prices);
  const rsiVals=calcRSI(prices);

  // ── 偵測是否為觸控裝置 ──
  const isTouch = ('ontouchstart' in window) || navigator.maxTouchPoints > 0;

  // ── 電腦版浮動 tooltip ──
  const tooltip=document.createElement('div');
  tooltip.style.cssText='position:absolute;z-index:100;display:none;background:rgba(20,24,36,0.97);border:1px solid rgba(255,255,255,0.12);border-radius:8px;padding:8px 12px;font-size:11px;color:#e8eaf0;pointer-events:none;white-space:nowrap;box-shadow:0 4px 16px rgba(0,0,0,0.5);min-width:160px;';
  container.style.position='relative';
  if(!isTouch) container.appendChild(tooltip);

  // ── 手機版固定資訊列 ──
  const infoBar=document.createElement('div');
  infoBar.style.cssText='display:none;padding:8px 12px;background:rgba(22,26,38,0.95);border-top:1px solid rgba(255,255,255,0.08);font-size:11px;color:#e8eaf0;line-height:1.8;';
  if(isTouch) container.appendChild(infoBar);

  // ── 主圖：K線 + EMA20/50 + 買賣點 ──
  const H=(typeof height==='object'&&height)?height:{main:height||240,ema:60,kd:70,rsi:70,vol:50};
  const mainH=H.main;
  const mainDiv=document.createElement('div');
  mainDiv.style.cssText=`width:100%;height:${mainH}px;`;
  container.appendChild(mainDiv);

  const mainChart=LightweightCharts.createChart(mainDiv,{...CHART_OPTS,height:mainH});

  // 蠟燭圖
  const candleSeries=mainChart.addCandlestickSeries({
    upColor:'#26a69a',downColor:'#ef5350',
    borderUpColor:'#26a69a',borderDownColor:'#ef5350',
    wickUpColor:'#26a69a',wickDownColor:'#ef5350',
    priceLineVisible:false,lastValueVisible:false,
  });
  // 如果有 OHLC 資料就用蠟燭圖，否則退回折線圖
  const hasOHLC = data.opens && data.opens.length === prices.length;
  if(hasOHLC){
    candleSeries.setData(dates.map((d,i)=>({
      time:toTime(d),
      open:data.opens[i],high:data.highs[i],low:data.lows[i],close:prices[i]
    })));
  } else {
    // 退回折線圖
    const lineSeries2=mainChart.addLineSeries({color:'#378ADD',lineWidth:2,priceLineVisible:false,lastValueVisible:false});
    lineSeries2.setData(dates.map((d,i)=>({time:toTime(d),value:prices[i]})));
  }
  const mainSeries = candleSeries; // 主要 series 參考

  const ema20Series=mainChart.addLineSeries({color:'#26a69a',lineWidth:1.2,priceLineVisible:false,lastValueVisible:false});
  ema20Series.setData(dates.map((d,i)=>data.ema20[i]!=null?{time:toTime(d),value:data.ema20[i]}:null).filter(Boolean));

  const ema50Series=mainChart.addLineSeries({color:'#ef5350',lineWidth:1.2,lineStyle:1,priceLineVisible:false,lastValueVisible:false});
  ema50Series.setData(dates.map((d,i)=>data.ema50[i]!=null?{time:toTime(d),value:data.ema50[i]}:null).filter(Boolean));

  // 買進賣出標記
  const markers=[];
  dates.forEach((d,i)=>{
    if(data.buyPoints[i]!==null) markers.push({time:toTime(d),position:'belowBar',color:'#26a69a',shape:'arrowUp',text:'買',size:1});
    if(data.sellPoints[i]!==null) markers.push({time:toTime(d),position:'aboveBar',color:'#ef5350',shape:'arrowDown',text:'賣',size:1});
  });
  mainSeries.setMarkers(markers);
  charts.push(mainChart);

  // ── Crosshair 事件：顯示 tooltip ──
  // ── 共用：組合資訊 HTML ──
  function buildInfoHtml(idx, compact){
    const price=prices[idx];
    const e20=data.ema20[idx];
    const e50=data.ema50[idx];
    const hasBuy=data.buyPoints[idx]!==null;
    const hasSell=data.sellPoints[idx]!==null;
    const k=K[idx],d_=D[idx],rsi=rsiVals[idx],df=diff[idx];
    const isUp=idx===0||prices[idx]>=prices[idx-1];
    const pc=isUp?'#26a69a':'#ef5350';
    function row(l,v,c){return `<span style="color:#8b90a0;">${l}</span> <span style="color:${c};font-weight:500;">${v}</span>`;}
    if(compact){
      // 手機版：橫向緊湊排列
      let parts=[];
      parts.push(`<span style="color:#8b90a0;font-size:10px;">${dates[idx]}</span>`);
      if(hasOHLC) parts.push(`${row('開',data.opens[idx],pc)} ${row('高',data.highs[idx],'#26a69a')} ${row('低',data.lows[idx],'#ef5350')} ${row('收',price,pc)}`);
      else parts.push(row('收',price,'#378ADD'));
      if(e20!=null) parts.push(row('E20',e20,'#26a69a'));
      if(e50!=null) parts.push(row('E50',e50,'#ef5350'));
      if(indicators.kd&&k!=null) parts.push(`<span style="color:#8b90a0;">KD</span> <span style="color:#f5a623;">${k}</span>/<span style="color:#378ADD;">${d_}</span>`);
      if(indicators.rsi&&rsi!=null) parts.push(row('RSI',rsi,'#9c27b0'));
      if(hasBuy) parts.push('<span style="color:#26a69a;font-weight:700;">▲買進</span>');
      if(hasSell) parts.push('<span style="color:#ef5350;font-weight:700;">▼賣出</span>');
      return parts.join(' &nbsp;·&nbsp; ');
    } else {
      // 電腦版：垂直排列
      function rowV(l,v,c){return `<div style="display:flex;justify-content:space-between;gap:14px;line-height:1.9;"><span style="color:#8b90a0;">${l}</span><span style="color:${c};font-weight:500;">${v}</span></div>`;}
      let html=`<div style="color:#8b90a0;margin-bottom:5px;font-size:10px;">${dates[idx]}</div>`;
      if(hasOHLC){html+=rowV('開盤',data.opens[idx],pc)+rowV('最高',data.highs[idx],'#26a69a')+rowV('最低',data.lows[idx],'#ef5350')+rowV('收盤',price,pc);}
      else html+=rowV('收盤',price,'#378ADD');
      if(e20!=null) html+=rowV('EMA20',e20,'#26a69a');
      if(e50!=null) html+=rowV('EMA50',e50,'#ef5350');
      if(indicators.ema) html+=rowV('EMA差距',(df>0?'+':'')+df+'%',df>=0?'#26a69a':'#ef5350');
      if(indicators.kd&&k!=null) html+=`<div style="display:flex;justify-content:space-between;gap:14px;line-height:1.9;"><span style="color:#8b90a0;">K/D</span><span style="font-weight:500;"><span style="color:#f5a623;">${k}</span>/<span style="color:#378ADD;">${d_}</span></span></div>`;
      if(indicators.rsi&&rsi!=null) html+=rowV('RSI',rsi,'#9c27b0');
      if(hasBuy) html+=`<div style="color:#26a69a;font-weight:700;margin-top:3px;">▲ 買進訊號</div>`;
      if(hasSell) html+=`<div style="color:#ef5350;font-weight:700;margin-top:3px;">▼ 賣出訊號</div>`;
      return html;
    }
  }

  mainChart.subscribeCrosshairMove(param=>{
    if(!param||!param.point||param.point.x<0){
      tooltip.style.display='none';
      return;
    }
    const seriesData=param.seriesData.get(mainSeries);
    if(!seriesData){tooltip.style.display='none';return;}
    const hoverTime=seriesData.time;
    const idx=dates.findIndex(d=>toTime(d)===hoverTime||d===hoverTime);
    if(idx<0||idx>=dates.length){tooltip.style.display='none';return;}

    if(isTouch){
      // 手機：顯示固定資訊列
      infoBar.innerHTML=buildInfoHtml(idx,true);
      infoBar.style.display='block';
    } else {
      // 電腦：顯示浮動 tooltip
      tooltip.innerHTML=buildInfoHtml(idx,false);
      const mainRect=mainDiv.getBoundingClientRect();
      let left=param.point.x+15;
      if(left+180>mainRect.width) left=param.point.x-195;
      tooltip.style.left=left+'px';
      tooltip.style.top='10px';
      tooltip.style.display='block';
    }
  });
  mainDiv.addEventListener('mouseleave',()=>{
    if(!isTouch) tooltip.style.display='none';
  });

  // ── 子圖 tooltip 共用函數 ──
  function makeSubTooltip(paneDiv){
    const tt=document.createElement('div');
    tt.style.cssText='position:absolute;z-index:99;display:none;background:rgba(20,24,36,0.95);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:5px 9px;font-size:10px;color:#e8eaf0;pointer-events:none;white-space:nowrap;';
    paneDiv.style.position='relative';
    paneDiv.appendChild(tt);
    return tt;
  }
  function syncCrosshair(chart,series,dates,formatter){
    const paneDiv=chart.chartElement().parentElement;
    const tt=makeSubTooltip(paneDiv);
    chart.subscribeCrosshairMove(param=>{
      if(!param||!param.point||param.point.x<0){tt.style.display='none';return;}
      const sd=param.seriesData.get(series);
      if(!sd){tt.style.display='none';return;}
      const idx=dates.findIndex(d=>toTime(d)===sd.time||d===sd.time);
      if(idx<0){tt.style.display='none';return;}
      tt.innerHTML=formatter(idx,sd);
      let left=param.point.x+10;
      if(left+160>paneDiv.offsetWidth) left=param.point.x-170;
      tt.style.left=Math.max(0,left)+'px';
      tt.style.top='2px';
      tt.style.display='block';
    });
    paneDiv.addEventListener('mouseleave',()=>{tt.style.display='none';});
  }

  // ── EMA差距 ──
  if(indicators.ema){
    const emaDiv=document.createElement('div');
    emaDiv.style.cssText=`width:100%;height:${H.ema}px;position:relative;`;
    const label=document.createElement('div');
    label.className='chart-pane-label';label.textContent='EMA差距';
    container.appendChild(label);container.appendChild(emaDiv);
    const emaChart=LightweightCharts.createChart(emaDiv,{...CHART_OPTS,height:H.ema,
      timeScale:{visible:false},rightPriceScale:{scaleMargins:{top:0.1,bottom:0.1}}});
    const emaHist=emaChart.addHistogramSeries({priceLineVisible:false,lastValueVisible:false});
    emaHist.setData(dates.map((d,i)=>({time:toTime(d),value:diff[i],color:diff[i]>=0?'rgba(38,166,154,0.6)':'rgba(239,83,80,0.6)'})));
    charts.push(emaChart);
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)emaChart.timeScale().setVisibleLogicalRange(r);});
    emaChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)mainChart.timeScale().setVisibleLogicalRange(r);});
    syncCrosshair(emaChart,emaHist,dates,(idx,sd)=>{
      const v=diff[idx];
      return `<span style="color:#8b90a0;">${dates[idx]}</span> &nbsp; EMA差距 <span style="color:${v>=0?"#26a69a":"#ef5350"};font-weight:600;">${v>0?"+":""}${v}%</span>`;
    });
  }

  // ── KD 線 ──
  if(indicators.kd){
    const kdDiv=document.createElement('div');
    kdDiv.style.cssText=`width:100%;height:${H.kd}px;position:relative;`;
    const label=document.createElement('div');
    label.className='chart-pane-label';label.textContent='KD';
    container.appendChild(label);container.appendChild(kdDiv);
    const kdChart=LightweightCharts.createChart(kdDiv,{...CHART_OPTS,height:H.kd,
      timeScale:{visible:false},rightPriceScale:{scaleMargins:{top:0.1,bottom:0.1}}});
    const kLine=kdChart.addLineSeries({color:'#f5a623',lineWidth:1.2,priceLineVisible:false,lastValueVisible:true,title:'K'});
    const dLine=kdChart.addLineSeries({color:'#378ADD',lineWidth:1.2,priceLineVisible:false,lastValueVisible:true,title:'D'});
    kLine.setData(dates.map((d,i)=>({time:toTime(d),value:K[i]})));
    dLine.setData(dates.map((d,i)=>({time:toTime(d),value:D[i]})));
    charts.push(kdChart);
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)kdChart.timeScale().setVisibleLogicalRange(r);});
    kdChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)mainChart.timeScale().setVisibleLogicalRange(r);});
    syncCrosshair(kdChart,kLine,dates,(idx)=>{
      return `<span style="color:#8b90a0;">${dates[idx]}</span> &nbsp; <span style="color:#f5a623;">K ${K[idx]}</span> &nbsp; <span style="color:#378ADD;">D ${D[idx]}</span>`;
    });
  }

  // ── RSI ──
  if(indicators.rsi){
    const rsiDiv=document.createElement('div');
    rsiDiv.style.cssText=`width:100%;height:${H.rsi}px;position:relative;`;
    const label=document.createElement('div');
    label.className='chart-pane-label';label.textContent='RSI(14)';
    container.appendChild(label);container.appendChild(rsiDiv);
    const rsiChart=LightweightCharts.createChart(rsiDiv,{...CHART_OPTS,height:H.rsi,
      timeScale:{visible:false},rightPriceScale:{scaleMargins:{top:0.1,bottom:0.1}}});
    const rsiLine=rsiChart.addLineSeries({color:'#9c27b0',lineWidth:1.2,priceLineVisible:false,lastValueVisible:true,title:'RSI'});
    rsiLine.setData(dates.map((d,i)=>rsiVals[i]!=null?{time:toTime(d),value:rsiVals[i]}:null).filter(Boolean));
    charts.push(rsiChart);
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)rsiChart.timeScale().setVisibleLogicalRange(r);});
    rsiChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)mainChart.timeScale().setVisibleLogicalRange(r);});
    syncCrosshair(rsiChart,rsiLine,dates,(idx)=>{
      const v=rsiVals[idx];
      if(v==null) return '';
      const color=v>=70?'#ef5350':v<=30?'#26a69a':'#9c27b0';
      return `<span style="color:#8b90a0;">${dates[idx]}</span> &nbsp; RSI <span style="color:${color};font-weight:600;">${v}</span>${v>=70?' <span style="color:#ef5350;">超買</span>':v<=30?' <span style="color:#26a69a;">超賣</span>':''}`;
    });
  }

  // ── 成交量 ──
  if(indicators.vol&&data.volumes&&data.volumes.some(v=>v>0)){
    const volDiv=document.createElement('div');
    volDiv.style.cssText=`width:100%;height:${H.vol}px;position:relative;`;
    const label=document.createElement('div');
    label.className='chart-pane-label';label.textContent='成交量';
    container.appendChild(label);container.appendChild(volDiv);
    const volChart=LightweightCharts.createChart(volDiv,{...CHART_OPTS,height:H.vol,
      timeScale:{visible:true},rightPriceScale:{scaleMargins:{top:0.1,bottom:0}}});
    const volHist=volChart.addHistogramSeries({priceLineVisible:false,lastValueVisible:false});
    volHist.setData(dates.map((d,i)=>({
      time:toTime(d),value:data.volumes[i]||0,
      color:i===0?'rgba(55,138,221,0.5)':prices[i]>=prices[i-1]?'rgba(38,166,154,0.5)':'rgba(239,83,80,0.5)'
    })));
    charts.push(volChart);
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)volChart.timeScale().setVisibleLogicalRange(r);});
    volChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)mainChart.timeScale().setVisibleLogicalRange(r);});
    syncCrosshair(volChart,volHist,dates,(idx)=>{
      const v=data.volumes[idx]||0;
      const fmt=v>=1e8?(v/1e8).toFixed(1)+'億':v>=1e4?(v/1e4).toFixed(0)+'萬':v.toFixed(0);
      return `<span style="color:#8b90a0;">${dates[idx]}</span> &nbsp; 成交量 <span style="font-weight:600;">${fmt}</span>`;
    });
  }

  // 同步所有圖表的時間軸
  mainChart.timeScale().fitContent();
  return charts;
}

function drawCharts(id,data,indicators){
  destroyCard(id);
  const card=document.getElementById(`card-${id}`);
  const container=card.querySelector('.chart-container');
  container.innerHTML='';
  chartInsts[id]=buildChartsInContainer(container,data,indicators,chartHeights('card'));
}

// ── Modal ──────────────────────────────────────────────
function openModal(id){
  const card=document.getElementById(`card-${id}`);
  if(!card||card.dataset.loaded!=='1') return;
  const stock=stocks.find(s=>s.id===id);
  modalStockId=id;
  modalData=JSON.parse(card.dataset.chartdata||'null');
  modalIndicators={...stock.indicators};
  document.getElementById('modalTitle').textContent=`${stock?.name||stock?.symbol} — 放大圖`;
  document.getElementById('modalPeriod').value=stock?.period||'2y';
  document.getElementById('modalTf').value=stock?.tf||'1d';

  // 建立指標開關
  const togglesEl=document.getElementById('modalIndToggles');
  togglesEl.innerHTML=[
    {k:'ema',l:'EMA差距'},{k:'kd',l:'KD 線'},{k:'rsi',l:'RSI'},{k:'vol',l:'成交量'}
  ].map(o=>`<button id="modal-itoggle-${o.k}" class="itoggle ${modalIndicators[o.k]?'on':''}" onclick="toggleModalIndicator('${o.k}')">${o.l}</button>`).join('');

  // 更新訊號
  updateModalSignal(modalData);
  document.getElementById('modalBg').classList.add('open');
  drawModalCharts(modalData,modalIndicators);
}

function updateModalSignal(data){
  if(!data) return;
  const lastDiff=data.diff[data.diff.length-1];
  const hasBuy=data.buyPoints[data.buyPoints.length-1]!==null;
  const hasSell=data.sellPoints[data.sellPoints.length-1]!==null;
  let html='';
  if(hasBuy) html='<span style="color:#26a69a;">▲ 現在有買進訊號！</span>';
  else if(hasSell) html='<span style="color:#ef5350;">▼ 現在有賣出訊號！</span>';
  else if(lastDiff>0.1) html='<span style="color:#26a69a;">▲ 多頭趨勢 · 等待訊號</span>';
  else if(lastDiff<-0.1) html='<span style="color:#ef5350;">▼ 空頭趨勢 · 觀望</span>';
  else html='<span style="color:#8b90a0;">— 中立 · 等待訊號</span>';
  document.getElementById('modalSignal').innerHTML=html;
}

async function reloadModal(){
  if(!modalStockId) return;
  const stock=stocks.find(s=>s.id===modalStockId);
  if(!stock) return;
  const p=document.getElementById('modalPeriod').value;
  const tf=document.getElementById('modalTf').value;
  try{
    const r=await fetch(`/api/analyze?symbol=${stock.symbol}&strategy=${stock.strat}&period=${p}&timeframe=${tf}`);
    const data=await r.json();
    if(!data.error){modalData=data;updateModalSignal(data);drawModalCharts(data,modalIndicators);}
  }catch(e){}
}

function drawModalCharts(data,indicators){
  if(!data) return;
  if(modalChartInst){
    modalChartInst.forEach(c=>{try{c.remove();}catch(e){}});
    modalChartInst=null;
  }
  const container=document.getElementById('modalChartContainer');
  container.innerHTML='';
  modalChartInst=buildChartsInContainer(container,data,indicators,chartHeights('modal'));
}

function closeModal(e){
  if(e&&e.target!==document.getElementById('modalBg')) return;
  document.getElementById('modalBg').classList.remove('open');
}
document.addEventListener('keydown',e=>{if(e.key==='Escape') document.getElementById('modalBg').classList.remove('open');});

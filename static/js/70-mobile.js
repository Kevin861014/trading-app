// ── 手機/觸控輔助(B2)────────────────────────────────────────────────
// 只處理「呈現與互動」:說明提示(觸控沒有 hover)、彈窗時鎖住背景捲動、旋轉/縮放時依新尺寸重畫圖。
// 不呼叫任何 API,也不改任何計算或資料。
(function(){
  const sheet = document.getElementById('tipSheet');
  if(!sheet) return;
  const txt = sheet.querySelector('.tip-text');
  let hideTimer = null, pressTimer = null, suppressClick = false;

  function showTip(t){
    txt.textContent = t; sheet.hidden = false;
    clearTimeout(hideTimer); hideTimer = setTimeout(hideTip, 14000);
  }
  function hideTip(){ sheet.hidden = true; clearTimeout(hideTimer); }
  const coarse = () => isTouchDevice() || isMobileView();

  // 輕點「ⓘ 說明」所在的區塊(KPI、訊號列、市場性格…)顯示說明;點別處或 ✕ 關閉。
  // 按鈕類元素(如指標開關)有自己的功能,改用「長按」顯示說明。
  document.addEventListener('click', e => {
    if(suppressClick){ suppressClick = false; e.preventDefault(); e.stopPropagation(); return; }
    if(e.target.closest('#tipSheet')){ if(e.target.closest('.tip-x')) hideTip(); return; }
    if(!coarse()) return;
    const el = e.target.closest('[data-tip]');
    if(el && !e.target.closest('button,a,input,select,label,textarea')){ showTip(el.getAttribute('data-tip')); return; }
    hideTip();
  }, true);

  document.addEventListener('touchstart', e => {
    const b = e.target.closest && e.target.closest('button[data-tip]');
    if(!b) return;
    clearTimeout(pressTimer);
    pressTimer = setTimeout(() => { suppressClick = true; showTip(b.getAttribute('data-tip')); }, 550);
  }, {passive:true});
  ['touchend','touchmove','touchcancel'].forEach(ev => document.addEventListener(ev, () => clearTimeout(pressTimer), {passive:true}));
  document.addEventListener('contextmenu', e => { if(e.target.closest && e.target.closest('button[data-tip]') && coarse()) e.preventDefault(); });
  window.addEventListener('scroll', () => { if(!sheet.hidden && coarse()) hideTip(); }, {passive:true});

  // 彈窗/抽屜開啟時,鎖住背景捲動(iOS Safari 才不會一直滑到後面的頁面)
  const watched = ['analysisBg', 'modalBg', 'navDrawer'].map(id => document.getElementById(id)).filter(Boolean);
  const sync = () => document.body.classList.toggle('modal-open', watched.some(el => el.classList.contains('open')));
  const mo = new MutationObserver(sync);
  watched.forEach(el => mo.observe(el, {attributes:true, attributeFilter:['class']}));

  // 旋轉或跨過手機斷點:只用已載入的資料重畫(不重新打 API)
  const mq = window.matchMedia('(max-width:720px)');
  let rsz = null;
  function redrawAll(){
    if(typeof stocks === 'undefined') return;
    stocks.forEach(s => {
      if(!s.expanded) return;
      const card = document.getElementById(`card-${s.id}`);
      if(!card || card.dataset.loaded !== '1' || card.style.display === 'none') return;
      const data = JSON.parse(card.dataset.chartdata || 'null');
      if(data && card.querySelector('.chart-container').clientWidth) drawCharts(s.id, data, s.indicators);
    });
    if(document.getElementById('modalBg').classList.contains('open') && modalData) drawModalCharts(modalData, modalIndicators);
    if(currentView === 'symbol' && typeof _symLast !== 'undefined' && _symLast){ symClear(); renderSymbolBody($id('symBody'), _symLast.data, _symLast.ctx); }
  }
  const onChange = () => { clearTimeout(rsz); rsz = setTimeout(redrawAll, 200); };
  (mq.addEventListener ? mq.addEventListener('change', onChange) : mq.addListener(onChange));
  window.addEventListener('orientationchange', onChange);
})();

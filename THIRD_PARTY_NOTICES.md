# Third-party notices

## TradingView Lightweight Charts™ 4.1.3
- 檔案:`static/vendor/lightweight-charts/lightweight-charts.standalone.production.js`(自行託管,與先前 CDN 版本逐位元組相同,sha256 `0c146b9b…e519`)
- 授權:Apache License 2.0(見同資料夾 `LICENSE`)
- 歸屬聲明(見同資料夾 `NOTICE`):TradingView Lightweight Charts™ Copyright (c) 2023 TradingView, Inc. https://www.tradingview.com/
- 網站頁尾已顯示上述歸屬與連結。

## JEV Trading Command Center(視覺語彙,原型)
- 來源:https://github.com/mars-tw/jev-trading-command-center(檔案 `web/three-viz.js` 的電漿球體 `makePlasma` 與粒子星環 `makeRing`)
- 授權:MIT License — Copyright (c) 2026 mars-tw and contributors
- 本站使用方式:`static/js/lab-core3d.js` 改寫其電漿球體 shader、弧光、藍紫粒子星環(含沿管面環流)、16 條螺旋線、Bloom 參數,以及 `web/core-effects.js` 中 createCinematicCore 的軌道環、弧線、光帶、光塵,用於「策略實驗室」的研究核心畫面。**沒有**使用原專案的 AI 角色/寵物、決策圖、模型投票、風險決策、持倉或下單相關程式與素材。
- 修改:移除對 `window.LIVE`、`decision-graph.js`、`core-effects.js`、`LineWorkers`、`OrbitControls` 的依賴;狀態與光點改由本站真實研究事件驅動。

```
MIT License

Copyright (c) 2026 mars-tw and contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Three.js 0.186.1
- 檔案:`static/vendor/three/`(`build/three.module.js`、`build/three.core.js`、`examples/jsm/postprocessing/{EffectComposer,RenderPass,UnrealBloomPass,ShaderPass,MaskPass,Pass}.js`、`examples/jsm/shaders/{CopyShader,LuminosityHighPassShader}.js`),自行託管,與官方發佈檔逐位元組相同(雜湊見 `static/vendor/three/PROVENANCE.json`)。
- 授權:MIT License — Copyright © 2010-2026 three.js authors(全文見 `static/vendor/three/LICENSE`)。

# 順勢策略分析工具

真實行情 K 線圖 + 策略回測分析，支援台股與加密貨幣。

## 功能
- 台股：台積電、鴻海、長榮、聯發科、0050 等
- 加密貨幣：PAXG、SOL、ETH、BNB、XRP、BTC
- 策略：DMI 方向動能、EMA 快慢交叉、波動突破、六條線
- 時間範圍：7天 / 1個月 / 1年 / 2年 / 3年 / 5年
- 回測數據：總報酬、年化報酬、PF、最大回撤、勝率、交易筆數
- 進出場紀錄

## 部署到 Render（免費）

### 步驟一：上傳到 GitHub
1. 到 https://github.com 註冊帳號
2. 點右上角「+」→「New repository」
3. 取名「trading-app」，按「Create repository」
4. 把這個資料夾的所有檔案上傳（拖曳到網頁）

### 步驟二：部署到 Render
1. 到 https://render.com 用 GitHub 帳號登入
2. 點「New +」→「Web Service」
3. 選你剛上傳的「trading-app」repository
4. 設定：
   - Name：trading-app（隨便取）
   - Environment：Python 3
   - Build Command：pip install -r requirements.txt
   - Start Command：gunicorn app:app --bind 0.0.0.0:$PORT
5. 按「Create Web Service」
6. 等 2~3 分鐘部署完成
7. 上方會給你一個網址，例如 https://trading-app-xxxx.onrender.com

### 步驟三：手機加到桌面（iPhone）
1. 用 Safari 打開你的網址
2. 點下方「分享」按鈕（方塊+箭頭圖示）
3. 選「加入主畫面」
4. 完成！桌面會出現圖示，打開就像 APP

## 本機測試
```
pip install -r requirements.txt
python app.py
```
然後打開 http://localhost:5000

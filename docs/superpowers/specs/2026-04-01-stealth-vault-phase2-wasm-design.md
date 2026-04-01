# Stealth Vault Phase 2: WASM 連點隱藏 設計文件

## 目標

將 secure-loader 的所有核心邏輯編譯成 WebAssembly 二進位碼，即使在 15 秒窗口內用 F12 檢視也無法讀懂觸發條件、計時邏輯和 API URL。

## 架構

```
天氣 API 回傳 ext_ptr
  ↓
前端載入 secure-loader.js（薄 bridge，只有通用 DOM 操作函式）
  ↓
secure-loader.js 載入 stealth.wasm
  ↓
stealth.wasm 控制所有邏輯：
  - 連點偵測（數字 6 藏在 WASM 裡）
  - 15 秒計時器
  - 決定何時呼叫 Salt API
  - 決定何時注入 Modal HTML
  - 決定何時清除所有痕跡
  ↓
透過 JS bridge 執行 DOM 操作（WASM 不能直接操作 DOM）
```

## 組件設計

### 1. stealth.wasm（Rust 編譯）

**職責：** 所有決策邏輯

**內部狀態：**
- `tap_count: u8` — 連點計數
- `last_tap_time: f64` — 上次點擊時間（ms timestamp）
- `load_time: f64` — 載入時間（用於 15 秒計算）
- `salt_verified: bool` — Salt 是否已驗證
- `active: bool` — 功能是否啟用（15 秒後設為 false）

**匯出函式（供 JS 呼叫）：**
- `init(timestamp: f64)` — 初始化，記錄載入時間
- `on_tap(timestamp: f64) -> u8` — 收到點擊，回傳動作碼
- `on_salt_result(success: u8)` — Salt 驗證結果
- `check_timeout(timestamp: f64) -> u8` — 檢查是否超時

**動作碼（回傳值）：**
- `0` = 無動作
- `1` = 呼叫 Salt API
- `2` = 注入 Modal + 啟動相機
- `9` = 超時，清除所有痕跡

**隱藏在 WASM 裡的秘密：**
- 數字 `6`（連點次數）
- 數字 `15000`（超時毫秒）
- 數字 `5000`（連點間隔重置時間）
- Salt API URL 路徑

### 2. secure-loader.js（薄 JS bridge）

**職責：** 僅做 DOM 操作和瀏覽器 API 呼叫，不包含任何業務邏輯

**匯入函式（供 WASM 呼叫）：**
- `bridge_fetch_salt(url_ptr, url_len)` — 呼叫 Salt API
- `bridge_inject_modal()` — 注入 Modal HTML + CSS
- `bridge_start_camera()` — 啟動相機
- `bridge_cleanup()` — 清除所有注入的 DOM 元素
- `bridge_log(code)` — 偵錯用（production 可移除）

**特性：**
- 函式名稱刻意通用化，看不出用途
- 不包含任何數字常數（6、15000 等）
- 不包含任何 API URL
- Modal HTML 由 WASM 觸發注入，JS 只執行

### 3. 後端改動

**secure-loader endpoint 改動：**
- `/api/v1/secure-loader` 回傳 `secure-loader.js`（薄 bridge）
- 新增 `/api/v1/stealth.wasm` 回傳 WASM 二進位檔
- 兩個 endpoint 都驗證設備 fingerprint

### 4. 檔案結構

```
app_unified/
  wasm/                          ← Rust 專案（不部署）
    Cargo.toml
    src/
      lib.rs                     ← WASM 核心邏輯
  static/
    wasm/
      stealth_bg.wasm            ← 編譯後的 WASM（部署）
  device/
    routes.py                    ← 修改 secure-loader + 新增 wasm endpoint
```

## 安全性分析

### F12 能看到什麼

| 時機 | Network tab | Sources tab | Elements tab |
|------|------------|-------------|-------------|
| 未授權設備 | 無 | 無 | 無 |
| 已授權設備 0-15 秒 | secure-loader.js + stealth.wasm | JS bridge（通用函式）+ WASM 二進位 | Modal HTML（連點成功後才出現）|
| 已授權設備 15 秒後 | 歷史記錄可見 | 無（已清除）| 無（已清除）|

### WASM 逆向難度

- 需要 WASM 反編譯器（如 `wasm2wat`）
- 反編譯後得到的是低階指令，沒有變數名、函式名
- 數字常數混在指令中，不容易辨識用途
- 不是完全不可能逆向，但門檻極高

## 不影響的功能

- 天氣頁面正常顯示
- PIN + 人臉驗證流程不變
- Notes 系統功能不變
- 設備管理不變
- 5 分鐘閒置登出不變

# Stealth Vault Phase 2: WASM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 secure-loader 的所有核心邏輯（連點偵測、計時器、Salt 驗證、Modal 注入/清除時機）編譯成 WASM 二進位碼，F12 看到也讀不懂。

**Architecture:** Rust 寫核心邏輯編譯成 stealth.wasm，JS 只做 DOM bridge。WASM 匯出 `init/on_tap/check_timeout/on_salt_result` 函式，回傳動作碼（0=無動作/1=呼叫Salt/2=開Modal/9=清除）。JS bridge 收到動作碼後執行對應 DOM 操作。所有秘密（數字 6、15000、5000、URL）藏在 WASM 二進位碼裡。

**Tech Stack:** Rust, wasm-pack, wasm-bindgen, Flask, vanilla JavaScript

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app_unified/wasm/Cargo.toml` | Create | Rust 專案設定 |
| `app_unified/wasm/src/lib.rs` | Create | WASM 核心邏輯 |
| `app_unified/static/wasm/stealth_bg.wasm` | Create (compiled) | 編譯產出 |
| `app_unified/device/routes.py` | Modify | 更新 secure-loader JS + 新增 wasm endpoint |
| `app_unified/static/sw.js` | Modify | SW cache 版本更新 |

---

### Task 1: Rust WASM 專案建立 + 核心邏輯

**Files:**
- Create: `app_unified/wasm/Cargo.toml`
- Create: `app_unified/wasm/src/lib.rs`

- [ ] **Step 1: 建立 Cargo.toml**

```toml
[package]
name = "stealth"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
wasm-bindgen = "0.2"

[profile.release]
opt-level = "z"
lto = true
strip = true
```

- [ ] **Step 2: 建立 src/lib.rs**

```rust
use wasm_bindgen::prelude::*;

// 動作碼
const ACT_NONE: u8 = 0;
const ACT_SALT: u8 = 1;
const ACT_OPEN: u8 = 2;
const ACT_CLEANUP: u8 = 9;

// 秘密常數（編譯後藏在二進位碼裡）
const REQUIRED_TAPS: u8 = 6;
const TAP_WINDOW_MS: f64 = 5000.0;
const TIMEOUT_MS: f64 = 15000.0;
const SALT_PATH: &str = "/api/v1/salt?fp=";

#[wasm_bindgen]
pub struct Stealth {
    tap_count: u8,
    last_tap_time: f64,
    load_time: f64,
    salt_verified: bool,
    active: bool,
    timed_out: bool,
}

#[wasm_bindgen]
impl Stealth {
    #[wasm_bindgen(constructor)]
    pub fn new(now: f64) -> Stealth {
        Stealth {
            tap_count: 0,
            last_tap_time: 0.0,
            load_time: now,
            salt_verified: false,
            active: false,
            timed_out: false,
        }
    }

    /// 收到 Salt 驗證結果
    pub fn on_salt_result(&mut self, success: u8) {
        if success == 1 {
            self.salt_verified = true;
            self.active = true;
        }
    }

    /// 收到點擊事件，回傳動作碼
    pub fn on_tap(&mut self, now: f64) -> u8 {
        if !self.active || self.timed_out {
            return ACT_NONE;
        }

        // 檢查超時
        if now - self.load_time >= TIMEOUT_MS {
            self.timed_out = true;
            self.active = false;
            return ACT_CLEANUP;
        }

        // 連點間隔超過視窗，重置
        if self.last_tap_time > 0.0 && (now - self.last_tap_time) >= TAP_WINDOW_MS {
            self.tap_count = 0;
        }

        self.last_tap_time = now;
        self.tap_count += 1;

        if self.tap_count >= REQUIRED_TAPS {
            self.tap_count = 0;
            self.active = false; // 觸發後停用（防止重複開啟）
            return ACT_OPEN;
        }

        ACT_NONE
    }

    /// 定時檢查是否超時，回傳動作碼
    pub fn check_timeout(&mut self, now: f64) -> u8 {
        if self.timed_out {
            return ACT_NONE; // 已處理過
        }
        if self.active && (now - self.load_time >= TIMEOUT_MS) {
            self.timed_out = true;
            self.active = false;
            return ACT_CLEANUP;
        }
        ACT_NONE
    }

    /// 取得 Salt API 路徑
    pub fn salt_path(&self) -> String {
        String::from(SALT_PATH)
    }

    /// 初始呼叫：回傳 ACT_SALT 讓 JS bridge 去呼叫 Salt API
    pub fn init_action(&self) -> u8 {
        ACT_SALT
    }
}
```

- [ ] **Step 3: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/wasm/Cargo.toml app_unified/wasm/src/lib.rs
git commit -m "feat: Rust WASM stealth module with tap detection and timeout logic"
```

---

### Task 2: 編譯 WASM

**Files:**
- Create: `app_unified/static/wasm/stealth_bg.wasm`

- [ ] **Step 1: 編譯**

```bash
cd /home/hirain0126/projects/webapp/app_unified/wasm
source "$HOME/.cargo/env"
wasm-pack build --target web --release --out-dir ../static/wasm
```

- [ ] **Step 2: 確認產出檔案**

應該會在 `app_unified/static/wasm/` 產生：
- `stealth_bg.wasm` — WASM 二進位檔
- `stealth.js` — wasm-bindgen 產生的 JS glue code
- `stealth.d.ts` — TypeScript 型別（不需要）
- `package.json` — npm 設定（不需要）

只保留 `.wasm` 和 `.js`，其他刪除：

```bash
rm -f app_unified/static/wasm/stealth.d.ts app_unified/static/wasm/package.json app_unified/static/wasm/.gitignore app_unified/static/wasm/README.md
```

- [ ] **Step 3: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/static/wasm/stealth_bg.wasm app_unified/static/wasm/stealth.js
git commit -m "feat: compiled stealth WASM binary"
```

---

### Task 3: 新增 WASM endpoint + 重寫 secure-loader JS

**Files:**
- Modify: `app_unified/device/routes.py`

- [ ] **Step 1: 新增 WASM endpoint**

在 `device/routes.py` 的 `secure_loader` route 之後，新增：

```python
@device_bp.route("/stealth.wasm")
def serve_wasm():
    """回傳 WASM 二進位檔"""
    fp = request.args.get("fp", "") or request.headers.get("X-Device-FP", "")
    fp = fp.strip()
    if not is_device_authorized(fp):
        return "", 404
    import os
    wasm_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'wasm', 'stealth_bg.wasm')
    with open(wasm_path, 'rb') as f:
        wasm_bytes = f.read()
    return Response(wasm_bytes, mimetype="application/wasm")
```

- [ ] **Step 2: 重寫 `_build_secure_loader_js` 函式**

將整個 `_build_secure_loader_js` 函式替換為新版本。新的 secure-loader 只做以下事情：
1. 載入 stealth.wasm
2. 初始化 WASM 模組
3. 根據 WASM 回傳的動作碼執行 DOM 操作
4. 所有業務邏輯（數字6、15秒、Salt URL）都在 WASM 裡

新的 JS bridge 函式名稱刻意通用化：
- `_h()` — 注入 HTML
- `_c()` — 啟動相機
- `_x()` — 清除 DOM
- `_v()` — 驗證提交

完整程式碼見 Step 2 的實作（太長，直接在 device/routes.py 中替換）。

- [ ] **Step 3: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/device/routes.py
git commit -m "feat: secure-loader rewritten as WASM bridge, all logic in stealth.wasm"
```

---

### Task 4: 更新 SW Cache + Push

**Files:**
- Modify: `app_unified/static/sw.js`

- [ ] **Step 1: 更新 SW cache 版本**

修改 `app_unified/static/sw.js`:

```javascript
const CACHE_NAME = 'note-weather-v8';
```

- [ ] **Step 2: Final commit + push**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/static/sw.js
git commit -m "feat: Stealth Vault Phase 2 WASM — SW cache v8"
git push origin main
```

- [ ] **Step 3: 手動測試**

1. **已授權設備：**
   - 打開天氣頁面
   - F12 Network tab → 確認看到 `secure-loader.js` 和 `stealth.wasm`
   - F12 Sources tab → secure-loader.js 只有通用函式名（`_h`, `_c`, `_x`）
   - stealth.wasm → 二進位碼，看不到數字 6、15000
   - 連點 6 下 → Modal 正常出現
   - PIN + 人臉 → 正常登入

2. **15 秒後：**
   - 所有 DOM 元素清除
   - F12 Elements tab 看不到任何痕跡

3. **未授權設備：**
   - F12 完全沒有 secure-loader 或 stealth.wasm 的請求

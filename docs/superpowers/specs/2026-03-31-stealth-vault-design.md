# 隱形堡壘（Stealth Vault）安全架構設計

## 目標

將天氣+筆記 app 改造為軍事級隱形架構，讓未授權設備在原始碼層面完全看不到 Notes 功能的存在。

## 設計原則

- 物理認證只用 **PIN + 人臉辨識**，不使用指紋/WebAuthn
- 所有使用者（含 admin）統一走設備綁定流程
- 員工自帶手機，需 admin 核准才能使用
- 瀏覽器清除資料後需重新授權（可接受）

---

## 子專案拆分與實作順序

```
子專案 1（設備綁定 + 動態載入）
  → 子專案 2（認證強化）
    → 子專案 3（遠端熔斷）
      → 子專案 4（網路層隱身）
```

每個子專案獨立 spec → plan → 實作 → 部署測試。

---

## 子專案 1：設備綁定 + 動態載入

### 1.1 資料庫：trusted_devices 表

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | Integer PK | 自增 |
| user_id | FK → users, nullable | 綁定的員工（未核准時為空） |
| fingerprint | Text, unique | 設備數位指紋 hash（SHA-256） |
| device_name | Text | 自動產生，如「iPhone / Safari」 |
| is_approved | Boolean, default=False | admin 是否已核准 |
| is_revoked | Boolean, default=False | 是否已掛失 |
| created_at | DateTime | 首次出現時間 |
| last_seen_at | DateTime | 最後一次存取時間 |

### 1.2 設備數位指紋收集

天氣頁面載入時，前端自動收集以下特徵並用 SHA-256 產生 hash：

- User-Agent（瀏覽器版本 + 作業系統）
- 螢幕解析度（screen.width x screen.height）
- 裝置像素比（devicePixelRatio）
- 時區（Intl.DateTimeFormat().resolvedOptions().timeZone）
- 語言（navigator.language）
- Canvas fingerprint（GPU 渲染特徵）
- CPU 核心數（navigator.hardwareConcurrency）
- 記憶體大小（navigator.deviceMemory）
- 觸控支援（navigator.maxTouchPoints）

fingerprint hash 透過自訂 header `X-Device-FP` 隨每次請求送出。

### 1.3 天氣 API 改造

`GET /weather/api/weather` 後端邏輯：

```
收到請求 → 讀取 X-Device-FP header
  ↓
查詢 trusted_devices 表
  ├─ 設備不存在 → 自動建立記錄（is_approved=False）→ 回傳純天氣 JSON
  ├─ 設備未核准（is_approved=False）→ 回傳純天氣 JSON
  ├─ 設備已掛失（is_revoked=True）→ 回傳純天氣 JSON
  └─ 設備已核准且未掛失 → 回傳天氣 JSON + ext_ptr 欄位
```

回傳範例（已授權設備）：
```json
{
  "name": "台北",
  "main": {"temp": 28, "humidity": 75},
  "weather": [{"main": "Clear", "description": "晴"}],
  "ext_ptr": "/api/v1/secure-loader"
}
```

未授權設備收到的 JSON 完全沒有 `ext_ptr`，與正常天氣 API 無異。

### 1.4 安全載入器

`GET /api/v1/secure-loader`：

- 驗證 `X-Device-FP` header 對應的設備是否已授權
- 已授權 → 回傳 JavaScript 程式碼（Content-Type: application/javascript），包含：
  - 連點 6 下監聽邏輯
  - PIN modal HTML 注入
  - 人臉驗證觸發
  - Auth modal 的完整 CSS + JS
- 未授權 → 回傳 404

效果：未授權設備的網頁原始碼和 DevTools Network 裡完全沒有 Notes 相關的任何痕跡。

### 1.5 前端動態載入

天氣頁面的 JS（寫在 weather/index.html 裡）：

```javascript
// 收到天氣資料後
if (data.ext_ptr) {
  var s = document.createElement('script');
  s.src = data.ext_ptr;
  document.body.appendChild(s);
}
```

這段是唯一留在原始碼裡的「線索」，但 `ext_ptr` 只有已授權設備才收得到，未授權設備執行這段時 `data.ext_ptr` 是 undefined，不會做任何事。

### 1.6 種子 Admin 機制

系統啟動時檢查 `User.query.filter_by(role='admin').count() == 0`：

- **有 admin** → 正常模式
- **沒有 admin（DB 空或新 DB）** → 種子模式

種子模式：
1. 第一台連上的設備（任何設備）→ 天氣 API 回傳特殊 `ext_ptr: "/api/v1/seed-setup"`
2. 前端載入初始化設定頁面：
   - 輸入管理員帳號名稱
   - 設定 PIN 碼
   - 拍攝人臉
3. 提交後 → 建立第一位 admin + 自動核准此設備
4. 種子模式永久關閉（因為已有 admin）

### 1.7 統一註冊流程

所有使用者（含 admin）走同一流程：

```
任何人打開天氣頁面
  ↓
設備指紋自動送到 server
  ↓
server 記錄新設備（is_approved=False）
  ↓
Admin 在後台「設備管理」看到新設備
  ↓
Admin 點擊該設備 → 設定：
  - 帳號名稱
  - PIN 碼
  - 拍攝人臉（用 admin 的鏡頭拍員工）
  - 指定店別
  - 權限（admin / user）
  → 按「核准」
  ↓
該設備下次打開天氣頁面 → 收到 ext_ptr → 可連點進入 Notes
```

### 1.8 Admin Dashboard 設備管理 UI

新增「設備管理」區塊：

**待核准設備列表：**
- 設備名稱（如「iPhone / Safari」）
- 首次出現時間
- 「設定並核准」按鈕 → 展開設定表單（帳號、PIN、人臉、店別、權限）

**已核准設備列表：**
- 設備名稱
- 綁定的員工名稱
- 權限（admin / user）
- 店別
- 最後上線時間
- 「掛失」按鈕
- 「刪除」按鈕

### 1.9 店別 OFF 與設備的關係

店別設為 OFF 時：
- 該店所有員工綁定的設備 → `ext_ptr` 不發放
- 效果：連點功能消失，純天氣 app
- Admin 設備不受店別 OFF 影響

---

## 子專案 2：認證強化

### 2.1 PIN 雜湊升級

- SHA256（無鹽）→ **bcrypt**（自動加鹽、慢雜湊）
- 需要 migration 將現有 hash 標記為舊格式
- 使用者下次登入時自動升級為 bcrypt

### 2.2 人臉驗證失敗鎖定

- 連續 3 次人臉比對失敗 → 該設備鎖定 15 分鐘
- 鎖定期間設備的 `ext_ptr` 不發放
- 在 `trusted_devices` 表加入 `locked_until` 欄位

### 2.3 三重驗證流程

```
設備已授權？（設備指紋）
  ↓ 是
連點 6 下
  ↓
PIN 碼驗證
  ↓ 通過
人臉辨識
  ↓ 通過
進入 Notes
```

三重驗證：設備綁定 + PIN + 人臉，缺一不可。

---

## 子專案 3：遠端熔斷 + 欺騙式錯誤

### 3.1 掛失機制

Admin dashboard 的設備管理 → 「掛失」按鈕：
- 設定 `is_revoked = True`
- 立即生效，該設備下次請求就失效

### 3.2 動態 Salt 機制

動態載入前必須向 server 請求 Salt：
- `GET /api/v1/salt`（帶 fingerprint header）
- 已授權 → 回傳 salt 值
- 已掛失 → 拒絕發放

前端的安全載入器收到 salt 後才能解密並啟用連點功能。

### 3.3 欺騙式錯誤

掛失設備的行為：
- 天氣功能完全正常
- 不回傳 `ext_ptr`（連點功能消失）
- 如果有人嘗試直接存取 `/api/v1/secure-loader` → 回傳 404
- 如果有人嘗試存取 `/api/v1/salt` → 回傳 `{"error": "氣象伺服器連線異常"}`

對方無法分辨是被掛失還是伺服器問題。

---

## 子專案 4：網路層隱身

### 4.1 Cloudflare 代理

- 購買自訂 domain
- 接入 Cloudflare（橘色雲朵 proxy）
- 隱藏 Zeabur 真實 IP
- 強制 TLS 1.3
- WAF 地理位置封鎖（只允許台灣 IP）

### 4.2 WebSocket 加密隧道

- 筆記相關通訊（CRUD、AI 摘要）全程走 WebSocket 長連接
- 連接建立時驗證設備指紋 + session token
- 斷線自動重連

### 4.3 流量填充（Traffic Padding）

- WebSocket 建立後，無論有無操作，每秒固定傳送 1KB 混淆數據
- 有操作時，真實數據混在 1KB 流量中
- Wireshark 只看到一條平滑、持續、無特徵的加密流
- 無法區分「看天氣」vs「讀筆記」vs「閒置」

---

## 角色權限（不變）

| 功能 | Admin | User |
|------|-------|------|
| 看到全店筆記 | ✅ | ✅ |
| 新增/修改/刪除筆記 | ✅ | ✅（自己的） |
| AI 摘要 | ✅ | ❌ |
| 管理員工 | ✅ | ❌ |
| 設備管理（核准/掛失） | ✅ | ❌ |
| 店別權限開關 | ✅ | ❌ |

---

## 現有功能影響

- 天氣功能：不受影響，所有人都能正常看天氣
- Notes 系統：功能不變，只是進入方式改為設備綁定 + 動態載入
- Admin Dashboard：新增設備管理區塊，其餘不變
- 人臉辨識：維持現有 face_recognition 流程，不改動
- AI 摘要：維持現有 Ollama 整合，不改動

---

## 技術限制與已知風險

1. **設備指紋穩定性**：瀏覽器更新或清除資料後指紋可能改變，需 admin 重新授權
2. **流量填充成本**：WebSocket 恆定 1KB/s 會增加頻寬使用，Zeabur 可能有流量限制
3. **Ollama 記憶體**：llama3.2:1b 模型較小，AI 摘要品質有限
4. **face_recognition_models**：目前靠 wsgi.py 的 pkg_resources shim 運作，升級 Python 版本時需注意

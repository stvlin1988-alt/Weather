# Stealth Vault Phase 4: 網路層隱身 設計文件

## 目標

Notes 通訊全程走 WebSocket 加密隧道，搭配恆定流量填充，讓 Wireshark 無法區分天氣瀏覽和筆記操作。

## 前置條件（已完成）

- 自訂 domain 已購買
- Cloudflare proxy 已開啟（橘色雲朵，隱藏真實 IP）
- SSL/TLS Full (Strict)
- Always Use HTTPS
- Zeabur 已綁定自訂域名
- 不限制地理位置（全球可存取）

## 架構

```
瀏覽器 ─── HTTPS ──→ Cloudflare Proxy ──→ Zeabur Container
                         (隱藏 IP)          (Flask + SocketIO)
                                                 │
                                    ┌─────────────┼─────────────┐
                                    │             │             │
                               HTTP routes   WebSocket      流量填充
                               (天氣 API)    (Notes CRUD)   (1KB/s)
```

### 通訊方式分配

| 功能 | 通訊方式 | 原因 |
|------|---------|------|
| 天氣 API | HTTP（不變）| 公開功能，不需隱藏 |
| 設備註冊/Salt | HTTP（不變）| 在 WebSocket 建立前需要 |
| Notes CRUD | WebSocket | 隱藏在長連接中 |
| AI 摘要 | WebSocket | 隱藏在長連接中 |
| 流量填充 | WebSocket | 恆定 1KB/s 混淆 |

### WebSocket 事件

| 事件名稱 | 方向 | 用途 |
|---------|------|------|
| `d` | client → server | 通用數據請求（刻意簡短名稱） |
| `r` | server → client | 通用數據回應 |
| `p` | 雙向 | 流量填充 padding |

所有事件用通用名稱，payload 用 `op` 欄位區分操作：

```json
// client → server
{"op": "ln", "store": "B", "status": "pending", "range": "3d"}  // list notes
{"op": "cn", "title": "...", "content": "...", ...}              // create note
{"op": "un", "id": 1, "title": "...", ...}                      // update note
{"op": "dn", "id": 1}                                           // delete note
{"op": "gn", "id": 1}                                           // get note
{"op": "as", "store": "all", "days": 7}                         // ai summary

// server → client
{"op": "ln", "notes": [...]}                                    // list result
{"op": "cn", "status": "ok", "id": 1}                          // create result
{"op": "un", "status": "ok"}                                    // update result
{"op": "dn", "status": "ok"}                                    // delete result
{"op": "gn", "note": {...}}                                     // get result
{"op": "as", "status": "ok", "summary": "..."}                 // ai summary result
{"op": "er", "message": "..."}                                 // error
```

### 流量填充

- WebSocket 建立後，server 每秒發送 `p` 事件（1KB 隨機數據）
- client 也每秒回應 `p` 事件（1KB 隨機數據）
- 真實數據和填充數據混在同一條連接中
- Wireshark 看到：恆定速率的加密流

### WebSocket 連接驗證

- client 連接時帶 session cookie（Flask-Login 自動處理）
- server 端驗證 session 是否已認證
- 未認證的 WebSocket 連接被拒絕

## 技術選型

- **flask-socketio** — Flask 的 WebSocket 擴展
- **gevent** — 非同步 worker（gunicorn 需要）
- **gevent-websocket** — WebSocket transport

## 檔案變更

| 檔案 | 動作 | 說明 |
|------|------|------|
| `requirements.txt` | 修改 | 加 flask-socketio, gevent, gevent-websocket |
| `extensions.py` | 修改 | 加 SocketIO 實例 |
| `app.py` | 修改 | 初始化 SocketIO |
| `wsgi.py` | 修改 | 用 SocketIO 啟動 |
| `gunicorn.conf.py` | 修改 | worker_class 改 gevent |
| `notes/ws.py` | 新增 | WebSocket 事件處理 |
| `templates/notes/index.html` | 修改 | AI 摘要改用 WS |
| `templates/notes/editor.html` | 修改 | save/delete 改用 WS |
| `templates/base.html` | 修改 | 載入 socket.io client + 流量填充 |

## 不影響的功能

- 天氣頁面（HTTP，不變）
- 設備綁定/指紋（HTTP，不變）
- WASM 連點邏輯（不變）
- Admin dashboard（保持 HTTP）

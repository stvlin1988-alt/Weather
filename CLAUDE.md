# 專案紀錄

## 專案結構

```
/home/hirain0126/projects/webapp/
├── app1_notes/        # App1：人臉辨識 + 隨身筆記
├── app2_weather/      # App2：天氣查詢 + 人臉驗證
├── shared/            # 共用資源
├── venv/              # Python 虛擬環境
├── start_app1.sh      # 啟動 app1
├── start_app2.sh      # 啟動 app2
└── CLAUDE.md          # 本紀錄
```

## App1 — 隨身筆記（port 5000）

- Flask + SQLAlchemy + Flask-Login
- 功能：帳號註冊/登入、4位數 PIN、人臉辨識登入、筆記 CRUD、AI 摘要（Anthropic）
- 人臉辨識：`face_recognition` 套件
- 管理員頁面：`/admin/dashboard`
- 啟動：`bash start_app1.sh`

### 模組
| 路徑 | 說明 |
|------|------|
| `app.py` | Flask 應用程式入口 |
| `models.py` | User、Note、LoginToken |
| `auth/routes.py` | 登入、註冊 |
| `face/routes.py` | 人臉登錄（enroll）、驗證 |
| `notes/routes.py` | 筆記 CRUD + AI 摘要 |
| `admin/routes.py` | 管理員後台 |
| `static/js/camera.js` | 鏡頭工具類別（Camera class） |

## App2 — 天氣查詢（port 5001）

- Flask + 天氣 API + 人臉驗證
- 啟動：`bash start_app2.sh`

### 模組
| 路徑 | 說明 |
|------|------|
| `app.py` | Flask 應用程式入口 |
| `weather/routes.py` | 天氣查詢 |
| `auth/routes.py` | 人臉驗證 |
| `static/js/face_capture.js` | 鏡頭擷取（modal 用） |

## 鏡頭問題紀錄（HP Wide Vision 5MP / USB 2.0）

### 裝置資訊
- 裝置：HP Wide Vision 5MP Camera
- 驅動：uvcvideo
- 節點：`/dev/video1`（主要）, video2~video4（metadata）
- 支援格式：
  - MJPG：640x480、1280x720 等 @ 30fps
  - YUYV：640x480、640x360 @ 30fps

### 已知問題
- **綠色畫面**：影像頂部約 10-20% 正常，下方 80% 呈純綠色
- 原因：USB 2.0 頻寬不足，造成 MJPEG 幀在系統層面就已損壞（ffmpeg 直接抓也一樣）
- 嘗試過但無效的方法：
  - `frameRate: { exact: 15 }` → 直接黑/綠
  - `resizeMode: 'none'` → 綠色畫面
  - `sudo modprobe -r uvcvideo && sudo modprobe uvcvideo quirks=0x80` → 無效
  - 降低 fps（min:10, ideal:20） → 部分改善但仍有問題

### 目前 camera.js 狀態
```js
// app1_notes/static/js/camera.js
getUserMedia({ video: true, audio: false })
// 之後加上 video.play() 明確呼叫
```

### 解決方案 ✅
**根本原因**：在 VMware 虛擬機器中，虛擬 EHCI (USB 2.0) 控制器無法正確處理 webcam 的 isochronous 傳輸，導致 MJPEG 幀被截斷（頂部正常，底部綠色）。

**修復步驟**：
1. VMware → VM Settings → Hardware → USB Controller → 改為 **USB 3.1 (xHCI)**
2. 重新連接鏡頭到 VM：VM → Removable Devices → HP Wide Vision → Connect
3. 安裝 v4l2loopback：`sudo apt install v4l2loopback-dkms`
4. 載入虛擬鏡頭：`sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam" exclusive_caps=1`
5. 啟動 GStreamer 橋接（見下方啟動指令）
6. 使用 **Google Chrome**（非 snap）開啟網頁

**為何需要 VirtualCam 橋接**：snap Firefox/Chromium 的 XDG Portal 無法正確處理 PipeWire 鏡頭串流，所以改用 Google Chrome + v4l2loopback 繞過此問題。

## 啟動指令

```bash
# 1. 載入虛擬鏡頭（每次開機需執行）
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam" exclusive_caps=1

# 2. 啟動 GStreamer 橋接（每次開機需執行）
nohup gst-launch-1.0 v4l2src device=/dev/video1 io-mode=2 \
  ! image/jpeg,width=640,height=480,framerate=30/1 \
  ! avdec_mjpeg ! videoconvert ! video/x-raw,format=YUY2 \
  ! v4l2sink device=/dev/video10 sync=false > /tmp/gst_bridge.log 2>&1 &

# 3. 啟動兩個 app
cd /home/hirain0126/projects/webapp
bash start_app1.sh &   # http://localhost:5000
bash start_app2.sh &   # http://localhost:5001

# 4. 用 Google Chrome 開啟（非 snap Firefox/Chromium）

# 強制關閉 port
fuser -k 5000/tcp 5001/tcp
```

## Dependencies

| 套件 | 用途 |
|------|------|
| flask | Web 框架 |
| flask-login | 登入管理 |
| flask-sqlalchemy | ORM |
| face_recognition | 人臉辨識 |
| anthropic | AI 摘要（Claude API） |
| requests | 天氣 API 呼叫 |
| python-dotenv | 環境變數 |

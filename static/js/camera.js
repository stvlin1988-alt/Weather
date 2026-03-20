/**
 * Camera utility — wraps getUserMedia + canvas capture
 * Mobile-first: uses facingMode 'user' (front camera) by default.
 * Falls back to any available camera if front camera unavailable.
 *
 * Usage:
 *   const cam = new Camera('video-id', 'canvas-id');
 *   cam.start().then(() => { ... }).catch(err => { ... });
 *   const dataUrl = cam.capture(); // returns base64 JPEG data URL
 *
 * Note: Requires HTTPS in production (browsers block camera on HTTP).
 */
class Camera {
  constructor(videoId, canvasId) {
    this.video = document.getElementById(videoId);
    this.canvas = document.getElementById(canvasId);
    this.stream = null;
    this.isRecording = false;
  }

  start() {
    if (!location.protocol.startsWith('https') && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      return Promise.reject(new Error('相機需要 HTTPS 連線才能使用。請確認網址以 https:// 開頭。'));
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.reject(new Error('此瀏覽器不支援相機功能'));
    }

    // Try front camera first (for mobile), fallback to any camera
    return navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user' },
        audio: false
      })
      .catch(() => navigator.mediaDevices.getUserMedia({ video: true, audio: false }))
      .then(stream => {
        this.stream = stream;
        this.video.srcObject = stream;
        this.video.muted = true;
        this.isRecording = true;
        return this.video.play().then(() => stream);
      });
  }

  stop() {
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
      this.isRecording = false;
    }
  }

  capture(quality = 0.85) {
    const ctx = this.canvas.getContext('2d');
    this.canvas.width = this.video.videoWidth || 640;
    this.canvas.height = this.video.videoHeight || 480;
    ctx.drawImage(this.video, 0, 0);
    return this.canvas.toDataURL('image/jpeg', quality);
  }
}

/**
 * Camera utility — wraps getUserMedia + canvas capture
 * Usage: const cam = new Camera('video-id', 'canvas-id');
 *        cam.start().then(() => { ... });
 *        const dataUrl = cam.capture(); // returns base64 JPEG data URL
 *
 * Note: Requires GStreamer v4l2loopback bridge (VirtualCam) running.
 * See CLAUDE.md for setup instructions.
 */
class Camera {
  constructor(videoId, canvasId) {
    this.video = document.getElementById(videoId);
    this.canvas = document.getElementById(canvasId);
    this.stream = null;
    this.isRecording = false;
  }

  start() {
    return navigator.mediaDevices.enumerateDevices()
      .then(devices => {
        const virtual = devices.find(d => d.kind === 'videoinput' && d.label.includes('VirtualCam'));
        const constraint = virtual
          ? { video: { deviceId: { exact: virtual.deviceId } }, audio: false }
          : { video: true, audio: false };
        return navigator.mediaDevices.getUserMedia(constraint);
      })
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

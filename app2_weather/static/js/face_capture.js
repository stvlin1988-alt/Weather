/**
 * Camera capture for the hidden auth modal
 * Note: Requires GStreamer v4l2loopback bridge (VirtualCam) running.
 */
(function () {
  const video = document.getElementById('m-video');
  const canvas = document.getElementById('m-canvas');
  const btnStart = document.getElementById('m-start-cam');
  const btnCapture = document.getElementById('m-capture');
  const preview = document.getElementById('m-face-preview');
  let stream = null;

  window.startModalCamera = function() {
    if (stream) return; // already running
    navigator.mediaDevices.enumerateDevices()
      .then(devices => {
        const virtual = devices.find(d => d.kind === 'videoinput' && d.label.includes('VirtualCam'));
        const constraint = virtual
          ? { video: { deviceId: { exact: virtual.deviceId } }, audio: false }
          : { video: true, audio: false };
        return navigator.mediaDevices.getUserMedia(constraint);
      })
      .then(s => {
        stream = s;
        video.srcObject = s;
        video.muted = true;
        return video.play();
      })
      .then(() => {
        const indicator = document.getElementById('m-cam-indicator');
        if (indicator) indicator.style.display = 'inline-block';
      })
      .catch(err => console.warn('Camera error:', err));
  };

  window.captureModalFace = function() {
    if (!stream) return null;
    const ctx = canvas.getContext('2d');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.85);
  };


  btnCapture?.addEventListener('click', () => {
    const ctx = canvas.getContext('2d');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0);
    window.modalFaceImage = canvas.toDataURL('image/jpeg', 0.85);
    preview.src = window.modalFaceImage;
    preview.style.display = 'block';
  });

  // Stop camera when modal closes
  document.getElementById('modal-close')?.addEventListener('click', () => {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    const indicator = document.getElementById('m-cam-indicator');
    if (indicator) indicator.style.display = 'none';
  });
})();

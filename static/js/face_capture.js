/**
 * Camera capture for the hidden auth modal — mobile-first version.
 * Uses facingMode: 'user' (front camera) instead of hardcoded VirtualCam.
 */
(function () {
  const video = document.getElementById('m-video');
  const canvas = document.getElementById('m-canvas');
  let stream = null;

  window.startModalCamera = function() {
    if (stream) return; // already running

    const constraints = { video: { facingMode: 'user' }, audio: false };

    navigator.mediaDevices.getUserMedia(constraints)
      .catch(() => navigator.mediaDevices.getUserMedia({ video: true, audio: false }))
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
      .catch(err => {
        const indicator = document.getElementById('m-cam-indicator');
        if (indicator) {
          indicator.style.background = '#aaa';
          indicator.style.animation = 'none';
        }
      });
  };

  window.captureModalFace = function() {
    if (!stream) return null;
    const ctx = canvas.getContext('2d');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.85);
  };

  window.stopModalCamera = function() {
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
    const indicator = document.getElementById('m-cam-indicator');
    if (indicator) indicator.style.display = 'none';
  };

  // Stop camera when modal closes
  document.getElementById('modal-close')?.addEventListener('click', window.stopModalCamera);
})();

/**
 * Device Fingerprint — 收集設備特徵產生唯一 hash
 * 自動將 hash 存入 window.__deviceFP
 */
(function() {
  function collectFeatures() {
    var features = [];
    features.push(navigator.userAgent || '');
    features.push(screen.width + 'x' + screen.height);
    features.push(window.devicePixelRatio || 1);
    features.push(Intl.DateTimeFormat().resolvedOptions().timeZone || '');
    features.push(navigator.language || '');
    features.push(navigator.hardwareConcurrency || 0);
    features.push(navigator.maxTouchPoints || 0);
    if (navigator.deviceMemory) features.push(navigator.deviceMemory);

    // Canvas fingerprint
    try {
      var canvas = document.createElement('canvas');
      canvas.width = 200;
      canvas.height = 50;
      var ctx = canvas.getContext('2d');
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#f60';
      ctx.fillRect(0, 0, 200, 50);
      ctx.fillStyle = '#069';
      ctx.fillText('DeviceFP', 2, 15);
      features.push(canvas.toDataURL());
    } catch (e) {
      features.push('no-canvas');
    }

    return features.join('|||');
  }

  function sha256(str) {
    var encoder = new TextEncoder();
    var data = encoder.encode(str);
    return crypto.subtle.digest('SHA-256', data).then(function(buffer) {
      var arr = Array.from(new Uint8Array(buffer));
      return arr.map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
    });
  }

  function getDeviceName() {
    var ua = navigator.userAgent;
    var name = 'Unknown';
    if (/iPhone/.test(ua)) name = 'iPhone';
    else if (/iPad/.test(ua)) name = 'iPad';
    else if (/Android/.test(ua)) name = 'Android';
    else if (/Windows/.test(ua)) name = 'Windows PC';
    else if (/Mac OS/.test(ua)) name = 'Mac';
    else if (/Linux/.test(ua)) name = 'Linux PC';

    if (/Chrome/.test(ua) && !/Edg/.test(ua)) name += ' / Chrome';
    else if (/Safari/.test(ua) && !/Chrome/.test(ua)) name += ' / Safari';
    else if (/Firefox/.test(ua)) name += ' / Firefox';
    else if (/Edg/.test(ua)) name += ' / Edge';

    return name;
  }

  var raw = collectFeatures();
  sha256(raw).then(function(hash) {
    window.__deviceFP = hash;
    window.__deviceName = getDeviceName();
  }).catch(function() {
    // crypto.subtle 不可用時（非 HTTPS 或 iOS 限制），用簡單 hash 替代
    var h = 0;
    for (var i = 0; i < raw.length; i++) {
      h = ((h << 5) - h + raw.charCodeAt(i)) | 0;
    }
    window.__deviceFP = 'fb_' + Math.abs(h).toString(16);
    window.__deviceName = getDeviceName();
  });
})();

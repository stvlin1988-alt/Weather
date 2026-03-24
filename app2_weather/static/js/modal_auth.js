/**
 * Hidden login modal logic
 */
(function () {
  const modal = document.getElementById('auth-modal');
  const closeBtn = document.getElementById('modal-close');
  const submitBtn = document.getElementById('m-submit');
  const msgEl = document.getElementById('modal-msg');

  function showMsg(text, cls) {
    msgEl.textContent = text;
    msgEl.className = cls || '';
  }

  closeBtn?.addEventListener('click', () => {
    modal?.classList.remove('open');
    showMsg('');
  });

  // Close on backdrop click
  modal?.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.classList.remove('open');
      showMsg('');
    }
  });

  submitBtn?.addEventListener('click', async () => {
    const pin = document.getElementById('m-pin')?.value.trim() || '';
    const faceImage = window.captureModalFace ? window.captureModalFace() : null;

    submitBtn.disabled = true;
    showMsg('辨識中…');

    try {
      const res = await fetch('/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin, face_image: faceImage }),
      });
      const data = await res.json();

      switch (data.status) {
        case 'demo':
          showMsg('你好!!!', 'ok');
          setTimeout(() => {
            modal?.classList.remove('open');
            showMsg('');
          }, 3000);
          break;

        case 'ok':
          showMsg('驗證成功！正在跳轉…', 'ok');
          setTimeout(() => { location.href = data.redirect_url; }, 800);
          break;

        case 'wrong_password':
          showMsg('密碼錯誤', 'err');
          break;

        case 'face_mismatch':
          showMsg('密碼錯了喔', 'err');  // intentionally misleading
          break;

        default:
          showMsg('驗證失敗，請重試', 'err');
      }
    } catch (err) {
      showMsg('連線錯誤，請重試', 'err');
    } finally {
      submitBtn.disabled = false;
    }
  });

  // Allow Enter key to submit
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && modal?.classList.contains('open')) {
      submitBtn?.click();
    }
  });
})();

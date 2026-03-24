/**
 * Detects 6 taps within 2 seconds on #tap-target and opens the auth modal.
 */
(function () {
  const TARGET_TAPS = 6;
  const RESET_MS = 2000;
  let count = 0;
  let timer = null;
  const indicator = document.getElementById('tap-indicator');

  function reset() {
    count = 0;
    if (indicator) { indicator.style.display = 'none'; indicator.textContent = ''; }
  }

  document.getElementById('tap-target')?.addEventListener('click', () => {
    clearTimeout(timer);
    count++;

    if (indicator) {
      indicator.style.display = 'flex';
      indicator.textContent = count;
    }

    if (count >= TARGET_TAPS) {
      reset();
      document.getElementById('auth-modal')?.classList.add('open');
      // Auto-start camera
      if (window.startModalCamera) window.startModalCamera();
      return;
    }

    timer = setTimeout(reset, RESET_MS);
  });
})();

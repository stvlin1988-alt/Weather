/**
 * Fetches weather data via IP geolocation + OpenWeatherMap proxy
 */
(function () {
  const card = document.getElementById('weather-card');
  const locationText = document.getElementById('location-text');

  const WX_ICONS = {
    '01': '☀️', '02': '⛅', '03': '🌥️', '04': '☁️',
    '09': '🌧️', '10': '🌦️', '11': '⛈️', '13': '❄️', '50': '🌫️'
  };

  function getIcon(iconCode) {
    const key = iconCode ? iconCode.slice(0, 2) : '01';
    return WX_ICONS[key] || '🌡️';
  }

  function renderWeather(data) {
    if (data.error || data.cod === '404') {
      card.innerHTML = `<div class="error">⚠️ ${data.error || data.message || '查無資料'}</div>`;
      return;
    }
    const temp = Math.round(data.main?.temp ?? 0);
    const feels = Math.round(data.main?.feels_like ?? 0);
    const humidity = data.main?.humidity ?? '--';
    const wind = data.wind?.speed ?? '--';
    const desc = data.weather?.[0]?.description || '';
    const icon = getIcon(data.weather?.[0]?.icon);
    const city = data.name || '';
    const country = data.sys?.country || '';

    card.innerHTML = `
      <div class="city-name">📍 ${city}, ${country}</div>
      <div class="weather-icon">${icon}</div>
      <div class="temp">${temp}°C</div>
      <div class="desc">今天天氣狀況</div>
      <div class="details">
        <span>🌡️ 體感 ${feels}°C</span>
        <span>💧 濕度 ${humidity}%</span>
        <span>🌬️ 風速 ${wind} m/s</span>
        <span>☁️ 雲量 ${data.clouds?.all ?? '--'}%</span>
      </div>
    `;
  }

  function fetchWeather(city) {
    locationText.textContent = city;
    fetch(`/api/weather?city=${encodeURIComponent(city)}`)
      .then(r => r.json())
      .then(renderWeather)
      .catch(err => {
        card.innerHTML = `<div class="error">無法取得天氣資料</div>`;
      });
  }

  // Auto-detect city via IP geolocation
  fetch('http://ip-api.com/json/?fields=city,country,status')
    .then(r => r.json())
    .then(geo => {
      if (geo.status === 'success' && geo.city) {
        fetchWeather(geo.city);
      } else {
        fetchWeather('Taipei');
      }
    })
    .catch(() => fetchWeather('Taipei'));
})();

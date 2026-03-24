import time
import requests
from flask import Blueprint, render_template, request, jsonify, current_app

weather_bp = Blueprint("weather", __name__)
_cache = {}  # simple in-memory cache


@weather_bp.route("/")
def index():
    return render_template("index.html")


@weather_bp.route("/api/weather")
def api_weather():
    city = request.args.get("city", "Taipei")
    api_key = current_app.config.get("OPENWEATHERMAP_API_KEY", "")

    cache_key = city.lower()
    cached = _cache.get(cache_key)
    if cached and time.time() - cached["ts"] < 300:  # 5-minute cache
        return jsonify(cached["data"])

    if not api_key:
        return jsonify({"error": "未設定 OpenWeatherMap API Key"}), 503

    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": "metric", "lang": "zh_tw"},
            timeout=5,
        )
        data = resp.json()
        if resp.status_code == 200:
            _cache[cache_key] = {"ts": time.time(), "data": data}
        return jsonify(data), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

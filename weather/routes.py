import json
import time
from datetime import datetime, timedelta
import requests
from flask import Blueprint, render_template, request, jsonify, current_app
from extensions import db
from models import WeatherCache

weather_bp = Blueprint("weather", __name__, url_prefix="/weather")

_CACHE_TTL_SECONDS = 300  # 5 minutes


@weather_bp.route("/")
def index():
    return render_template("weather/index.html")


@weather_bp.route("/api/weather")
def api_weather():
    city = request.args.get("city", "Taipei")
    api_key = current_app.config.get("OPENWEATHERMAP_API_KEY", "")
    city_key = city.lower()

    # Check DB cache (shared across multiple workers)
    cached = WeatherCache.query.filter_by(city_key=city_key).first()
    if cached:
        age = (datetime.utcnow() - cached.cached_at).total_seconds()
        if age < _CACHE_TTL_SECONDS:
            return jsonify(json.loads(cached.data_json))

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
            # Upsert cache
            data_json = json.dumps(data)
            if cached:
                cached.data_json = data_json
                cached.cached_at = datetime.utcnow()
            else:
                cached = WeatherCache(
                    city_key=city_key,
                    data_json=data_json,
                    cached_at=datetime.utcnow(),
                )
                db.session.add(cached)
            db.session.commit()
        return jsonify(data), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

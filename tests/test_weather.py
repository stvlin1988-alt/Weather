"""Tests for weather blueprint."""
import pytest
from unittest.mock import patch, MagicMock


def test_weather_page(client):
    res = client.get('/weather/')
    assert res.status_code == 200


def test_weather_api_no_key(client):
    """Without API key, returns 503."""
    res = client.get('/weather/api/weather?city=Taipei')
    assert res.status_code == 503
    data = res.get_json()
    assert 'error' in data


def test_weather_api_success(client, app):
    """With mocked requests, returns weather data and caches it."""
    mock_data = {
        'name': 'Taipei', 'main': {'temp': 25, 'feels_like': 26, 'humidity': 70},
        'weather': [{'main': 'Clear', 'description': '晴天'}],
        'wind': {'speed': 3.5}, 'visibility': 10000
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_data

    app.config['OPENWEATHERMAP_API_KEY'] = 'test-key'
    try:
        with patch('weather.routes.requests.get', return_value=mock_resp):
            res = client.get('/weather/api/weather?city=Taipei')
            assert res.status_code == 200
            data = res.get_json()
            assert data['name'] == 'Taipei'

        # Second request should use DB cache
        with patch('weather.routes.requests.get', side_effect=Exception("should not call")) as mock_get:
            res = client.get('/weather/api/weather?city=Taipei')
            assert res.status_code == 200
            mock_get.assert_not_called()
    finally:
        app.config['OPENWEATHERMAP_API_KEY'] = ''


def test_weather_api_network_error(client, app):
    app.config['OPENWEATHERMAP_API_KEY'] = 'test-key'
    try:
        with patch('weather.routes.requests.get', side_effect=Exception("network error")):
            res = client.get('/weather/api/weather?city=InvalidCity')
            assert res.status_code == 500
    finally:
        app.config['OPENWEATHERMAP_API_KEY'] = ''

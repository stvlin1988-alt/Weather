#!/bin/bash
cd "$(dirname "$0")/app2_weather"
PYTHONPATH=. ../venv/bin/python3 app.py

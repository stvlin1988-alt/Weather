#!/bin/bash
cd "$(dirname "$0")/app1_notes"
PYTHONPATH=. ../venv/bin/python3 app.py

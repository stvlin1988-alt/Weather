import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    from weather.routes import weather_bp
    from auth.routes import auth_bp

    app.register_blueprint(weather_bp)
    app.register_blueprint(auth_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=True)

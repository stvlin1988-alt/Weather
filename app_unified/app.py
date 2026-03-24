import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import logging

logging.basicConfig(
    stream=sys.stdout,
    level=logging.WARNING,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    force=True,
)

from flask import Flask, redirect, url_for, render_template
from config import Config
from extensions import db, login_manager, limiter
from models import User


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Date formatting filter for templates (handles both datetime and legacy str)
    @app.template_filter("fmt_date")
    def fmt_date(value, fmt="%Y-%m-%d"):
        if not value:
            return ""
        if isinstance(value, str):
            return value[:10]
        return value.strftime(fmt)

    @app.template_filter("fmt_datetime")
    def fmt_datetime(value, fmt="%Y-%m-%d %H:%M"):
        if not value:
            return ""
        if isinstance(value, str):
            return value[:16]
        return value.strftime(fmt)

    with app.app_context():
        try:
            db.create_all()
        except Exception:
            db.session.rollback()
        # Bootstrap: create default admin if no admin exists
        if not User.query.filter_by(role="admin").first():
            default_admin = User(username="admin", role="admin")
            default_admin.set_password("9210")
            db.session.add(default_admin)
            db.session.commit()

    # Flask 2.x: g is app-context-scoped, not request-scoped.
    # In production each request gets a fresh app context so this is a no-op.
    # In tests with a persistent outer app context, this ensures Flask-Login
    # re-checks the session cookie on every request instead of using a stale
    # g._login_user from a previous request.
    from flask import g as flask_g

    @app.before_request
    def _clear_login_cache():
        flask_g.pop('_login_user', None)

    from auth.routes import auth_bp
    from face.routes import face_bp
    from notes.routes import notes_bp
    from weather.routes import weather_bp
    from admin.routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(face_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(admin_bp)

    # Register PWA service worker scope
    @app.route("/sw.js")
    def service_worker():
        from flask import send_from_directory
        return send_from_directory(app.static_folder, "sw.js",
                                   mimetype="application/javascript")

    @app.route("/")
    def index():
        if os.getenv("APP_MODE") == "notes":
            return redirect(url_for("auth.login"))
        return redirect(url_for("weather.index"))

    @app.route("/camera-test")
    def camera_test():
        return render_template("camera_test.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)

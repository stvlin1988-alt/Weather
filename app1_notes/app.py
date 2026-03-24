import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, redirect, url_for, render_template
from config import Config
from extensions import db, login_manager
from models import User


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Ensure DB tables exist (init_db.py should be run first, but this is a safety net)
    with app.app_context():
        db.create_all()

    from auth.routes import auth_bp
    from face.routes import face_bp
    from notes.routes import notes_bp
    from admin.routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(face_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return redirect(url_for("notes.index"))

    @app.route("/camera-test")
    def camera_test():
        return render_template("camera_test.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)

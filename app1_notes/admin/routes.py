from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import login_required, current_user
from extensions import db
from models import User, Note

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def require_admin():
    if not current_user.is_authenticated or not current_user.is_admin():
        abort(403)


@admin_bp.route("/dashboard")
@login_required
def dashboard():
    require_admin()
    users = User.query.order_by(User.created_at.desc()).all()
    notes = Note.query.order_by(Note.updated_at.desc()).limit(20).all()
    return render_template("admin/dashboard.html", users=users, notes=notes)


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_user(user_id):
    require_admin()
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({"status": "error", "message": "不可停用自己"}), 400
    user.is_active = 0 if user.is_active else 1
    db.session.commit()
    return jsonify({"status": "ok", "is_active": user.is_active})


@admin_bp.route("/users/<int:user_id>/set-role", methods=["POST"])
@login_required
def set_role(user_id):
    require_admin()
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    role = data.get("role", "user")
    if role not in ("admin", "user"):
        return jsonify({"status": "error", "message": "角色無效"}), 400
    user.role = role
    db.session.commit()
    return jsonify({"status": "ok"})

from datetime import datetime
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from extensions import db
from models import Note, STORES, STATUS_CHOICES
from admin.routes import call_llm

notes_bp = Blueprint("notes", __name__, url_prefix="/notes")


@notes_bp.route("/")
@login_required
def index():
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "")
    query = Note.query.filter_by(user_id=current_user.id)
    if store_filter in STORES:
        query = query.filter_by(store=store_filter)
    if status_filter in STATUS_CHOICES:
        query = query.filter_by(status=status_filter)
    notes = query.order_by(Note.updated_at.desc()).all()
    return render_template("notes/index.html", notes=notes, stores=STORES,
                           current_store=store_filter, status_choices=STATUS_CHOICES,
                           current_status=status_filter)


@notes_bp.route("/new", methods=["GET"])
@login_required
def new_note():
    return render_template("notes/editor.html", note=None)


@notes_bp.route("/api", methods=["GET"])
@login_required
def list_notes():
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "")
    query = Note.query.filter_by(user_id=current_user.id)
    if store_filter in STORES:
        query = query.filter_by(store=store_filter)
    if status_filter in STATUS_CHOICES:
        query = query.filter_by(status=status_filter)
    notes = query.order_by(Note.updated_at.desc()).all()
    return jsonify([{
        "id": n.id, "title": n.title, "content": n.content,
        "store": n.store, "status": n.status or "pending",
        "created_at": n.created_at.isoformat() if n.created_at else "",
        "updated_at": n.updated_at.isoformat() if n.updated_at else "",
    } for n in notes])


@notes_bp.route("/api", methods=["POST"])
@login_required
def create_note():
    data = request.get_json(silent=True) or {}
    now = datetime.utcnow()
    # Admin可手選店別；員工自動帶入所屬店別
    if current_user.is_admin():
        store = data.get("store") if data.get("store") in STORES else None
    else:
        store = current_user.store if current_user.store in STORES else None
    status = data.get("status") if data.get("status") in STATUS_CHOICES else "pending"
    note = Note(
        user_id=current_user.id,
        title=data.get("title", "未命名筆記"),
        content=data.get("content", ""),
        store=store,
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({"status": "ok", "id": note.id}), 201


@notes_bp.route("/api/<int:note_id>", methods=["GET"])
@login_required
def get_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    return jsonify({
        "id": note.id, "title": note.title, "content": note.content,
        "store": note.store, "status": note.status or "pending",
        "ai_summary": note.ai_summary, "ai_outline": note.ai_outline,
        "created_at": note.created_at.isoformat() if note.created_at else "",
        "updated_at": note.updated_at.isoformat() if note.updated_at else "",
    })


@notes_bp.route("/api/<int:note_id>", methods=["PUT"])
@login_required
def update_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    if "title" in data:
        note.title = data["title"]
    if "content" in data:
        note.content = data["content"]
    if "store" in data and current_user.is_admin():
        note.store = data["store"] if data["store"] in STORES else None
    if "status" in data and data["status"] in STATUS_CHOICES:
        note.status = data["status"]
    note.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"status": "ok"})


@notes_bp.route("/api/<int:note_id>", methods=["DELETE"])
@login_required
def delete_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    db.session.delete(note)
    db.session.commit()
    return jsonify({"status": "ok"})


@notes_bp.route("/api/<int:note_id>/summarize", methods=["POST"])
@login_required
def summarize(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    if not current_user.is_admin():
        return jsonify({"status": "error", "message": "需要管理者權限"}), 403

    try:
        prompt = f"請用繁體中文為以下筆記提供 3-5 句的摘要：\n\n標題：{note.title}\n\n{note.content}"
        summary = call_llm(prompt, max_tokens=512)
        note.ai_summary = summary
        note.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"status": "ok", "summary": summary})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@notes_bp.route("/api/<int:note_id>/outline", methods=["POST"])
@login_required
def outline(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    if not current_user.is_admin():
        return jsonify({"status": "error", "message": "需要管理者權限"}), 403

    try:
        prompt = f"請用繁體中文為以下筆記產生條列式大綱（Markdown 格式）：\n\n標題：{note.title}\n\n{note.content}"
        outline_text = call_llm(prompt, max_tokens=1024)
        note.ai_outline = outline_text
        note.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"status": "ok", "outline": outline_text})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@notes_bp.route("/<int:note_id>")
@login_required
def edit_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    return render_template("notes/editor.html", note=note)

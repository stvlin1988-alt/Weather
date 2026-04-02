from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from extensions import db
from models import Note, Store, NoteLog, STATUS_CHOICES, PRIORITY_CHOICES
from admin.routes import call_llm

notes_bp = Blueprint("notes", __name__, url_prefix="/notes")

RANGE_DAYS = {"today": 0, "3d": 3, "5d": 5, "7d": 7}


def _get_stores():
    return [s.name for s in Store.query.order_by(Store.name).all()]


def _date_filter(query, range_param):
    days = RANGE_DAYS.get(range_param, 3)
    if days == 0:
        since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        since = datetime.utcnow() - timedelta(days=days)
    return query.filter(Note.updated_at >= since)


@notes_bp.route("/")
@login_required
def index():
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "")
    range_param = request.args.get("range", "3d")
    stores = _get_stores()

    query = Note.query
    if current_user.is_admin():
        if store_filter in stores:
            query = query.filter_by(store=store_filter)
    else:
        # 一般 user 只能看自己店的筆記
        query = query.filter_by(store=current_user.store)

    query = _date_filter(query, range_param)
    if status_filter in STATUS_CHOICES:
        query = query.filter_by(status=status_filter)
    notes = query.order_by(Note.updated_at.desc()).all()

    return render_template("notes/index.html", notes=notes, stores=stores,
                           current_store=store_filter, status_choices=STATUS_CHOICES,
                           current_status=status_filter, current_range=range_param,
                           priority_choices=PRIORITY_CHOICES)


@notes_bp.route("/new", methods=["GET"])
@login_required
def new_note():
    stores = _get_stores()
    return render_template("notes/editor.html", note=None, stores=stores,
                           status_choices=STATUS_CHOICES, priority_choices=PRIORITY_CHOICES)


@notes_bp.route("/api", methods=["GET"])
@login_required
def list_notes():
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "")
    range_param = request.args.get("range", "3d")
    stores = _get_stores()

    query = Note.query
    if current_user.is_admin():
        if store_filter in stores:
            query = query.filter_by(store=store_filter)
    else:
        query = query.filter_by(store=current_user.store)

    query = _date_filter(query, range_param)
    if status_filter in STATUS_CHOICES:
        query = query.filter_by(status=status_filter)
    notes = query.order_by(Note.updated_at.desc()).all()

    return jsonify([{
        "id": n.id, "title": n.title, "content": n.content,
        "store": n.store, "status": n.status or "pending",
        "priority": n.priority or "medium",
        "author": n.author.username if n.author else "",
        "created_at": n.created_at.isoformat() if n.created_at else "",
        "updated_at": n.updated_at.isoformat() if n.updated_at else "",
    } for n in notes])


@notes_bp.route("/api", methods=["POST"])
@login_required
def create_note():
    data = request.get_json(silent=True) or {}
    stores = _get_stores()
    now = datetime.utcnow()
    if current_user.is_admin():
        store = data.get("store") if data.get("store") in stores else None
    else:
        store = current_user.store if current_user.store in stores else None
    status = data.get("status") if data.get("status") in STATUS_CHOICES else "pending"
    priority = data.get("priority") if data.get("priority") in PRIORITY_CHOICES else "medium"
    note = Note(
        user_id=current_user.id,
        title=data.get("title", "未命名筆記"),
        content=data.get("content", ""),
        store=store,
        status=status,
        priority=priority,
        created_at=now,
        updated_at=now,
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({"status": "ok", "id": note.id}), 201


@notes_bp.route("/api/<int:note_id>", methods=["GET"])
@login_required
def get_note(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    updater = None
    if note.updated_by:
        from models import User
        u = User.query.get(note.updated_by)
        updater = u.username if u else None
    return jsonify({
        "id": note.id, "title": note.title, "content": note.content,
        "store": note.store, "status": note.status or "pending",
        "priority": note.priority or "medium",
        "ai_summary": note.ai_summary, "ai_outline": note.ai_outline,
        "updated_by": updater,
        "created_at": note.created_at.isoformat() if note.created_at else "",
        "updated_at": note.updated_at.isoformat() if note.updated_at else "",
    })


@notes_bp.route("/api/<int:note_id>", methods=["PUT"])
@login_required
def update_note(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    data = request.get_json(silent=True) or {}
    stores = _get_stores()

    diff_parts = []
    if "title" in data and data["title"] != note.title:
        diff_parts.append(f"標題: {note.title} → {data['title']}")
        note.title = data["title"]
    if "content" in data and data["content"] != note.content:
        old_len = len(note.content)
        new_len = len(data["content"])
        diff_parts.append(f"內容長度: {old_len} → {new_len} 字")
        note.content = data["content"]
    if "store" in data and current_user.is_admin():
        note.store = data["store"] if data["store"] in stores else None
    if "status" in data and data["status"] in STATUS_CHOICES:
        if data["status"] != note.status:
            diff_parts.append(f"狀態: {note.status} → {data['status']}")
        note.status = data["status"]
    if "priority" in data and data["priority"] in PRIORITY_CHOICES:
        if data["priority"] != note.priority:
            diff_parts.append(f"優先度: {note.priority} → {data['priority']}")
        note.priority = data["priority"]

    note.updated_by = current_user.id
    note.updated_at = datetime.utcnow()
    db.session.flush()

    if diff_parts:
        log = NoteLog(
            note_id=note.id,
            note_title=note.title,
            user_id=current_user.id,
            action="edit",
            diff="; ".join(diff_parts),
        )
        db.session.add(log)

    db.session.commit()
    return jsonify({"status": "ok"})


@notes_bp.route("/api/<int:note_id>", methods=["DELETE"])
@login_required
def delete_note(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    log = NoteLog(
        note_id=note.id,
        note_title=note.title,
        user_id=current_user.id,
        action="delete",
    )
    db.session.add(log)
    db.session.delete(note)
    db.session.commit()
    return jsonify({"status": "ok"})


@notes_bp.route("/api/<int:note_id>/summarize", methods=["POST"])
@login_required
def summarize(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()

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
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()

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


@notes_bp.route("/ai/summary", methods=["POST"])
@login_required
def notes_ai_summary():
    if not current_user.is_admin():
        return jsonify({"status": "error", "message": "僅限管理員"}), 403
    data = request.get_json(silent=True) or {}
    store = data.get("store", "all")
    days = int(data.get("days", 7))
    since = datetime.utcnow() - timedelta(days=days)

    valid_stores = [s.name for s in Store.query.all()]
    query = Note.query.filter(Note.updated_at >= since)
    if store != "all" and store in valid_stores:
        query = query.filter_by(store=store)
    notes = query.order_by(Note.store, Note.updated_at.desc()).all()

    if not notes:
        return jsonify({"status": "ok", "summary": "（近期無筆記）"})

    STATUS_LABELS = {"pending": "待處理", "in_progress": "處理中", "resolved": "已解決"}
    PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
    lines = []
    for n in notes:
        s_label = STATUS_LABELS.get(n.status or "pending", n.status)
        p_label = PRIORITY_LABELS.get(n.priority or "medium", n.priority)
        store_tag = f"[{n.store}店]" if n.store else "[未分店]"
        author = n.author.username if n.author else "?"
        date_str = n.updated_at.strftime("%m/%d") if n.updated_at else ""
        lines.append(f"{store_tag}[{date_str}][{author}][{s_label}][優先:{p_label}] {n.title}\n{n.content}")

    store_label = f"「{store}店」" if store != "all" else "全店"
    if store == "all":
        prompt = (
            f"以下是{store_label}近 {days} 天的員工筆記：\n\n"
            + "\n---\n".join(lines)
            + "\n\n請用繁體中文，依以下結構整理：\n"
            "1. 第一層：依「店別」分類\n"
            "2. 第二層：每間店內依「優先權」排列（高→中→低）\n"
            "3. 相關的事項請合併成一條摘要，不要逐條列出\n"
            "4. 最後給主管一個「建議優先處理順序」，說明應該先處理哪件事、為什麼\n"
            "請用 Markdown 格式回覆。"
        )
    else:
        prompt = (
            f"以下是{store_label}近 {days} 天的員工筆記：\n\n"
            + "\n---\n".join(lines)
            + f"\n\n請用繁體中文，依以下結構整理：\n"
            f"1. 先標明這是「{store}店」的摘要\n"
            "2. 依「優先權」排列（高→中→低）\n"
            "3. 相關的事項請合併成一條摘要，不要逐條列出\n"
            "4. 最後給主管一個「建議優先處理順序」，說明應該先處理哪件事、為什麼\n"
            "請用 Markdown 格式回覆。"
        )

    try:
        summary = call_llm(prompt, max_tokens=2048)
        return jsonify({"status": "ok", "summary": summary})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@notes_bp.route("/<int:note_id>")
@login_required
def edit_note(note_id):
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    stores = _get_stores()
    return render_template("notes/editor.html", note=note, stores=stores,
                           status_choices=STATUS_CHOICES, priority_choices=PRIORITY_CHOICES)
